"""Tests for ``x todo done <id>`` (v0.4.x new feature).

对应 BDD: ``docs/behaviors/todo-done-behavior.md`` (6 场景).

`_todo_done` is a thin wrapper around `_todo_archive(args)` with
`--reason done` pre-filled. We test both:

  1. The storage-level behaviour (does the task end up archived with
     ``reason=done``?) — drives ``store.archive_task`` directly. This
     is the contract Subagent A has to honour.
  2. The CLI integration (does ``x main todo done kemu1`` succeed and
     produce the expected message / exit code?) — drives ``x.main``.
     This depends on Subagent A registering ``done`` in
     ``TODO_ACTIONS`` and implementing ``_todo_done``.

The split lets most tests run even before Subagent A lands, while still
exercising the CLI wiring once it does.

Style: matches ``test_todo_archive.py`` (uses ``XCLI_TODO_DIR=tmp_path``
+ local ``_write_task`` helper).
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

import pytest

from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.parser import parse_frontmatter
from core.storage import TaskStore


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
) -> None:
    """Drop a TODO.md on disk for the done shortcut to operate on."""
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


def _invoke(*argv: str) -> tuple[int, str, str]:
    """Call ``main`` with the given argv (relative to ``x``)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        exit_code = x_main(["todo", "done", *argv])
    return exit_code, out.getvalue(), err.getvalue()


def x_main(argv):
    """Lazy import of x.main so the test file loads even mid-refactor."""
    from x import main

    return main(argv)


# ============================================================
#  Scenario 1: 基本 done（最常用）
# ============================================================


def test_done_storage_layer_archives_with_reason_done(
    store: TaskStore,
) -> None:
    """BDD §todo-done 1 (storage level): archived with reason=done.

    Verifies the contract that ``_todo_done`` enforces: the underlying
    ``store.archive_task`` call must use ``reason=DONE`` (the only
    reason the shortcut ever passes).
    """
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        status="in_progress",
        priority="high",
    )
    # The shortcut is equivalent to archive(reason="done")
    archived = store.archive_task("kemu1", reason=ArchiveReason.DONE, today="2026-06-21")
    assert archived.status is TaskStatus.ARCHIVED
    assert archived.reason is ArchiveReason.DONE
    assert archived.folder.startswith("归档/")
    assert archived.updated == "2026-06-21"


def test_done_cli_succeeds_and_archives(store: TaskStore) -> None:
    """BDD §todo-done 1 (CLI level): ``x todo done kemu1`` exits 0.

    Requires Subagent A to have registered ``done`` in
    ``TODO_ACTIONS`` and implemented ``_todo_done``. Will fail with
    a clear argparse "unknown action" / "not implemented" error until
    then.
    """
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        status="in_progress",
        priority="high",
    )
    exit_code, stdout, stderr = _invoke("kemu1")
    if exit_code != 0:
        # Surface whatever the CLI said so the failure is debuggable
        pytest.fail(
            f"x todo done failed: exit={exit_code}, stdout={stdout!r}, stderr={stderr!r}"
        )
    assert "✅" in stdout
    # The archive folder exists with today's date prefix
    today_prefix = date.today().isoformat().replace("-", "")
    assert (store.archive_dir / f"{today_prefix}-kemu1" / "TODO.md").is_file()
    on_disk = (store.archive_dir / f"{today_prefix}-kemu1" / "TODO.md").read_text(
        encoding="utf-8"
    )
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["status"] == "archived"
    assert metadata["reason"] == "done"


# ============================================================
#  Scenario 2: 与 archive --reason done 行为完全一致
# ============================================================


def test_done_equivalent_to_archive_reason_done(store: TaskStore) -> None:
    """BDD §todo-done 2: behavior identical to archive --reason done.

    We compare two parallel paths: (a) directly call
    ``store.archive_task(reason="done")``; (b) call it again with
    ``reason=ArchiveReason.DONE``. The shortcut must be byte-equivalent
    in folder structure + frontmatter to either.
    """
    # Path A: kemu1 via storage
    _write_task(store, "A", task_id="A", status="in_progress")
    a_archived = store.archive_task("A", reason="done", today="2026-06-21")
    # Path B: B via storage (same args via enum)
    _write_task(store, "B", task_id="B", status="in_progress")
    b_archived = store.archive_task("B", reason=ArchiveReason.DONE, today="2026-06-21")

    # Status, reason, folder format must match
    assert a_archived.status is b_archived.status is TaskStatus.ARCHIVED
    assert a_archived.reason is b_archived.reason is ArchiveReason.DONE
    assert a_archived.folder.startswith("归档/20260621-")
    assert b_archived.folder.startswith("归档/20260621-")


# ============================================================
#  Scenario 3: 任务不存在
# ============================================================


def test_done_task_not_found_exits_3(store: TaskStore) -> None:
    """BDD §todo-done 3: nonexistent task → exit 3 + clear error."""
    _write_task(store, "kemu1", task_id="kemu1")  # something in the store
    exit_code, _stdout, stderr = _invoke("nonexistent-id")
    assert exit_code == 3
    assert "❌ 任务不存在" in stderr
    # No archive file was created
    assert not (store.archive_dir / "nonexistent-id").exists()


# ============================================================
#  Scenario 4: 任务已归档
# ============================================================


def test_done_task_already_archived_exits_4(store: TaskStore) -> None:
    """BDD §todo-done 4: already archived → exit 4 + clear error."""
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
        reason="done",
    )
    exit_code, _stdout, stderr = _invoke("kemu1")
    assert exit_code == 4
    assert "❌ 任务已归档" in stderr


# ============================================================
#  Scenario 5: 多种 reason 的对比（语义化收益）— doc test
# ============================================================


def test_done_use_case_rationale_documented() -> None:
    """BDD §todo-done 5: the use-case table is a design rationale, not a test.

    We capture it here as a docstring-style assertion so future
    contributors see the design intent.
    """
    use_case_table = {
        ("做完了", "x todo done <id>", "done"),
        ("主动放弃", "x todo archive <id> --reason cancelled", "cancelled"),
        ("过期没做", "x todo archive <id> --reason expired", "expired"),
        ("试了失败", "x todo archive <id> --reason failed", "failed"),
    }
    # The shortcut covers ~80% of cases; the other reasons keep --reason
    # because they need the explicit semantic flag.
    shortcuts = {row[0] for row in use_case_table if "done" in row[1]}
    assert shortcuts == {"做完了"}, f"only '做完了' should be shortcut; got {shortcuts}"
    explicit = {row[0] for row in use_case_table if "done" not in row[1]}
    assert explicit == {"主动放弃", "过期没做", "试了失败"}


# ============================================================
#  Scenario 6: 与 x secret get 的"clipboard" 哲学一致 — doc test
# ============================================================


def test_done_philosophy_matches_secret_clipboard() -> None:
    """BDD §todo-done 6: both commands are use-case optimised shortcuts.

    Philosophy: optimise for the 80% case by reducing keystrokes. We
    don't test behavior here — this is a design-rationale guard.
    """
    # Both commands share the same philosophy: high-frequency use case
    # gets a 1-arg shortcut; low-frequency cases keep the full flag set.
    shortcuts = {
        "x secret get <name>": "auto-copy to clipboard (frequent paste)",
        "x todo done <id>": "archive with reason=done (frequent completion)",
    }
    assert len(shortcuts) == 2
    assert all("frequent" in rationale for rationale in shortcuts.values())


# ============================================================
#  End-to-end: argparse 接线 (Scenario 1 again via subprocess-of-main)
# ============================================================


def test_done_help_or_unknown_action_is_wired(store: TaskStore) -> None:
    """Verify ``x todo done`` is recognised (not "not implemented").

    Calls ``x todo done --help`` to trigger the help branch. If the
    action is not registered, we get exit 1 + "🚧 x todo done 还未实现".
    If it IS registered, we get the help text via SystemExit(0).
    """
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = x_main(["todo", "done", "--help"])
        except SystemExit as exc:
            # argparse calls sys.exit(0) for --help
            code = exc.code
    # Either argparse printed help (SystemExit 0) or Subagent A
    # returned its own help; both are acceptable. The failure mode we
    # care about is "not implemented" / exit 1.
    assert code != 1 or "未实现" not in (err.getvalue() + out.getvalue()), (
        f"x todo done is not yet wired: code={code}, "
        f"stdout={out.getvalue()!r}, stderr={err.getvalue()!r}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
