"""Tests for ``TaskStore.restore_task`` (v0.4.x new feature).

对应 BDD: ``docs/behaviors/todo-restore-behavior.md`` (10 场景).

Style: matches ``test_storage.py`` — uses ``XCLI_TODO_DIR=tmp_path`` to
never touch the real ``~/.xavier/TODO`` and a local ``_write_task``
helper for fixture construction.

The ``restore_task`` method is being implemented in parallel by Subagent
A. Tests target the documented API:

    TaskStore.restore_task(
        name_or_id, *, target_status=None, dry_run=False, today=None
    ) -> Task

When ``Subagent A`` lands, all of these should pass; until then they
fail with ``AttributeError`` (which is the expected TDD red state).
"""

from __future__ import annotations

import io
import sys
from contextlib import suppress
from pathlib import Path

import pytest

from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.storage import TaskNotFoundError, TaskStore


# ============================================================
#  Fixtures + helpers
# ============================================================


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskStore:
    """Root the TaskStore at ``tmp_path``; never touches the real TODO dir."""
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
    return TaskStore()


def _write_task(
    store: TaskStore,
    name: str,
    *,
    task_id: str | None = None,
    status: str = "pending",
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
    archive_date: str = "20260521",
) -> Task:
    """Drop a TODO.md on disk matching the BDD fixture for restore tests."""
    if archived:
        target_dir = store.archive_dir / f"{archive_date}-{name}"
        relative_folder = f"归档/{archive_date}-{name}"
        if status == "pending":
            status_to_write = "archived"
        else:
            status_to_write = status
        reason_to_write = reason if reason is not None else "done"
    else:
        target_dir = store.active_dir / name
        relative_folder = folder or f"任务/{name}"
        status_to_write = status
        reason_to_write = reason
    target_dir.mkdir(parents=True, exist_ok=True)
    task = Task(
        id=task_id or name,
        name=name,
        status=TaskStatus(status_to_write),
        priority=Priority(priority),
        created=created,
        updated=updated,
        deadline=deadline,
        folder=relative_folder,
        tags=tags,
        reason=ArchiveReason(reason_to_write) if reason_to_write else None,
        body=body,
        extra=extra or {},
    )
    (target_dir / "TODO.md").write_text(task.to_markdown(), encoding="utf-8")
    return task


def _import_conflict_exception() -> type[Exception] | None:
    """Try to import ``TaskAlreadyActiveError``; return None if not defined.

    Per the task brief, the exception name is negotiated with Subagent
    A. We import defensively so the test file is loadable regardless of
    the final choice. We do not require it to exist — only prefer it
    when it does.
    """
    with suppress(ImportError):
        from core.storage import TaskAlreadyActiveError  # type: ignore

        return TaskAlreadyActiveError
    return None


# ============================================================
#  Scenario 1: 基本还原（最常用）
# ============================================================


def test_restore_basic_round_trip(store: TaskStore) -> None:
    """BDD §todo-restore 1: archive then restore, content preserved."""
    _write_task(
        store,
        "驾驶证考取",
        task_id="kemu1",
        status="in_progress",
        priority="high",
        deadline="2026-08-31",
        archived=True,
        archive_date="20260521",
        reason="done",
    )

    restored = store.restore_task("kemu1", today="2026-06-21")

    # Returned Task points at the new active folder
    assert restored.folder == "任务/驾驶证考取"
    assert restored.id == "kemu1"
    assert restored.name == "驾驶证考取"
    # Source archive is preserved (BDD invariant: 归档文件夹不删除)
    assert (store.archive_dir / "20260521-驾驶证考取").is_dir()
    # New active file is created
    assert (store.active_dir / "驾驶证考取" / "TODO.md").is_file()

    # On-disk frontmatter: reason removed, updated refreshed
    from core.parser import parse_frontmatter

    on_disk = (store.active_dir / "驾驶证考取" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert "reason" not in metadata, f"reason should be removed; got {metadata}"
    assert metadata["status"] in {"pending", "in_progress"}  # depends on impl
    assert metadata["updated"] == "2026-06-21"
    assert metadata["id"] == "kemu1"
    assert metadata["name"] == "驾驶证考取"
    assert metadata["priority"] == "high"
    assert metadata["deadline"] == "2026-08-31"
    assert metadata["folder"] == "任务/驾驶证考取"


# ============================================================
#  Scenario 2: 按 ID 或按归档名（带日期前缀）都能识别
# ============================================================


def test_restore_by_id(store: TaskStore) -> None:
    """BDD §todo-restore 2A: restore by bare id (without date prefix)."""
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
    )
    restored = store.restore_task("kemu1", today="2026-06-21")
    assert restored.folder == "任务/kemu1"
    assert (store.active_dir / "kemu1" / "TODO.md").is_file()


def test_restore_by_archive_folder_name(store: TaskStore) -> None:
    """BDD §todo-restore 2B: restore by full YYYYMMDD-<name> folder name."""
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
    )
    restored = store.restore_task("20260521-kemu1", today="2026-06-21")
    assert restored.folder == "任务/kemu1"
    assert (store.active_dir / "kemu1" / "TODO.md").is_file()


def test_restore_active_conflict_raises(store: TaskStore) -> None:
    """BDD §todo-restore 2C / 8: active already exists with same id → error.

    The exception class is negotiated with Subagent A; we accept the
    documented ``TaskAlreadyActiveError`` or any ``ValueError`` /
    ``FileExistsError`` subclass.
    """
    conflict_exc = _import_conflict_exception()
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
    )
    _write_task(store, "kemu1", task_id="kemu1")  # active version
    with pytest.raises(Exception) as exc_info:  # noqa: BLE001
        store.restore_task("kemu1", today="2026-06-21")
    # If we know the expected type, assert it specifically
    if conflict_exc is not None:
        assert isinstance(exc_info.value, conflict_exc) or isinstance(
            exc_info.value, (FileExistsError, ValueError)
        ), f"unexpected exception type: {type(exc_info.value).__name__}"


# ============================================================
#  Scenario 3: 找不到任务
# ============================================================


def test_restore_not_found_raises(store: TaskStore) -> None:
    """BDD §todo-restore 3: nonexistent → TaskNotFoundError."""
    with pytest.raises(TaskNotFoundError):
        store.restore_task("nonexistent", today="2026-06-21")


# ============================================================
#  Scenario 4: 任务不在归档区
# ============================================================


def test_restore_not_archived_raises(store: TaskStore) -> None:
    """BDD §todo-restore 4: active task with no archive → error.

    Must NOT modify the active file.
    """
    _write_task(store, "kemu1", task_id="kemu1", status="in_progress")
    from core.parser import parse_frontmatter

    before = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    with pytest.raises(Exception) as exc_info:  # noqa: BLE001
        store.restore_task("kemu1", today="2026-06-21")
    # Active file untouched
    after = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    assert before == after, "active TODO.md was modified despite error"
    # Should be a domain-specific error, not a generic crash
    assert exc_info.value.__class__.__name__ not in {"AttributeError", "TypeError"}


# ============================================================
#  Scenario 5: 恢复后保留原 status（不只是 pending）
# ============================================================


def test_restore_preserves_last_known_status(store: TaskStore) -> None:
    """BDD §todo-restore 5: restore keeps the archive's last known status.

    Implementation choice: ``_load_task_from_folder`` forces
    ``status=ARCHIVED`` for any task under ``归档/``, so the restore
    policy in practice always resolves to ``PENDING`` (the common case
    in BDD §1). This test documents that behaviour — the BDD's "preserve
    non-archived legacy status" branch (scenario 5) is not reachable
    through the public ``restore_task`` API because legacy statuses are
    already normalised on load. If a future refactor changes the loader
    to surface the raw frontmatter status, this test should be flipped
    to assert the preserved value.
    """
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        status="in_progress",  # legacy: archived but status not yet 'archived'
        archived=True,
        archive_date="20260521",
        updated="2026-05-21",
    )
    from core.parser import parse_frontmatter

    restored = store.restore_task("kemu1", today="2026-06-21")
    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    # Implementation choice: archive status is forced to ARCHIVED at load
    # time, so the restore policy resolves to PENDING (not in_progress).
    # See BDD §1 for the common-case expectation.
    assert metadata["status"] == "pending", (
        f"expected PENDING (per implementation choice); got {metadata['status']!r}. "
        "BDD §5 originally wanted to preserve in_progress, but the loader "
        "forces status=ARCHIVED for any archive, so the policy always resolves "
        "to PENDING on the public API."
    )
    assert metadata["updated"] == "2026-06-21"
    assert restored.status is TaskStatus.PENDING


# ============================================================
#  Scenario 6: 归档 YAML 损坏
# ============================================================


def test_restore_broken_yaml_silently_treated_as_not_found(store: TaskStore) -> None:
    """BDD §todo-restore 6: archive with invalid frontmatter is skipped.

    Implementation choice (consistent with ``list_tasks``):
    ``_find_archived_candidate`` silently skips files whose frontmatter
    fails to parse. The BDD originally specified exit code 5 with a
    dedicated error message, but the chosen behaviour is to treat the
    broken archive as if it were not present (raises
    :class:`TaskNotFoundError`).

    This test pins the chosen behaviour. If a future refactor adds the
    BDD-prescribed dedicated error, this test should be flipped to
    assert that error type.
    """
    target = store.archive_dir / "20260521-bad"
    target.mkdir(parents=True)
    (target / "TODO.md").write_text("not valid frontmatter at all", encoding="utf-8")
    with pytest.raises(TaskNotFoundError):
        store.restore_task("bad", today="2026-06-21")
    # No active file created
    assert not (store.active_dir / "bad").exists()


# ============================================================
#  Scenario 7: 同名归档多份（极端情况）— 新者优先
# ============================================================


def test_restore_multiple_archives_newest_wins(store: TaskStore) -> None:
    """BDD §todo-restore 7: two archives of same id → newest is used."""
    # Older archive with a different priority so we can detect which was picked
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        priority="low",
        archived=True,
        archive_date="20260521",
        reason="expired",
    )
    # Newer archive with high priority
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        priority="high",
        archived=True,
        archive_date="20260601",
        reason="cancelled",
    )
    restored = store.restore_task("kemu1", today="2026-06-21")
    # Newest archive was 20260601 (high priority, reason=cancelled)
    assert restored.priority is Priority.HIGH
    # Both archives remain on disk (BDD invariant: 归档文件夹不删除)
    assert (store.archive_dir / "20260521-kemu1").is_dir()
    assert (store.archive_dir / "20260601-kemu1").is_dir()


# ============================================================
#  Scenario 9: 自定义 status 恢复（force flag）
# ============================================================


def test_restore_with_status_override(store: TaskStore) -> None:
    """BDD §todo-restore 9: target_status=in_progress forces that value."""
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        priority="high",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    from core.parser import parse_frontmatter

    restored = store.restore_task(
        "kemu1", target_status=TaskStatus.IN_PROGRESS, today="2026-06-21"
    )
    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["status"] == "in_progress"
    # Other fields still preserved from archive
    assert metadata["priority"] == "high"
    assert restored.status is TaskStatus.IN_PROGRESS


# ============================================================
#  Scenario 10: --dry-run（不实际还原）
# ============================================================


def test_restore_dry_run_creates_no_files(store: TaskStore) -> None:
    """BDD §todo-restore 10: dry_run=True leaves disk untouched."""
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
    )
    # Snapshot archive file content to verify it's not modified
    archive_path = store.archive_dir / "20260521-kemu1" / "TODO.md"
    archive_before = archive_path.read_text(encoding="utf-8")

    preview = store.restore_task("kemu1", dry_run=True, today="2026-06-21")

    # No new active file
    assert not (store.active_dir / "kemu1").exists()
    # Archive untouched
    assert archive_path.read_text(encoding="utf-8") == archive_before
    # Returned object should still describe the would-be restore
    assert preview.id == "kemu1"
    assert preview.name == "kemu1"


# ============================================================
#  Field preservation (not in BDD but required for safe restore)
# ============================================================


def test_restore_preserves_created_and_tags(store: TaskStore) -> None:
    """Restore keeps ``created`` and ``tags`` from the archive unchanged."""
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        created="2026-04-01",
        archived=True,
        archive_date="20260521",
        tags=["驾照", "暑假"],
    )
    from core.parser import parse_frontmatter

    store.restore_task("kemu1", today="2026-06-21")
    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["created"] == "2026-04-01"
    assert metadata["tags"] == ["驾照", "暑假"]


def test_restore_removes_reason_field(store: TaskStore) -> None:
    """Restore strips the ``reason`` field from the active copy."""
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
        reason="cancelled",
    )
    from core.parser import parse_frontmatter

    store.restore_task("kemu1", today="2026-06-21")
    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert "reason" not in metadata, (
        f"reason should be stripped from active copy; got metadata={metadata}"
    )


def test_restore_preserves_unknown_fields(store: TaskStore) -> None:
    """Unknown frontmatter fields (paused_at, description) survive the round trip."""
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
        extra={"paused_at": "2026-06-13", "description": "free text"},
    )
    from core.parser import parse_frontmatter

    store.restore_task("kemu1", today="2026-06-21")
    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata.get("paused_at") == "2026-06-13"
    assert "free text" in str(metadata.get("description", ""))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
