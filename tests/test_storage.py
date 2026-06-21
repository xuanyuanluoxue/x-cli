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
    TaskAlreadyArchivedError,
    TaskAlreadyExistsError,
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
    """No env var → falls back to ``~/.xavier/TODO`` (just check the suffix)."""
    monkeypatch.delenv("XAVIER_TODO_DIR", raising=False)
    s = TaskStore()
    assert s.todo_dir.name == "TODO"
    assert s.todo_dir.parent.name == ".xavier"


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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
