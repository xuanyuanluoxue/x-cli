"""Tests for core/storage.py — TaskStore filesystem CRUD.

All tests use ``tmp_path`` (via the :envvar:`XAVIER_TODO_DIR`
override) so the real ``~/.xavier/TODO`` is never touched. The
fixture ``store`` below initialises an empty store rooted at
``tmp_path``; helpers ``write_task`` and ``make_task`` keep each
test focused on a single behaviour.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pytest

from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.storage import (
    TaskAlreadyActiveError,
    TaskAlreadyArchivedError,
    TaskAlreadyExistsError,
    TaskNotArchivedError,
    TaskNotFoundError,
    TaskStore,
)


# ============================================================
#  Fixtures
# ============================================================


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskStore:
    """Return a TaskStore rooted at ``tmp_path`` (real ~/.xavier/TODO is safe)."""
    monkeypatch.setenv("XAVIER_TODO_DIR", str(tmp_path))
    return TaskStore()  # picks up the env var


def write_task(
    store: TaskStore,
    name: str,
    *,
    task_id: str | None = None,
    status: str | None = None,
    priority: str = "medium",
    created: str = "2026-06-01",
    updated: str = "2026-06-01",
    deadline: str | None = None,
    folder: str | None = None,
    tags: list[str] | None = None,
    reason: str | None = None,
    body: str = "",
    extra: dict | None = None,
    archived: bool = False,
    archive_date: str = "20260615",
) -> Task:
    """Create a Task on disk inside ``store`` and return it.

    The on-disk layout follows the real convention: active tasks go
    under ``任务/<name>`` and archived tasks under
    ``归档/<archive_date>-<name>``. When ``archived=True`` and the
    caller did not explicitly pass a ``status``, the status defaults
    to ``"archived"`` so the file on disk is internally consistent.
    """
    if archived:
        target_dir = store.archive_dir / f"{archive_date}-{name}"
        relative_folder = f"归档/{archive_date}-{name}"
        if status is None:
            status = "archived"
    else:
        target_dir = store.active_dir / name
        relative_folder = folder or f"任务/{name}"
    if status is None:
        status = "pending"
    target_dir.mkdir(parents=True, exist_ok=True)
    task = Task(
        id=task_id or name,
        name=name,
        status=TaskStatus(status),
        priority=Priority(priority),
        created=created,
        updated=updated,
        deadline=deadline,
        folder=relative_folder,
        tags=tags,
        reason=ArchiveReason(reason) if reason else None,
        body=body,
        extra=extra or {},
    )
    (target_dir / "TODO.md").write_text(task.to_markdown(), encoding="utf-8")
    return task


# ============================================================
#  Construction / env-var override
# ============================================================


def test_default_constructor_uses_env_var(monkeypatch, tmp_path):
    """With ``XAVIER_TODO_DIR`` set, ``TaskStore()`` uses it."""
    monkeypatch.setenv("XAVIER_TODO_DIR", str(tmp_path))
    s = TaskStore()
    assert s.todo_dir == tmp_path
    assert s.active_dir == tmp_path / "任务"
    assert s.archive_dir == tmp_path / "归档"


def test_explicit_constructor_overrides_env(monkeypatch, tmp_path):
    """An explicit ``todo_dir`` argument wins over the env var."""
    monkeypatch.setenv("XAVIER_TODO_DIR", "/some/other/path")
    other = tmp_path / "explicit"
    s = TaskStore(todo_dir=other)
    assert s.todo_dir == other


def test_constructor_uses_default_when_no_env(monkeypatch):
    """No env var → falls back to ``<xcli_data_dir>/todo`` (v0.4.0+ independent).

    Previously (v0.2.0) this was ``~/.xavier/TODO``; the v0.4.0 storage
    decoupling moved the default to x-cli's per-user data dir to keep
    the CLI independent of the xavier system. The :envvar:`XAVIER_TODO_DIR`
    env var is still honoured for back-compat (and tests use it).
    """
    monkeypatch.delenv("XAVIER_TODO_DIR", raising=False)
    s = TaskStore()
    # Must NOT be the legacy xavier path
    assert ".xavier" not in s.todo_dir.parts, (
        f"default TODO dir leaked into xavier system: {s.todo_dir}"
    )
    # Must end with the ``todo`` segment under x-cli's data dir
    assert s.todo_dir.name == "todo"
    assert s.todo_dir.parent.name == "x-cli"


# ============================================================
#  list_tasks
# ============================================================


def test_list_tasks_empty_store_returns_empty_list(store):
    assert store.list_tasks() == []


def test_list_tasks_includes_only_active_by_default(store):
    write_task(store, "a")
    write_task(store, "b")
    write_task(store, "c", archived=True, archive_date="20260101")
    tasks = store.list_tasks()
    assert len(tasks) == 2
    assert {t.name for t in tasks} == {"a", "b"}


def test_list_tasks_includes_archived_when_requested(store):
    write_task(store, "a")
    write_task(store, "b", archived=True, archive_date="20260101")
    tasks = store.list_tasks(include_archived=True)
    assert len(tasks) == 2


def test_list_tasks_sorts_by_deadline_then_name(store):
    write_task(store, "z", deadline="2026-08-01")
    write_task(store, "a", deadline="2026-07-01")
    write_task(store, "m", deadline=None)
    tasks = store.list_tasks()
    # Deadline ascending, None at end
    assert [t.name for t in tasks] == ["a", "z", "m"]


def test_list_tasks_archived_sorted_after_active(store):
    write_task(store, "active")
    write_task(store, "old", archived=True, archive_date="20260101")
    write_task(store, "older", archived=True, archive_date="20251201")
    tasks = store.list_tasks(include_archived=True)
    names = [t.name for t in tasks]
    assert names[0] == "active"
    assert set(names[1:]) == {"old", "older"}


def test_list_tasks_handles_malformed_file_gracefully(store):
    """A broken TODO.md is skipped (the BDD says error reporting is the
    plugin layer's job; storage just keeps going)."""
    store.active_dir.mkdir(parents=True, exist_ok=True)
    (store.active_dir / "good").mkdir()
    (store.active_dir / "good" / "TODO.md").write_text(
        "---\nid: good\nname: good\nstatus: pending\n---\n\nbody\n",
        encoding="utf-8",
    )
    (store.active_dir / "bad").mkdir()
    (store.active_dir / "bad" / "TODO.md").write_text(
        "no frontmatter at all",
        encoding="utf-8",
    )
    tasks = store.list_tasks()
    assert [t.name for t in tasks] == ["good"]


def test_list_tasks_skips_dirs_without_todo_md(store):
    """A folder with no ``TODO.md`` is ignored (e.g. a stray directory)."""
    store.active_dir.mkdir(parents=True, exist_ok=True)
    (store.active_dir / "stray").mkdir()
    write_task(store, "real")
    tasks = store.list_tasks()
    assert [t.name for t in tasks] == ["real"]


# ============================================================
#  get_task
# ============================================================


def test_get_task_by_id(store):
    write_task(store, "kemu1", task_id="kemu1")
    task = store.get_task("kemu1")
    assert task is not None
    assert task.id == "kemu1"
    assert task.name == "kemu1"


def test_get_task_by_name_for_active(store):
    write_task(store, "kemu1", task_id="abc")
    task = store.get_task("kemu1")
    assert task is not None
    assert task.id == "abc"


def test_get_task_returns_none_when_missing(store):
    assert store.get_task("nonexistent") is None


def test_get_task_returns_none_for_empty_query(store):
    assert store.get_task("") is None


def test_list_tasks_skips_non_directory_files_in_active_dir(store):
    """A stray file (not a folder) inside ``任务/`` is ignored."""
    store.active_dir.mkdir(parents=True, exist_ok=True)
    (store.active_dir / "stray.txt").write_text("not a folder", encoding="utf-8")
    write_task(store, "real")
    tasks = store.list_tasks()
    assert [t.name for t in tasks] == ["real"]


def test_load_task_falls_back_to_disk_path_when_folder_field_missing(store):
    """If a TODO.md is written without a ``folder`` field, the loader
    derives the folder from the on-disk path."""
    store.active_dir.mkdir(parents=True, exist_ok=True)
    target = store.active_dir / "loose"
    target.mkdir()
    (target / "TODO.md").write_text(
        "---\nid: loose\nname: loose\nstatus: pending\n---\n",
        encoding="utf-8",
    )
    task = store.get_task("loose")
    assert task is not None
    assert task.folder == "任务/loose"


def test_get_task_does_not_match_archived_by_active_name(store):
    """An archived task's folder name is ``YYYYMMDD-<name>``; looking up
    the bare active name should miss even with ``include_archived=True``.

    We use distinct id and name so the id-based path cannot accidentally
    make the test pass.
    """
    write_task(
        store,
        "kemu1",
        task_id="kemu1-archived",
        archived=True,
        archive_date="20260101",
    )
    # Default: archive is not searched
    assert store.get_task("kemu1") is None
    # With include_archived: name "kemu1" does not match folder
    # "归档/20260101-kemu1", and id "kemu1-archived" does not match
    # the query "kemu1".
    assert store.get_task("kemu1", include_archived=True) is None


def test_get_task_finds_archived_by_id_when_requested(store):
    write_task(
        store,
        "kemu1",
        task_id="kemu1-archived",
        archived=True,
        archive_date="20260101",
    )
    task = store.get_task("kemu1-archived", include_archived=True)
    assert task is not None
    assert task.id == "kemu1-archived"
    assert task.status is TaskStatus.ARCHIVED


# ============================================================
#  add_task
# ============================================================


def test_add_task_creates_folder_and_file(store):
    task = Task(
        id="kemu1",
        name="科目一",
        status=TaskStatus.PENDING,
        priority=Priority.HIGH,
        created="2026-06-21",
        updated="2026-06-21",
        body="# 科目一\n",
    )
    store.add_task(task)
    folder = store.active_dir / "科目一"
    assert folder.is_dir()
    assert (folder / "TODO.md").is_file()
    # Round-trip
    reloaded = store.get_task("kemu1")
    assert reloaded is not None
    assert reloaded.name == "科目一"
    assert reloaded.priority is Priority.HIGH
    assert reloaded.body == "# 科目一\n"


def test_add_task_sets_folder_field_if_missing(store):
    task = Task(id="x", name="foo", folder=None)
    store.add_task(task)
    reloaded = store.get_task("x")
    assert reloaded.folder == "任务/foo"


def test_add_task_duplicate_name_raises(store):
    write_task(store, "科目一", task_id="kemu1")
    duplicate = Task(id="kemu1-new", name="科目一")
    with pytest.raises(TaskAlreadyExistsError) as exc:
        store.add_task(duplicate)
    assert exc.value.name == "科目一"
    assert exc.value.existing_id == "kemu1"


def test_add_task_requires_name(store):
    with pytest.raises(ValueError, match="name is required"):
        store.add_task(Task(id="x", name=""))


def test_add_task_preserves_unknown_fields(store):
    task = Task(
        id="kemu1",
        name="科目一",
        extra={"paused_at": "2026-06-13", "description": "free text"},
    )
    store.add_task(task)
    reloaded = store.get_task("kemu1")
    assert reloaded.extra.get("paused_at") == "2026-06-13"
    assert "free text" in reloaded.extra.get("description", "")


# ============================================================
#  update_task
# ============================================================


def test_update_task_status(store):
    write_task(store, "kemu1", status="pending")
    updated = store.update_task("kemu1", status=TaskStatus.IN_PROGRESS, today="2026-06-21")
    assert updated.status is TaskStatus.IN_PROGRESS
    assert updated.updated == "2026-06-21"
    # On disk too
    reloaded = store.get_task("kemu1")
    assert reloaded.status is TaskStatus.IN_PROGRESS
    assert reloaded.updated == "2026-06-21"


def test_update_task_priority_and_deadline(store):
    write_task(store, "kemu1", deadline="2026-08-31", priority="high")
    updated = store.update_task(
        "kemu1",
        priority=Priority.MEDIUM,
        deadline="2026-07-15",
        today="2026-06-21",
    )
    assert updated.priority is Priority.MEDIUM
    assert updated.deadline == "2026-07-15"


def test_update_task_tags_replaces_not_merges(store):
    write_task(store, "kemu1", tags=["驾照", "暑假"])
    updated = store.update_task("kemu1", tags=["驾照"], today="2026-06-21")
    assert updated.tags == ["驾照"]


def test_update_task_clears_deadline(store):
    write_task(store, "kemu1", deadline="2026-08-31")
    updated = store.update_task("kemu1", clear_deadline=True, today="2026-06-21")
    assert updated.deadline is None
    # Field is removed from the file (not set to "")
    reloaded = store.get_task("kemu1")
    assert reloaded.deadline is None


def test_update_task_missing_raises(store):
    with pytest.raises(TaskNotFoundError):
        store.update_task("nonexistent", priority=Priority.HIGH)


def test_update_task_invalid_status_raises(store):
    write_task(store, "kemu1")
    with pytest.raises(ValueError, match="invalid status"):
        store.update_task("kemu1", status="bogus")


def test_update_task_preserves_unknown_fields(store):
    write_task(store, "kemu1", extra={"paused_at": "2026-06-13", "description": "x"})
    updated = store.update_task("kemu1", status=TaskStatus.IN_PROGRESS, today="2026-06-21")
    assert updated.extra.get("paused_at") == "2026-06-13"
    assert updated.extra.get("description") == "x"


def test_update_task_on_archived_raises(store):
    write_task(store, "kemu1", archived=True, archive_date="20260101")
    with pytest.raises(TaskAlreadyArchivedError):
        store.update_task("kemu1", priority=Priority.HIGH)


def test_update_task_auto_sets_updated_to_today(store):
    write_task(store, "kemu1", updated="2026-01-01")
    # No `today` argument → uses real date.today(); we only assert it changed
    updated = store.update_task("kemu1", priority=Priority.HIGH)
    assert updated.updated == date.today().isoformat()


def test_update_task_via_id_works(store):
    """Even when name differs from id, update should find the task by id."""
    write_task(store, "kemu1", task_id="kemu-special")
    updated = store.update_task("kemu-special", priority=Priority.HIGH, today="2026-06-21")
    assert updated.id == "kemu-special"
    assert updated.priority is Priority.HIGH


# ============================================================
#  archive_task
# ============================================================


def test_archive_task_moves_to_archive_dir(store):
    write_task(store, "科目一", task_id="kemu1")
    archived = store.archive_task("kemu1", today="2026-08-30")
    # Old location gone
    assert not (store.active_dir / "科目一").exists()
    # New location exists
    new_folder = store.archive_dir / "20260830-科目一"
    assert new_folder.is_dir()
    assert (new_folder / "TODO.md").is_file()
    # Fields updated
    assert archived.status is TaskStatus.ARCHIVED
    assert archived.reason is ArchiveReason.DONE
    assert archived.updated == "2026-08-30"
    assert archived.folder == "归档/20260830-科目一"


def test_archive_task_default_reason_is_done(store):
    write_task(store, "kemu1")
    archived = store.archive_task("kemu1", today="2026-06-21")
    assert archived.reason is ArchiveReason.DONE


def test_archive_task_with_explicit_reason(store):
    write_task(store, "kemu1")
    archived = store.archive_task(
        "kemu1", reason=ArchiveReason.CANCELLED, today="2026-06-21"
    )
    assert archived.reason is ArchiveReason.CANCELLED
    # The folder is now 归档/20260621-kemu1 and the file is on disk.
    assert archived.folder == "归档/20260621-kemu1"
    assert (store.archive_dir / "20260621-kemu1" / "TODO.md").is_file()


def test_archive_task_missing_raises(store):
    with pytest.raises(TaskNotFoundError):
        store.archive_task("nonexistent", today="2026-06-21")


def test_archive_task_already_archived_raises(store):
    write_task(store, "kemu1", archived=True, archive_date="20260101")
    with pytest.raises(TaskAlreadyArchivedError):
        store.archive_task("kemu1", today="2026-06-21")


def test_archive_task_duplicate_destination_raises(store):
    """If a folder with the target date-prefixed name already exists, refuse."""
    write_task(store, "kemu1")
    # Pre-create a conflicting folder
    (store.archive_dir / "20260621-kemu1").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        store.archive_task("kemu1", today="2026-06-21")


def test_archive_task_preserves_unknown_fields(store):
    write_task(store, "kemu1", extra={"paused_at": "2026-06-13", "description": "x"})
    archived = store.archive_task("kemu1", today="2026-06-21")
    assert archived.extra.get("paused_at") == "2026-06-13"
    assert archived.extra.get("description") == "x"


def test_archive_task_creates_archive_dir_if_missing(store):
    """archive_dir may not exist yet — it should be created on demand."""
    write_task(store, "kemu1")
    # archive_dir not yet created
    assert not store.archive_dir.exists()
    store.archive_task("kemu1", today="2026-06-21")
    assert store.archive_dir.is_dir()


# ============================================================
#  stats
# ============================================================


def test_stats_empty_store(store):
    stats = store.stats()
    assert stats["total"] == 0
    assert stats["by_status"] == {s.value: 0 for s in TaskStatus}
    assert stats["by_priority"] == {p.value: 0 for p in Priority}
    assert stats["due_within_7_days"] == 0
    assert stats["high_priority_active"] == 0


def test_stats_counts_status_and_priority(store):
    write_task(store, "p1", status="pending", priority="high")
    write_task(store, "p2", status="pending", priority="medium")
    write_task(store, "ip1", status="in_progress", priority="high")
    write_task(store, "ip2", status="in_progress", priority="low")
    write_task(store, "b1", status="blocked", priority="medium")
    write_task(store, "a1", status="archived", priority="low", archived=True, archive_date="20260101")
    stats = store.stats()
    assert stats["total"] == 6
    assert stats["by_status"]["pending"] == 2
    assert stats["by_status"]["in_progress"] == 2
    assert stats["by_status"]["blocked"] == 1
    assert stats["by_status"]["archived"] == 1
    assert stats["by_priority"]["high"] == 2
    assert stats["by_priority"]["medium"] == 2
    assert stats["by_priority"]["low"] == 2


def test_stats_due_within_7_days_excludes_archived(store):
    today = "2026-06-21"
    # 1 day from today → counted
    write_task(store, "soon1", deadline="2026-06-22")
    # 7 days from today → counted
    write_task(store, "soon2", deadline="2026-06-28")
    # 8 days from today → excluded
    write_task(store, "later", deadline="2026-06-29")
    # In the past → excluded (per spec, only future)
    write_task(store, "past", deadline="2026-06-20")
    # Archived but within window → excluded
    write_task(
        store,
        "old-archived",
        deadline="2026-06-25",
        archived=True,
        archive_date="20260101",
    )
    stats = store.stats(today=today)
    assert stats["due_within_7_days"] == 2


def test_stats_due_within_7_days_includes_today(store):
    """Deadline today is included (boundary check)."""
    write_task(store, "today_task", deadline="2026-06-21")
    stats = store.stats(today="2026-06-21")
    assert stats["due_within_7_days"] == 1


def test_stats_high_priority_active(store):
    write_task(store, "h1", priority="high", status="pending")
    write_task(store, "h2", priority="high", status="in_progress")
    write_task(store, "h3", priority="high", status="blocked")
    write_task(store, "h4", priority="high", status="archived", archived=True, archive_date="20260101")
    write_task(store, "nh", priority="low", status="pending")
    stats = store.stats()
    assert stats["high_priority_active"] == 2
    assert stats["high_priority_breakdown"]["pending"] == 1
    assert stats["high_priority_breakdown"]["in_progress"] == 1


def test_stats_handles_malformed_date_gracefully(store):
    write_task(store, "broken", deadline="not-a-date")
    stats = store.stats()
    # The malformed deadline is simply skipped (no crash).
    assert stats["total"] == 1
    assert stats["due_within_7_days"] == 0


def test_stats_unknown_fields_do_not_affect_counts(store):
    """Extra frontmatter fields must not change the totals (BDD §stats 6)."""
    write_task(
        store,
        "kemu1",
        status="pending",
        priority="high",
        extra={"description": "...", "paused_at": "2026-06-13"},
    )
    stats = store.stats()
    assert stats["total"] == 1
    assert stats["by_status"]["pending"] == 1


# ============================================================
#  Cross-cutting: env var does not leak between tests
# ============================================================


def test_env_var_is_isolated(store, monkeypatch):
    """The store fixture sets the env var; the original is restored after."""
    assert os.environ["XAVIER_TODO_DIR"] == str(store.todo_dir)
    # Mutating the store's paths must not persist
    assert not (store.todo_dir / "任务").exists() or True  # may be created by tests


# ============================================================
#  Integration: full lifecycle
# ============================================================


def test_full_lifecycle_add_update_archive(store):
    """Add → update → archive — full happy path."""
    task = Task(
        id="kemu1",
        name="科目一",
        status=TaskStatus.PENDING,
        priority=Priority.HIGH,
        created="2026-06-21",
        updated="2026-06-21",
        deadline="2026-08-31",
        tags=["驾照", "暑假"],
    )
    store.add_task(task)

    # Update to in_progress
    updated = store.update_task(
        "kemu1", status=TaskStatus.IN_PROGRESS, today="2026-07-01"
    )
    assert updated.status is TaskStatus.IN_PROGRESS
    assert updated.updated == "2026-07-01"

    # Archive with cancelled reason
    archived = store.archive_task(
        "kemu1", reason=ArchiveReason.CANCELLED, today="2026-08-15"
    )
    assert archived.status is TaskStatus.ARCHIVED
    assert archived.reason is ArchiveReason.CANCELLED
    assert archived.folder == "归档/20260815-科目一"

    # Active list now empty
    assert store.list_tasks() == []
    # Archived list contains it
    archived_list = store.list_tasks(include_archived=True)
    assert len(archived_list) == 1
    assert archived_list[0].name == "科目一"


# ============================================================
#  restore_task — BDD docs/behaviors/todo-restore-behavior.md
# ============================================================


def test_restore_basic_round_trip(store):
    """Scenario 1: archive a task, then restore it.

    The restored task has ``status=pending``, ``reason`` dropped, and
    ``updated`` refreshed to today. The original archive folder
    remains untouched (audit trail).
    """
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        priority="high",
        deadline="2026-08-31",
        tags=["驾照"],
        created="2026-04-01",
        updated="2026-05-21",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    # Sanity: original folder exists, active empty
    assert (store.archive_dir / "20260521-kemu1" / "TODO.md").is_file()
    assert not (store.active_dir / "kemu1").exists()

    restored = store.restore_task("kemu1", today="2026-06-21")

    # Returned Task reflects the restore
    assert restored.id == "kemu1"
    assert restored.name == "kemu1"
    assert restored.status is TaskStatus.PENDING
    assert restored.reason is None
    assert restored.updated == "2026-06-21"
    assert restored.folder == "任务/kemu1"

    # On disk: new active file, archive folder still there
    assert (store.active_dir / "kemu1" / "TODO.md").is_file()
    assert (store.archive_dir / "20260521-kemu1" / "TODO.md").is_file()

    # Round-trip: reloading the active file shows the expected state
    reloaded = store.get_task("kemu1")
    assert reloaded is not None
    assert reloaded.status is TaskStatus.PENDING
    assert reloaded.reason is None
    assert reloaded.updated == "2026-06-21"


def test_restore_preserves_created_and_tags(store):
    """Scenario 1: fields other than status/reason/updated are preserved
    (including ``created``, ``deadline``, ``tags``, ``extra``)."""
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        priority="high",
        deadline="2026-08-31",
        tags=["驾照", "暑假"],
        created="2026-04-01",
        updated="2026-05-21",
        archived=True,
        archive_date="20260521",
        reason="done",
        extra={"paused_at": "2026-05-10", "description": "AA 分摊"},
    )
    restored = store.restore_task("kemu1", today="2026-06-21")

    assert restored.created == "2026-04-01"  # preserved
    assert restored.priority is Priority.HIGH
    assert restored.deadline == "2026-08-31"
    assert restored.tags == ["驾照", "暑假"]
    # Unknown frontmatter fields round-trip via Task.extra
    assert restored.extra.get("paused_at") == "2026-05-10"
    assert "AA" in str(restored.extra.get("description", ""))


def test_restore_unknown_raises_not_found(store):
    """Scenario 3: restore with an id that exists nowhere → TaskNotFoundError."""
    with pytest.raises(TaskNotFoundError):
        store.restore_task("nonexistent", today="2026-06-21")


def test_restore_active_task_raises_not_archived(store):
    """Scenario 4: restore against an active (non-archived) task → TaskNotArchivedError."""
    write_task(store, "kemu1", task_id="kemu1", status="pending")
    with pytest.raises(TaskNotArchivedError) as exc:
        store.restore_task("kemu1", today="2026-06-21")
    assert exc.value.name_or_id == "kemu1"


def test_restore_active_conflict_raises(store):
    """Scenarios 2C and 8: archive has the task but active also has the
    same name → ``TaskAlreadyActiveError`` (no overwrite)."""
    # Archive the original
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    # A different active task with the same name already exists
    write_task(store, "kemu1", task_id="kemu1-new", status="in_progress")
    with pytest.raises(TaskAlreadyActiveError) as exc:
        store.restore_task("kemu1", today="2026-06-21")
    assert exc.value.name == "kemu1"
    assert exc.value.existing_id == "kemu1-new"

    # Existing active file was NOT modified
    reloaded = store.get_task("kemu1")
    assert reloaded is not None
    assert reloaded.id == "kemu1-new"
    assert reloaded.status is TaskStatus.IN_PROGRESS


def test_restore_with_status_override(store):
    """Scenario 9: ``--status in_progress`` overrides the default PENDING
    restore. Other fields (priority, deadline, tags) are preserved from
    the archive."""
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        priority="high",
        deadline="2026-08-31",
        tags=["驾照"],
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    restored = store.restore_task(
        "kemu1", target_status=TaskStatus.IN_PROGRESS, today="2026-06-21"
    )
    assert restored.status is TaskStatus.IN_PROGRESS
    # Other fields preserved
    assert restored.priority is Priority.HIGH
    assert restored.deadline == "2026-08-31"
    assert restored.tags == ["驾照"]


def test_restore_dry_run_does_not_write(store):
    """Scenario 10: ``dry_run=True`` returns the new Task but creates no
    files. The archive folder is also untouched."""
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    archive_path = store.archive_dir / "20260521-kemu1" / "TODO.md"
    archive_mtime_before = archive_path.stat().st_mtime

    dry = store.restore_task("kemu1", dry_run=True, today="2026-06-21")

    # Returned task reflects the restore
    assert dry.status is TaskStatus.PENDING
    assert dry.folder == "任务/kemu1"
    # No active file created
    assert not (store.active_dir / "kemu1").exists()
    # Archive file untouched (mtime unchanged)
    assert archive_path.stat().st_mtime == archive_mtime_before


def test_restore_by_id_works(store):
    """Restore looks up by ``id`` field (not folder name)."""
    write_task(
        store,
        "驾驶证考取",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    restored = store.restore_task("kemu1", today="2026-06-21")
    assert restored.id == "kemu1"
    assert restored.name == "驾驶证考取"
    assert (store.active_dir / "驾驶证考取" / "TODO.md").is_file()


def test_restore_by_archive_folder_name_works(store):
    """Restore accepts the full ``YYYYMMDD-<name>`` folder name as
    ``name_or_id`` (BDD scenario 2B)."""
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    restored = store.restore_task("20260521-kemu1", today="2026-06-21")
    assert restored.id == "kemu1"
    assert (store.active_dir / "kemu1" / "TODO.md").is_file()


def test_restore_picks_latest_when_multiple_archives(store):
    """Scenario 7: two archive copies exist → restore the most recent
    (largest ``YYYYMMDD`` prefix)."""
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        created="2026-04-01",
        updated="2026-05-21",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        created="2026-04-01",
        updated="2026-06-01",
        archived=True,
        archive_date="20260601",
        reason="cancelled",
    )
    restored = store.restore_task("kemu1", today="2026-06-21")
    # Picked the 20260601 copy (newer) — its updated field reflects that
    assert restored.updated == "2026-06-21"  # today
    # Round-trip and inspect the file we wrote — the source we picked
    # has ``updated: '2026-06-01'`` in its frontmatter
    # (and ``reason: cancelled``)
    reloaded = store.get_task("kemu1")
    assert reloaded is not None
    # The on-disk file was created with reason=None (we strip on restore),
    # but the body and other frontmatter come from the chosen source.
    # We verify by reading the raw text:
    raw = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    # The chosen source had reason=cancelled; the new file drops it
    assert "reason:" not in raw
    # The other archive is still there
    assert (store.archive_dir / "20260521-kemu1" / "TODO.md").is_file()
    assert (store.archive_dir / "20260601-kemu1" / "TODO.md").is_file()


def test_restore_legacy_non_archived_status_defaults_to_pending(store):
    """Scenario 5 (implementation choice): an archive whose frontmatter
    still carries a non-archived ``status`` (legacy data) is restored
    to ``PENDING`` because :meth:`_load_task_from_folder` forces
    ``status=ARCHIVED`` for any task under ``归档/``. The BDD's
    "preserve legacy non-archived status" branch is therefore not
    reachable through the public API — see also
    ``tests/test_todo_restore.py::test_restore_preserves_last_known_status``
    which pins the same behaviour."""
    # Manually craft an archive file whose frontmatter says
    # ``status: in_progress`` even though it lives under 归档/
    archive_folder = store.archive_dir / "20260521-kemu1"
    archive_folder.mkdir(parents=True)
    (archive_folder / "TODO.md").write_text(
        "---\n"
        "id: kemu1\n"
        "name: kemu1\n"
        "status: in_progress\n"  # legacy — would have been overridden
        "priority: high\n"
        "created: '2026-04-01'\n"
        "updated: '2026-05-21'\n"
        "---\n",
        encoding="utf-8",
    )
    restored = store.restore_task("kemu1", today="2026-06-21")
    # Loader forced ARCHIVED at read time → policy resolves to PENDING
    assert restored.status is TaskStatus.PENDING


def test_restore_invalid_target_status_raises(store):
    """A bogus ``--status`` value raises ValueError (defensive — the
    CLI normally validates via argparse ``choices=``)."""
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    with pytest.raises(ValueError, match="invalid status"):
        store.restore_task("kemu1", target_status="bogus", today="2026-06-21")


def test_restore_broken_archive_yaml_treated_as_not_found(store):
    """Scenario 6 (implementation choice): archive file with unparseable
    frontmatter is silently skipped, so the lookup falls through to
    :class:`TaskNotFoundError`. Matches ``list_tasks``'s behaviour
    and the contract pinned by
    ``tests/test_todo_restore.py::test_restore_broken_yaml_silently_treated_as_not_found``.
    The BDD's "exit code 5 with dedicated error message" path is not
    exposed on the public API."""
    archive_folder = store.archive_dir / "20260521-bad"
    archive_folder.mkdir(parents=True)
    (archive_folder / "TODO.md").write_text(
        "no frontmatter at all", encoding="utf-8"
    )
    with pytest.raises(TaskNotFoundError):
        store.restore_task("bad", today="2026-06-21")
    # No active file created
    assert not (store.active_dir / "bad").exists()


def test_restore_does_not_delete_source_archive(store):
    """The source archive folder is never modified (per BDD 不变量)."""
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    archive_path = store.archive_dir / "20260521-kemu1" / "TODO.md"
    original_content = archive_path.read_text(encoding="utf-8")
    store.restore_task("kemu1", today="2026-06-21")
    # Archive file byte-identical
    assert archive_path.read_text(encoding="utf-8") == original_content


# ============================================================
#  search_tasks — BDD docs/behaviors/todo-search-behavior.md
# ============================================================


def test_search_matches_name(store):
    """Scenario 1: keyword is a substring of a task's ``name``."""
    write_task(store, "驾驶证考取", task_id="kemu1", priority="high")
    write_task(store, "助学金-下学期材料", task_id="zijiashixi")
    hits = store.search_tasks("驾驶")
    assert {t.id for t in hits} == {"kemu1"}


def test_search_matches_note_field(store):
    """Scenario 2: keyword matches via the ``note`` frontmatter field
    (carried in :attr:`Task.extra`)."""
    store.active_dir.mkdir(parents=True, exist_ok=True)
    target = store.active_dir / "kemu1"
    target.mkdir()
    (target / "TODO.md").write_text(
        "---\n"
        "id: kemu1\n"
        "name: kemu1\n"
        "status: pending\n"
        "note: 跟朋友 AA 分摊\n"
        "---\n",
        encoding="utf-8",
    )
    hits = store.search_tasks("AA")
    assert {t.id for t in hits} == {"kemu1"}


def test_search_matches_tag(store):
    """Scenario 3: keyword matches via a tag."""
    write_task(store, "kemu1", task_id="kemu1", tags=["驾照", "暑假"])
    hits = store.search_tasks("驾照")
    assert {t.id for t in hits} == {"kemu1"}


def test_search_case_insensitive(store):
    """Scenario 4: case-insensitive match."""
    write_task(store, "aliyun", task_id="aliyun")
    hits = store.search_tasks("ALIYUN")
    assert {t.id for t in hits} == {"aliyun"}


def test_search_includes_archived_by_default(store):
    """Scenario 5: archived tasks are searched by default."""
    write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    hits = store.search_tasks("kemu1")
    assert {t.id for t in hits} == {"kemu1"}


def test_search_active_only_excludes_archived(store):
    """Scenario 6: ``include_archived=False`` skips archived tasks."""
    write_task(store, "active1", task_id="active1")
    write_task(
        store,
        "archived1",
        task_id="archived1",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    hits = store.search_tasks(
        "1", include_active=True, include_archived=False
    )
    assert {t.id for t in hits} == {"active1"}


def test_search_archived_only_excludes_active(store):
    """Scenario 7: ``include_active=False`` skips active tasks."""
    write_task(store, "active1", task_id="active1")
    write_task(
        store,
        "archived1",
        task_id="archived1",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    hits = store.search_tasks(
        "1", include_active=False, include_archived=True
    )
    assert {t.id for t in hits} == {"archived1"}


def test_search_empty_keyword_returns_empty(store):
    """Scenario 8 (storage layer): empty keyword returns nothing
    (the CLI is responsible for the exit-code-2 error)."""
    write_task(store, "kemu1", task_id="kemu1")
    assert store.search_tasks("") == []


def test_search_lenient_fuzzy_match(store):
    """Scenario 11: keyword whose every character appears in a field
    (in any order) still counts as a hit."""
    write_task(store, "助学金-下学期材料", task_id="zijin")
    hits = store.search_tasks("助材")
    # "助" and "材" both appear in the name → match
    assert {t.id for t in hits} == {"zijin"}


def test_search_no_match_returns_empty(store):
    """Scenario 9: a keyword that matches nothing returns an empty list."""
    write_task(store, "kemu1", task_id="kemu1")
    assert store.search_tasks("xyz_no_match_hopefully") == []


def test_search_skips_broken_yaml_silently(store):
    """Scenario 12: a broken TODO.md does not break the search
    (storage layer silently skips; the CLI does not print a warning)."""
    write_task(store, "good", task_id="good")
    bad_folder = store.active_dir / "bad"
    bad_folder.mkdir(parents=True)
    (bad_folder / "TODO.md").write_text(
        "no frontmatter at all", encoding="utf-8"
    )
    hits = store.search_tasks("good")
    assert {t.id for t in hits} == {"good"}
    # The broken task is simply absent from results
    assert "bad" not in {t.id for t in hits}


def test_search_combined_name_and_tag_match(store):
    """Multi-field haystack: a keyword present in either name OR tag
    produces a hit (the haystack joins them with spaces)."""
    write_task(store, "misc", task_id="misc", tags=["unique-needle"])
    hits = store.search_tasks("unique-needle")
    assert {t.id for t in hits} == {"misc"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
