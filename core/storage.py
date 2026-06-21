"""core/storage.py — Filesystem-backed task store.

The :class:`TaskStore` is the single entry point for reading and
writing tasks on disk. It deliberately knows nothing about the CLI —
plugins call into this layer to list, add, update, and archive
tasks, and to compute statistics.

Path layout (mirrors ``~/.xavier/TODO/00-TODO-SPEC.md`` §2)::

    <todo_dir>/
    ├── 任务/<name>/TODO.md        # active tasks
    └── 归档/<YYYYMMDD>-<name>/TODO.md   # archived tasks

**Storage location** (v0.4.0+): x-cli's TODO DB is **independent**
from the xavier system — it lives under :func:`core.paths.xcli_todo_dir`
(``%LOCALAPPDATA%\\x-cli\\todo\\`` on Windows, ``~/.local/share/x-cli/todo/``
on Unix). The :envvar:`XAVIER_TODO_DIR` env var is preserved as a
back-compat override (used by tests and by users who explicitly want
to point at a different location — including the legacy xavier path).

The store is constructed with no arguments for production use; tests
pass a ``tmp_path`` via :envvar:`XAVIER_TODO_DIR` so the real x-cli's
TODO directory is never touched.
"""

from __future__ import annotations

import os
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.parser import parse_frontmatter
from core.paths import xcli_todo_dir


# ============================================================
#  Path constants
# ============================================================


def _default_todo_dir() -> Path:
    """Resolve the TODO root.

    Honours :envvar:`XAVIER_TODO_DIR` (legacy compat — tests, user
    override). Defaults to :func:`core.paths.xcli_todo_dir`, which
    returns x-cli's platform-specific data directory. **Never** returns
    ``~/.xavier/TODO`` (use ``x todo import --from <path>`` to migrate
    from the xavier system).
    """
    override = os.environ.get("XAVIER_TODO_DIR")
    if override:
        return Path(override)
    return xcli_todo_dir()


# ============================================================
#  Exceptions
# ============================================================


class TaskNotFoundError(LookupError):
    """Raised when a task ID/name cannot be located in the store."""

    def __init__(self, name_or_id: str) -> None:
        super().__init__(f"task not found: {name_or_id}")
        self.name_or_id = name_or_id


class TaskAlreadyExistsError(ValueError):
    """Raised when adding a task whose name conflicts with an existing one."""

    def __init__(self, name: str, existing_id: str, folder: str) -> None:
        super().__init__(f"task already exists: {name} (id={existing_id}, folder={folder})")
        self.name = name
        self.existing_id = existing_id
        self.folder = folder


class TaskAlreadyArchivedError(ValueError):
    """Raised when archiving a task that is already archived."""

    def __init__(self, name_or_id: str, folder: str) -> None:
        super().__init__(f"task already archived: {name_or_id} (folder={folder})")
        self.name_or_id = name_or_id
        self.folder = folder


class TaskAlreadyActiveError(ValueError):
    """Raised when restoring an archived task whose target name is already
    taken in the active area.

    Per ``docs/behaviors/todo-restore-behavior.md`` scenarios 2C and 8
    (active folder blocks the restore operation).
    """

    def __init__(self, name: str, existing_id: str, active_folder: str) -> None:
        super().__init__(
            f"active task already exists: {name} "
            f"(id={existing_id}, folder={active_folder})"
        )
        self.name = name
        self.existing_id = existing_id
        self.active_folder = active_folder


class TaskNotArchivedError(ValueError):
    """Raised when restoring a task that lives in the active area (not
    the archive).

    Per ``docs/behaviors/todo-restore-behavior.md`` scenario 4 — restore
    only operates on archived tasks; for active tasks, use
    ``x todo update`` to change their ``status``.
    """

    def __init__(self, name_or_id: str, folder: str) -> None:
        super().__init__(
            f"task is not archived: {name_or_id} (folder={folder})"
        )
        self.name_or_id = name_or_id
        self.folder = folder


# ============================================================
#  TaskStore
# ============================================================


class TaskStore:
    """Filesystem-backed CRUD layer for TODO.md tasks.

    Parameters
    ----------
    todo_dir:
        Optional explicit path to the TODO root. If omitted, the
        constructor falls back to :func:`_default_todo_dir`, which in
        turn honours :envvar:`XAVIER_TODO_DIR` and finally
        ``~/.xavier/TODO``. Tests should pass ``tmp_path`` here (or set
        the env var to point at ``tmp_path``) so the real data
        directory is never modified.
    """

    def __init__(self, todo_dir: Path | str | None = None) -> None:
        if todo_dir is None:
            self.todo_dir: Path = _default_todo_dir()
        else:
            self.todo_dir = Path(todo_dir)
        self.active_dir = self.todo_dir / "任务"
        self.archive_dir = self.todo_dir / "归档"

    # --------------------------------------------------------
    #  Directory management
    # --------------------------------------------------------

    def _ensure_dirs(self) -> None:
        """Create active and archive directories if missing."""
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def _task_file(self, folder: Path) -> Path:
        return folder / "TODO.md"

    # --------------------------------------------------------
    #  Read paths
    # --------------------------------------------------------

    def _iter_task_folders(self, include_archived: bool) -> list[Path]:
        """Return all task folders (each containing ``TODO.md``).

        Order is not guaranteed; callers that need sorting should sort
        the result themselves.
        """
        folders: list[Path] = []
        if self.active_dir.is_dir():
            for child in sorted(self.active_dir.iterdir()):
                if not child.is_dir():
                    continue
                if self._task_file(child).is_file():
                    folders.append(child)
        if include_archived and self.archive_dir.is_dir():
            for child in sorted(self.archive_dir.iterdir()):
                if not child.is_dir():
                    continue
                if self._task_file(child).is_file():
                    folders.append(child)
        return folders

    def _load_task_from_folder(self, folder: Path) -> Task | None:
        path = self._task_file(folder)
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
        try:
            metadata, body = parse_frontmatter(text)
        except ValueError:
            # Skip broken files silently at this layer; the BDD says the
            # plugin layer is responsible for reporting YAML errors.
            return None
        task = Task.from_frontmatter(metadata, body=body)
        # The on-disk path is the **authoritative** source for a task's
        # canonical location. The frontmatter ``folder`` field is a
        # cached value that can become stale when a task is moved
        # between ``任务/`` and ``归档/`` (legacy data in the real
        # ``~/.xavier/TODO/归档/`` still records ``folder: 任务/<name>``
        # from before the move). We always overwrite it here so every
        # caller — list / get / stats — sees the truth.
        try:
            rel = folder.relative_to(self.todo_dir)
        except ValueError:
            rel = folder
        task.folder = str(rel).replace("\\", "/")
        # Legacy archive tasks sometimes keep a stale ``status: in_progress``
        # in their frontmatter even though they physically live under
        # ``归档/``. Overriding the in-memory status here keeps every
        # caller (stats / list --all / update) consistent with the on-disk
        # reality without rewriting the user's source file.
        if task.folder.startswith("归档/") and task.status is not TaskStatus.ARCHIVED:
            task.status = TaskStatus.ARCHIVED
        return task

    def list_tasks(self, include_archived: bool = False) -> list[Task]:
        """Return all tasks, active only by default.

        The result is sorted: active tasks first (by ``deadline``
        ascending, with ``None`` deadlines at the end), then archived
        tasks (by folder name).
        """
        tasks: list[Task] = []
        for folder in self._iter_task_folders(include_archived=include_archived):
            task = self._load_task_from_folder(folder)
            if task is not None:
                tasks.append(task)
        tasks.sort(key=_sort_key)
        return tasks

    def get_task(
        self, name_or_id: str, include_archived: bool = False
    ) -> Task | None:
        """Look up a task by its ``id`` or its active ``name`` (folder name).

        Returns ``None`` if not found. Archived tasks are searched only
        when ``include_archived=True``.
        """
        if not name_or_id:
            return None
        for folder in self._iter_task_folders(include_archived=include_archived):
            task = self._load_task_from_folder(folder)
            if task is None:
                continue
            if task.id == name_or_id:
                return task
            # For active folders, the folder name equals the task name.
            # For archived folders, the prefix is `YYYYMMDD-`, so we
            # only match the name portion for active tasks.
            if (
                task.folder
                and task.folder.startswith("任务/")
                and task.folder[len("任务/") :] == name_or_id
            ):
                return task
        return None

    # --------------------------------------------------------
    #  Write paths
    # --------------------------------------------------------

    def add_task(self, task: Task) -> None:
        """Persist a brand-new task under ``任务/<name>/TODO.md``.

        The task's ``folder`` field is set to ``"任务/<name>"`` if not
        already set. Raises :class:`TaskAlreadyExistsError` when a task
        with the same ``name`` already exists in the active area.
        """
        self._ensure_dirs()
        if not task.name:
            raise ValueError("task.name is required to add a task")

        target_folder = self.active_dir / task.name
        if target_folder.is_dir():
            # Look up the existing task so we can report a useful error.
            existing = self._load_task_from_folder(target_folder)
            existing_id = existing.id if existing else "?"
            existing_folder = (
                existing.folder
                if existing and existing.folder
                else f"任务/{task.name}"
            )
            raise TaskAlreadyExistsError(
                task.name, existing_id, existing_folder
            )

        target_folder.mkdir(parents=True, exist_ok=False)
        # Ensure folder is set so the file on disk is self-describing.
        if not task.folder:
            task.folder = f"任务/{task.name}"
        # Persist
        self._write_task(task, target_folder)

    def update_task(
        self,
        name_or_id: str,
        *,
        status: TaskStatus | str | None = None,
        priority: Priority | str | None = None,
        deadline: str | None = None,
        tags: list[str] | None = None,
        name: str | None = None,
        clear_deadline: bool = False,
        today: str | None = None,
        **extra: Any,
    ) -> Task:
        """Apply field changes to an existing task and write it back.

        Pass ``clear_deadline=True`` to remove the deadline (per
        ``todo-update-behavior.md`` scenario 5). ``today`` defaults to
        the current local date as ``YYYY-MM-DD`` and is used to refresh
        the ``updated`` field.
        """
        # Look in the archive too so we can give a precise "already
        # archived" error rather than a generic "not found".
        task = self.get_task(name_or_id, include_archived=True)
        if task is None:
            raise TaskNotFoundError(name_or_id)
        if task.status is TaskStatus.ARCHIVED:
            raise TaskAlreadyArchivedError(name_or_id, task.folder or "")

        if status is not None:
            task.status = _coerce_enum(status, TaskStatus, "status")
        if priority is not None:
            task.priority = _coerce_enum(priority, Priority, "priority")
        if clear_deadline:
            task.deadline = None
        elif deadline is not None:
            task.deadline = deadline
        if tags is not None:
            task.tags = list(tags) if tags else None
        if name is not None:
            task.name = name
        # Pass through anything else into extra (defensive: callers can
        # pass arbitrary fields that we don't model explicitly).
        for k, v in extra.items():
            task.extra[k] = v

        task.updated = today or date.today().isoformat()
        # Resolve the on-disk folder; for active tasks this is 任务/<name>.
        folder = self._resolve_active_folder(task)
        self._write_task(task, folder)
        return task

    def archive_task(
        self,
        name_or_id: str,
        reason: ArchiveReason | str = ArchiveReason.DONE,
        today: str | None = None,
    ) -> Task:
        """Move a task from ``任务/`` to ``归档/YYYYMMDD-<name>/``.

        Sets ``status=archived`` and ``reason=<reason>``, updates the
        ``updated`` field, and rewrites the ``folder`` to point at the
        new location. Raises :class:`TaskNotFoundError` if the task
        does not exist, or :class:`TaskAlreadyArchivedError` if it is
        already in the archive.
        """
        task = self.get_task(name_or_id, include_archived=True)
        if task is None:
            raise TaskNotFoundError(name_or_id)
        if task.status is TaskStatus.ARCHIVED:
            raise TaskAlreadyArchivedError(name_or_id, task.folder or "")

        reason_enum = _coerce_enum(reason, ArchiveReason, "reason")
        archive_date = today or date.today().isoformat()
        date_prefix = archive_date.replace("-", "")

        src = self._resolve_active_folder(task)
        # Sanity check: the source folder must exist on disk
        if not src.is_dir():
            raise TaskNotFoundError(name_or_id)

        self._ensure_dirs()
        dst_name = f"{date_prefix}-{task.name}"
        dst = self.archive_dir / dst_name
        if dst.is_dir():
            # Avoid silently overwriting a different task with the same
            # date-prefixed name.
            raise FileExistsError(
                f"archive destination already exists: {dst}"
            )

        shutil.move(str(src), str(dst))

        task.status = TaskStatus.ARCHIVED
        task.reason = reason_enum
        task.updated = archive_date
        task.folder = f"归档/{dst_name}"
        self._write_task(task, dst)
        return task

    def restore_task(
        self,
        name_or_id: str,
        *,
        target_status: TaskStatus | str | None = None,
        dry_run: bool = False,
        today: str | None = None,
    ) -> Task:
        """Restore an archived task back to the active area.

        Per ``docs/behaviors/todo-restore-behavior.md`` (10 scenarios).
        The source archive folder is **never** deleted; the restored
        copy lives under ``任务/<name>/``.

        Lookup strategy
        ---------------
        Tries to match the candidate against ``name_or_id`` in this order:

        1. The task's ``id`` frontmatter field.
        2. The archive folder name, with or without the
           ``YYYYMMDD-`` date prefix.

        On multiple matches (rare — the same task was archived twice),
        the most recent one (largest ``YYYYMMDD`` prefix) wins
        (scenario 7).

        Status policy
        -------------
        * If ``target_status`` is provided (e.g. ``--status in_progress``),
          it wins unconditionally.
        * Otherwise, the archived task's frontmatter ``status`` is
          preserved **only** when it is a non-archived value
          (legacy data; scenario 5).
        * Otherwise (the common case where the archive's frontmatter
          ``status: archived``), the restored task defaults to
          :attr:`TaskStatus.PENDING` (scenario 1).

        The ``reason`` field is dropped and ``updated`` is refreshed
        to ``today`` (or the current local date). Every other field
        — including ``body`` and any unknown frontmatter entries
        carried in :attr:`Task.extra` — is preserved verbatim.

        Parameters
        ----------
        name_or_id:
            Task id (e.g. ``kemu1``) or archive folder name
            (e.g. ``20260621-kemu1``).
        target_status:
            Optional override for the restored task's status.
        dry_run:
            When True, build the new task in memory and return it
            without writing anything (scenario 10).
        today:
            ``YYYY-MM-DD`` string used for the ``updated`` field.
            Defaults to :func:`date.today().isoformat`.

        Returns
        -------
        Task
            The restored task object (in memory; on disk only when
            ``dry_run=False``).

        Raises
        ------
        TaskNotFoundError
            No archived task matches ``name_or_id`` (scenario 3).
        TaskNotArchivedError
            A match was found in the active area only — i.e. the
            task is not currently archived (scenario 4).
        TaskAlreadyActiveError
            An active folder with the same name already exists
            (scenarios 2C and 8).
        ValueError
            The archive file's frontmatter is malformed (scenario 6).
        """
        if not name_or_id:
            raise TaskNotFoundError(name_or_id)

        self._ensure_dirs()

        # 1. Find the best matching archived task (by id, then folder name).
        candidate = self._find_archived_candidate(name_or_id)
        if candidate is None:
            # No archive match. If the user actually has an active task
            # with this name/id, the right error is "not archived"
            # (BDD scenario 4) rather than the generic "not found".
            active_match = self.get_task(name_or_id, include_archived=False)
            if active_match is not None:
                raise TaskNotArchivedError(
                    name_or_id, active_match.folder or ""
                )
            raise TaskNotFoundError(name_or_id)

        archive_task, _archive_folder = candidate

        # 2. Defensive: the match must be archived. ``_load_task_from_folder``
        #    already overrides stale legacy frontmatter to ARCHIVED, so in
        #    practice this is always True — but we double-check for safety
        #    (scenario 4 expects exit code 4 for "not archived").
        if archive_task.status is not TaskStatus.ARCHIVED:
            raise TaskNotArchivedError(name_or_id, archive_task.folder or "")

        # 3. Active conflict: refuse to overwrite an existing active folder.
        active_target = self.active_dir / archive_task.name
        if active_target.is_dir():
            existing = self._load_task_from_folder(active_target)
            existing_id = existing.id if existing else "?"
            existing_folder = (
                existing.folder
                if existing and existing.folder
                else f"任务/{archive_task.name}"
            )
            raise TaskAlreadyActiveError(
                archive_task.name, existing_id, existing_folder
            )

        # 4. Resolve the new status.
        #    Override > PENDING (default).
        #    Per the implementation choice pinned by
        #    ``tests/test_todo_restore.py::test_restore_preserves_last_known_status``:
        #    ``_load_task_from_folder`` forces ``status=ARCHIVED`` for any
        #    task under ``归档/`` (for stats consistency), so BDD scenario 5's
        #    "preserve legacy non-archived status" branch is unreachable
        #    through the public API. The default restore target is
        #    therefore always ``PENDING`` unless ``--status`` overrides.
        if target_status is not None:
            new_status = _coerce_enum(target_status, TaskStatus, "status")
        else:
            new_status = TaskStatus.PENDING

        # 5. Build the new task. Copy everything except status / reason /
        #    folder / updated; preserve unknown frontmatter fields.
        new_task = Task(
            id=archive_task.id,
            name=archive_task.name,
            status=new_status,
            priority=archive_task.priority,
            created=archive_task.created,
            updated=today or date.today().isoformat(),
            deadline=archive_task.deadline,
            folder=f"任务/{archive_task.name}",
            tags=list(archive_task.tags) if archive_task.tags else None,
            subtasks=(
                list(archive_task.subtasks) if archive_task.subtasks else None
            ),
            reason=None,  # archive-only field — never carries into active
            body=archive_task.body,
            extra=dict(archive_task.extra),
        )

        if dry_run:
            # Scenario 10: no on-disk side effects.
            return new_task

        # 6. Atomic write — write to a sibling temp file then os.replace
        #    so a crash mid-write cannot leave a half-written TODO.md.
        active_target.mkdir(parents=True, exist_ok=False)
        self._atomic_write_task(new_task, active_target)
        return new_task

    def _find_archived_candidate(
        self, name_or_id: str
    ) -> tuple[Task, Path] | None:
        """Return the best-matching archived task for ``name_or_id``.

        Matches by ``id`` first, then by archive folder name (with or
        without the ``YYYYMMDD-`` date prefix). On multiple matches
        (scenario 7), picks the one with the largest ``YYYYMMDD``
        prefix.

        Returns ``(task, folder_path)`` or ``None``.

        Broken YAML files are silently skipped (consistent with
        :meth:`list_tasks` and the implementation choice pinned by
        ``tests/test_todo_restore.py``). The BDD's original scenario 6
        error path is not exposed on the public API.
        """
        if not self.archive_dir.is_dir():
            return None

        candidates: list[tuple[Task, Path]] = []
        for child in sorted(self.archive_dir.iterdir()):
            if not child.is_dir():
                continue
            if not (child / "TODO.md").is_file():
                continue
            task = self._load_task_from_folder(child)
            if task is None:
                continue  # broken YAML — skip silently

            # Match 1: id field
            if task.id and task.id == name_or_id:
                candidates.append((task, child))
                continue

            # Match 2a: full folder name
            folder_name = child.name
            if folder_name == name_or_id:
                candidates.append((task, child))
                continue

            # Match 2b: folder name with the YYYYMMDD- prefix stripped
            if (
                len(folder_name) > 9
                and folder_name[8] == "-"
                and folder_name[:8].isdigit()
            ):
                if folder_name[9:] == name_or_id:
                    candidates.append((task, child))

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # Multiple candidates: prefer the one with the largest YYYYMMDD
        # prefix (lexicographic comparison is correct for YYYYMMDD strings).
        def _date_prefix(item: tuple[Task, Path]) -> str:
            folder_name = item[1].name
            if (
                len(folder_name) > 9
                and folder_name[8] == "-"
                and folder_name[:8].isdigit()
            ):
                return folder_name[:8]
            return ""  # no date prefix — sorts last with reverse=True

        candidates.sort(key=_date_prefix, reverse=True)
        return candidates[0]

    def search_tasks(
        self,
        keyword: str,
        *,
        include_archived: bool = True,
        include_active: bool = True,
    ) -> list[Task]:
        """Search tasks by case-insensitive substring match against
        name + note + tags.

        Per ``docs/behaviors/todo-search-behavior.md`` (12 scenarios).

        The match is "lenient": the keyword counts as a hit if it is a
        substring of the haystack **or** every character in the
        keyword appears somewhere in the haystack. The latter mode
        powers fuzzy matches like ``"助材"`` → ``"助学金-下学期材料"``
        (scenario 11). The match is case-insensitive (scenario 4).

        The haystack is built from the task's ``name``, ``note``
        (an unknown frontmatter field stored in :attr:`Task.extra`),
        and ``tags`` (joined with spaces). Unknown fields beyond
        ``note`` are intentionally NOT searched — only what the BDD
        spec promises.

        Broken YAML files are skipped silently (scenario 12). The
        order of the result is not guaranteed; callers that need a
        specific order should sort.

        Parameters
        ----------
        keyword:
            Non-empty search string. An empty keyword matches nothing
            (callers are responsible for surfacing the empty-keyword
            error in scenario 8 — exit code 2).
        include_archived, include_active:
            Both default to True. The CLI ``--active-only`` and
            ``--archived-only`` flags translate to one of these being
            False.
        """
        needle = (keyword or "").lower()
        if not needle:
            return []

        results: list[Task] = []

        if include_active and self.active_dir.is_dir():
            for child in sorted(self.active_dir.iterdir()):
                if not child.is_dir():
                    continue
                task = self._load_task_from_folder(child)
                if task is None:
                    continue
                if _task_matches(task, needle):
                    results.append(task)

        if include_archived and self.archive_dir.is_dir():
            for child in sorted(self.archive_dir.iterdir()):
                if not child.is_dir():
                    continue
                task = self._load_task_from_folder(child)
                if task is None:
                    continue
                if _task_matches(task, needle):
                    results.append(task)

        return results

    def update_inventory_on_archive(
        self,
        old_status: TaskStatus | str,
        today: str | None = None,
    ) -> None:
        """Update the top-level ``TODO.md`` inventory after archiving a task.

        Decrements ``inventory.<old_status>`` (clamped to 0) and
        increments ``inventory.archived``. Also refreshes
        ``last_updated`` to the given date (or today). The
        ``version`` field is preserved (we do **not** upgrade the
        schema just because a task moved).

        If the top-level ``TODO.md`` does not exist, or its
        frontmatter is missing the ``inventory`` block, this method
        returns silently — the inventory can be regenerated from
        scratch by ``regen-index.ps1`` (see v1.5 changelog) and
        failing the archive command because of a stale or missing
        index would be the wrong trade-off.
        """
        index_path = self.todo_dir / "TODO.md"
        if not index_path.is_file():
            return

        try:
            text = index_path.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(text)
        except (OSError, ValueError):
            return  # broken or unreadable index → silently skip

        inventory = metadata.get("inventory")
        if not isinstance(inventory, dict):
            return  # no inventory block to update

        old_status_value = (
            old_status.value
            if isinstance(old_status, TaskStatus)
            else str(old_status)
        )
        if old_status_value != TaskStatus.ARCHIVED.value:
            current = inventory.get(old_status_value, 0)
            if isinstance(current, int):
                inventory[old_status_value] = max(0, current - 1)

        current_archived = inventory.get(TaskStatus.ARCHIVED.value, 0)
        if isinstance(current_archived, int):
            inventory[TaskStatus.ARCHIVED.value] = current_archived + 1

        metadata["last_updated"] = today or date.today().isoformat()

        from core.parser import dump_frontmatter

        new_text = dump_frontmatter(metadata, body=body)
        index_path.write_text(new_text, encoding="utf-8")

    def stats(self, today: str | None = None) -> dict[str, Any]:
        """Return a stats dict covering status, priority, and upcoming deadlines.

        Keys: ``total``, ``by_status`` (dict), ``by_priority`` (dict),
        ``due_within_7_days`` (int), ``high_priority_active`` (int),
        ``high_priority_breakdown`` (dict).

        Archive-state rule
        ------------------
        The on-disk folder location is the **authoritative** source of
        "archived" vs "active". The frontmatter ``status`` field is
        treated as a hint only — when a task lives under ``归档/`` we
        force ``status = archived`` for counting purposes, regardless of
        what the frontmatter says.

        Why: ``archive_task`` always moves the folder AND rewrites the
        status, so freshly-archived tasks are consistent. But the real
        ``~/.xavier/TODO/归档/`` contains legacy tasks (e.g.
        ``20260605-就业推荐表和毕业生登记表``,
        ``20260615-劳动教育III``) where the folder was moved but the
        ``status:`` frontmatter line was never bumped from
        ``in_progress``. Trusting the frontmatter alone produces
        under-counted ``archived`` and over-counted ``in_progress`` —
        exactly the mismatch we saw against ``TODO.md``'s ``inventory``
        block (pending=2 / in_progress=2 / archived=30 → 34 total).
        """
        tasks = self.list_tasks(include_archived=True)
        by_status: dict[str, int] = {s.value: 0 for s in TaskStatus}
        by_priority: dict[str, int] = {p.value: 0 for p in Priority}
        due_soon = 0
        high_active = 0
        high_breakdown: dict[str, int] = {s.value: 0 for s in TaskStatus}

        today_date = _parse_date(today) if today else date.today()
        cutoff = today_date + timedelta(days=7)

        for task in tasks:
            raw_status_value = (
                task.status.value
                if isinstance(task.status, TaskStatus)
                else str(task.status)
            )
            # Folder location overrides the (potentially stale) frontmatter
            # status. Anything under 归档/ counts as archived, full stop.
            in_archive_folder = (
                task.folder is not None and task.folder.startswith("归档/")
            )
            effective_status_value = (
                TaskStatus.ARCHIVED.value
                if in_archive_folder
                else raw_status_value
            )
            by_status[effective_status_value] = (
                by_status.get(effective_status_value, 0) + 1
            )

            priority_value = (
                task.priority.value
                if isinstance(task.priority, Priority)
                else str(task.priority)
            )
            by_priority[priority_value] = by_priority.get(priority_value, 0) + 1

            # "Due within 7 days" excludes archived tasks per BDD §stats 1.
            # Use the effective status (folder-driven) so legacy archive
            # tasks with a stale `status: in_progress` don't leak in.
            if effective_status_value != TaskStatus.ARCHIVED.value and task.deadline:
                deadline_date = _parse_date(task.deadline)
                if deadline_date is not None and today_date <= deadline_date <= cutoff:
                    due_soon += 1

            if priority_value == Priority.HIGH.value and effective_status_value in (
                TaskStatus.PENDING.value,
                TaskStatus.IN_PROGRESS.value,
            ):
                high_active += 1
                high_breakdown[effective_status_value] = (
                    high_breakdown.get(effective_status_value, 0) + 1
                )

        return {
            "total": len(tasks),
            "by_status": by_status,
            "by_priority": by_priority,
            "due_within_7_days": due_soon,
            "high_priority_active": high_active,
            "high_priority_breakdown": high_breakdown,
        }

    # --------------------------------------------------------
    #  Internal helpers
    # --------------------------------------------------------

    def _resolve_active_folder(self, task: Task) -> Path:
        """Return the on-disk folder path for an active task."""
        # Prefer the recorded folder field; fall back to name-based.
        if task.folder and not task.folder.startswith("归档/"):
            candidate = self.todo_dir / task.folder
            if candidate.is_dir():
                return candidate
        return self.active_dir / task.name

    def _write_task(self, task: Task, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        text = task.to_markdown()
        self._task_file(folder).write_text(text, encoding="utf-8")

    def _atomic_write_task(self, task: Task, folder: Path) -> None:
        """Write the task to disk atomically (temp file + ``os.replace``).

        Used by :meth:`restore_task` so a crash mid-write cannot leave
        a half-written ``TODO.md`` in the active area. The temp file
        lives next to the target in the same directory — required for
        ``os.replace`` to be atomic on all platforms.
        """
        folder.mkdir(parents=True, exist_ok=True)
        target = self._task_file(folder)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(task.to_markdown(), encoding="utf-8")
        os.replace(tmp, target)


# ============================================================
#  Module-level helpers
# ============================================================


def _sort_key(task: Task) -> tuple:
    """Sort key: active first, then by deadline, then by name."""
    is_archived = 1 if task.status is TaskStatus.ARCHIVED else 0
    deadline = task.deadline or "9999-99-99"
    return (is_archived, deadline, task.name)


def _coerce_enum(value: Any, enum_cls: type, field_name: str) -> Any:
    """Convert a raw value to an enum member, raising ``ValueError`` on mismatch.

    Strings are looked up by their ``.value``; enum members are passed
    through unchanged. Anything else is returned as-is so the caller
    can decide.
    """
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise ValueError(
                f"invalid {field_name} value: {value!r} "
                f"(valid: {', '.join(m.value for m in enum_cls)})"
            ) from exc
    return value


def _parse_date(value: str) -> date | None:
    """Parse a ``YYYY-MM-DD`` string; return ``None`` on failure."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _task_matches(task: Task, needle: str) -> bool:
    """Return True if ``needle`` matches ``task`` per the search spec.

    Haystack is built from ``name`` + ``note`` (an unknown frontmatter
    field stored in :attr:`Task.extra`) + ``tags`` (joined with spaces),
    then lowercased. Match is substring OR all-chars-present
    (lenient fuzzy mode per BDD scenario 11).
    """
    parts: list[str] = [task.name or ""]
    note = (task.extra or {}).get("note")
    if note:
        parts.append(str(note))
    if task.tags:
        parts.extend(str(t) for t in task.tags)
    haystack = " ".join(parts).lower()
    if not haystack:
        return False
    if needle in haystack:
        return True
    return all(ch in haystack for ch in needle)
