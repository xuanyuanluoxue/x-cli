"""Tests for ``x todo stats`` command.

Each test maps to a scenario in
``docs/behaviors/todo-stats-behavior.md``. The command wraps
:meth:`core.storage.TaskStore.stats` and renders the result; tests
here exercise the formatter, the broken-YAML detector, the dispatcher
in ``x.py``, and the integration through ``x.main``.

All tests use ``tmp_path`` (via :envvar:`XCLI_TODO_DIR`) so the real
``~/.xavier/TODO`` is never touched.
"""

from __future__ import annotations

import io
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from core.models import Priority, Task, TaskStatus
from core.storage import TaskStore
from x import (
    _find_broken_tasks,
    _render_stats,
    _todo_stats,
    main,
)


# ============================================================
#  Fixtures and helpers
# ============================================================


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskStore:
    """Return a TaskStore rooted at ``tmp_path`` (real ~/.xavier/TODO is safe)."""
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
    return TaskStore()


def make_task(
    store: TaskStore,
    name: str,
    *,
    task_id: str | None = None,
    status: str = "pending",
    priority: str = "medium",
    deadline: str | None = None,
    created: str = "2026-06-01",
    updated: str = "2026-06-21",
    folder: str | None = None,
    tags: list[str] | None = None,
    body: str = "",
    extra: dict | None = None,
    archived: bool = False,
    archive_date: str = "20260601",
) -> Task:
    """Create a Task on disk and return it. Mirrors the helper in test_storage.py."""
    if archived:
        target_dir = store.archive_dir / f"{archive_date}-{name}"
        relative_folder = folder or f"归档/{archive_date}-{name}"
        if status == "pending":
            status = "archived"
    else:
        target_dir = store.active_dir / name
        relative_folder = folder or f"任务/{name}"
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
        body=body,
        extra=extra or {},
    )
    (target_dir / "TODO.md").write_text(task.to_markdown(), encoding="utf-8")
    return task


def run_stats(store: TaskStore) -> tuple[int, str, str]:
    """Invoke ``_todo_stats([])`` and return ``(exit_code, stdout, stderr)``."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = _todo_stats([])
    return code, out.getvalue(), err.getvalue()


# ============================================================
#  _render_stats — formatter unit tests
# ============================================================


def test_render_stats_empty_store():
    """Total=0 → no status breakdown lines (BDD §stats 2)."""
    stats = {
        "total": 0,
        "by_status": {"pending": 0, "in_progress": 0, "blocked": 0, "waiting": 0, "archived": 0},
        "by_priority": {"high": 0, "medium": 0, "low": 0},
        "due_within_7_days": 0,
        "high_priority_active": 0,
        "high_priority_breakdown": {"pending": 0, "in_progress": 0},
    }
    out = _render_stats(stats)
    assert "📊 TODO 统计信息" in out
    assert "总任务数：0" in out
    # No status breakdown when total is 0
    assert "⏳ pending" not in out
    assert "▶ in_progress" not in out
    assert "✅ archived" not in out
    # Priority section always present
    assert "🔥 high：0" in out
    assert "⚡ medium：0" in out
    assert "🐢 low：0" in out
    assert "即将到期（7 天内）：0" in out
    # No 🔥 高优先级任务 breakdown when no high-priority active
    assert "🔥 高优先级任务" not in out


def test_render_stats_full_breakdown_includes_all_five_status_lines():
    """When total > 0, all 5 status lines are always printed (commands.md §2.6)."""
    stats = {
        "total": 11,
        "by_status": {
            "pending": 3, "in_progress": 5, "blocked": 1,
            "waiting": 0, "archived": 2,
        },
        "by_priority": {"high": 4, "medium": 6, "low": 1},
        "due_within_7_days": 1,
        "high_priority_active": 0,
        "high_priority_breakdown": {"pending": 0, "in_progress": 0},
    }
    out = _render_stats(stats)
    assert "⏳ pending：3" in out
    assert "▶ in_progress：5" in out
    assert "⏸ blocked：1" in out
    assert "⌛ waiting：0" in out
    assert "✅ archived：2" in out
    assert "🔥 high：4" in out
    assert "⚡ medium：6" in out
    assert "🐢 low：1" in out
    assert "即将到期（7 天内）：1" in out


def test_render_stats_appends_high_priority_breakdown_when_present():
    """BDD §stats 5: 🔥 line appears when high-priority active tasks exist."""
    stats = {
        "total": 4,
        "by_status": {
            "pending": 2, "in_progress": 2, "blocked": 0,
            "waiting": 0, "archived": 0,
        },
        "by_priority": {"high": 4, "medium": 0, "low": 0},
        "due_within_7_days": 0,
        "high_priority_active": 4,
        "high_priority_breakdown": {"pending": 2, "in_progress": 2},
    }
    out = _render_stats(stats)
    assert "🔥 高优先级任务：4（⏳ pending: 2 / ▶ in_progress: 2）" in out


def test_render_stats_high_priority_breakdown_skips_when_zero():
    """No 🔥 line when high_priority_active == 0."""
    stats = {
        "total": 2,
        "by_status": {
            "pending": 2, "in_progress": 0, "blocked": 0,
            "waiting": 0, "archived": 0,
        },
        "by_priority": {"high": 0, "medium": 2, "low": 0},
        "due_within_7_days": 0,
        "high_priority_active": 0,
        "high_priority_breakdown": {"pending": 0, "in_progress": 0},
    }
    out = _render_stats(stats)
    assert "🔥 高优先级任务" not in out


def test_render_stats_returns_text_with_trailing_newline():
    """Output ends with a single trailing newline for clean piping."""
    stats = {
        "total": 0,
        "by_status": {"pending": 0, "in_progress": 0, "blocked": 0, "waiting": 0, "archived": 0},
        "by_priority": {"high": 0, "medium": 0, "low": 0},
        "due_within_7_days": 0,
        "high_priority_active": 0,
        "high_priority_breakdown": {"pending": 0, "in_progress": 0},
    }
    out = _render_stats(stats)
    assert out.endswith("\n")


# ============================================================
#  _find_broken_tasks — YAML error detector
# ============================================================


def test_find_broken_tasks_returns_empty_for_clean_store(store):
    assert _find_broken_tasks(store.todo_dir) == []


def test_find_broken_tasks_returns_empty_for_missing_dirs(store):
    """No 任务/ or 归档/ directories → no broken files."""
    # tmp_path exists but 任务/ and 归档/ do not
    assert _find_broken_tasks(store.todo_dir) == []


def test_find_broken_tasks_detects_malformed_yaml_in_active(store):
    store.active_dir.mkdir(parents=True, exist_ok=True)
    bad_folder = store.active_dir / "broken"
    bad_folder.mkdir()
    (bad_folder / "TODO.md").write_text(
        "this is not YAML frontmatter at all",
        encoding="utf-8",
    )
    broken = _find_broken_tasks(store.todo_dir)
    assert len(broken) == 1
    rel, err = broken[0]
    assert "broken" in str(rel)
    assert "frontmatter" in err.lower() or "yaml" in err.lower()


def test_find_broken_tasks_detects_malformed_yaml_in_archive(store):
    store.archive_dir.mkdir(parents=True, exist_ok=True)
    bad_folder = store.archive_dir / "20260101-bad"
    bad_folder.mkdir()
    # Missing the opening `---` on line 1 → parse_frontmatter raises.
    (bad_folder / "TODO.md").write_text(
        "id: bad\nname: bad\nthis is not enclosed in --- markers\n",
        encoding="utf-8",
    )
    broken = _find_broken_tasks(store.todo_dir)
    assert len(broken) == 1


def test_find_broken_tasks_returns_relative_paths(store):
    """Returned paths are relative to the TODO root (POSIX style)."""
    store.active_dir.mkdir(parents=True, exist_ok=True)
    bad_folder = store.active_dir / "broken"
    bad_folder.mkdir()
    (bad_folder / "TODO.md").write_text("no frontmatter", encoding="utf-8")
    broken = _find_broken_tasks(store.todo_dir)
    rel, _ = broken[0]
    assert not Path(rel).is_absolute()
    # Forward-slash separator per BDD §stats 7 example
    assert "\\" not in str(rel)


def test_find_broken_tasks_skips_dirs_without_todo_md(store):
    """A stray folder with no TODO.md is not 'broken' — it's just empty."""
    store.active_dir.mkdir(parents=True, exist_ok=True)
    (store.active_dir / "stray").mkdir()
    assert _find_broken_tasks(store.todo_dir) == []


# ============================================================
#  Scenario 1: regular stats
# ============================================================


def test_stats_regular_distribution(store):
    """BDD §stats 1: 11 tasks across all 5 statuses + 1 due-soon."""
    # pending=3 (kemu1 high, zizhushixi medium, laodongjiaoyu3 low)
    make_task(store, "kemu1", status="pending", priority="high", deadline="2026-08-31")
    make_task(store, "zizhushixi", status="pending", priority="medium", deadline="2026-09-15")
    make_task(store, "laodongjiaoyu3", status="pending", priority="low")
    # in_progress=5 — ip1 is the due-soon one, ip2 also high
    make_task(store, "ip1", status="in_progress", priority="high", deadline="2026-06-25")
    make_task(store, "ip2", status="in_progress", priority="high")
    make_task(store, "ip3", status="in_progress", priority="medium")
    make_task(store, "ip4", status="in_progress", priority="medium")
    make_task(store, "ip5", status="in_progress", priority="medium")
    # blocked=1 high (does not count as high_active per storage.stats rules)
    make_task(store, "blocked1", status="blocked", priority="high")
    # waiting=0
    # archived=2 medium
    make_task(
        store, "old1", status="archived", priority="medium",
        archived=True, archive_date="20260101",
    )
    make_task(
        store, "old2", status="archived", priority="medium",
        archived=True, archive_date="20260102",
    )

    # Today fixed so the "within 7 days" calc is deterministic
    s = store.stats(today="2026-06-21")
    assert s["total"] == 11
    assert s["by_status"]["pending"] == 3
    assert s["by_status"]["in_progress"] == 5
    assert s["by_status"]["blocked"] == 1
    assert s["by_status"]["waiting"] == 0
    assert s["by_status"]["archived"] == 2
    assert s["by_priority"]["high"] == 4   # kemu1 + ip1 + ip2 + blocked1
    assert s["by_priority"]["medium"] == 6  # zizhushixi + ip3+ip4+ip5 + old1+old2
    assert s["by_priority"]["low"] == 1     # laodongjiaoyu3
    assert s["due_within_7_days"] == 1      # only ip1 (deadline 2026-06-25)
    # high_active = pending(1) + in_progress(2) = 3 (blocked1 not counted)
    assert s["high_priority_active"] == 3


# ============================================================
#  Scenario 2: empty repo
# ============================================================


def test_stats_empty_repo(store):
    """BDD §stats 2: total=0, no status lines, all priority lines 0, due=0."""
    # No tasks created
    code, stdout, stderr = run_stats(store)
    assert code == 0
    assert stderr == ""
    assert "📊 TODO 统计信息" in stdout
    assert "总任务数：0" in stdout
    # Status breakdown omitted when total=0
    assert "⏳ pending" not in stdout
    assert "▶ in_progress" not in stdout
    assert "⏸ blocked" not in stdout
    assert "⌛ waiting" not in stdout
    assert "✅ archived" not in stdout
    # Priority breakdown always present
    assert "🔥 high：0" in stdout
    assert "⚡ medium：0" in stdout
    assert "🐢 low：0" in stdout
    assert "即将到期（7 天内）：0" in stdout
    # No 🔥 line
    assert "🔥 高优先级任务" not in stdout


# ============================================================
#  Scenario 3: only archived tasks
# ============================================================


def test_stats_only_archived(store):
    """BDD §stats 3: 5 archived tasks → total=5, archived=5, due=0."""
    for i in range(5):
        make_task(
            store, f"old{i}", status="archived", priority="medium",
            deadline="2026-06-25",  # within 7 days — should NOT count
            archived=True, archive_date=f"2026010{i}",
        )

    code, stdout, stderr = run_stats(store)
    assert code == 0
    assert stderr == ""
    assert "总任务数：5" in stdout
    # All 5 status lines shown when total > 0
    assert "⏳ pending：0" in stdout
    assert "▶ in_progress：0" in stdout
    assert "⏸ blocked：0" in stdout
    assert "⌛ waiting：0" in stdout
    assert "✅ archived：5" in stdout
    # Archived deadlines are excluded from "due within 7 days"
    assert "即将到期（7 天内）：0" in stdout


# ============================================================
#  Scenario 4: 7-day window boundary
# ============================================================


def test_stats_due_within_7_days_inclusive_boundaries(store):
    """BDD §stats 4: today and today+7 included; today+8 excluded.

    Fixes ``today`` to 2026-06-21 via a direct call to TaskStore.stats
    so the test is deterministic regardless of when it runs.
    """
    make_task(store, "t1", deadline="2026-06-21")  # today
    make_task(store, "t2", deadline="2026-06-28")  # +7
    make_task(store, "t3", deadline="2026-06-29")  # +8 → excluded
    make_task(store, "t4", deadline="2026-06-22")  # +1
    make_task(store, "t5", deadline="2026-06-20")  # yesterday → excluded

    s = store.stats(today="2026-06-21")
    assert s["due_within_7_days"] == 3  # t1, t2, t4


def test_stats_due_window_in_command_output(store):
    """The formatted output reflects the same boundary."""
    make_task(store, "soon1", deadline="2026-06-25")
    make_task(store, "soon2", deadline="2026-06-28")
    make_task(store, "later", deadline="2026-06-29")

    code, stdout, _ = run_stats(store)
    assert code == 0
    # Extract the count from the rendered output
    m = re.search(r"即将到期（7 天内）：(\d+)", stdout)
    assert m is not None
    count = int(m.group(1))
    # If today >= 2026-06-28 we miss soon1 but still count soon2; this test
    # only asserts the "later" task is excluded (count >= 1, count <= 2).
    assert 1 <= count <= 2


# ============================================================
#  Scenario 5: high-priority active breakdown
# ============================================================


def test_stats_high_priority_breakdown_appears(store):
    """BDD §stats 5: 🔥 line appended when high-active tasks exist."""
    make_task(store, "h1", status="pending", priority="high")
    make_task(store, "h2", status="pending", priority="high")
    make_task(store, "h3", status="in_progress", priority="high")
    make_task(store, "h4", status="in_progress", priority="high")

    code, stdout, _ = run_stats(store)
    assert code == 0
    assert "🔥 高优先级任务：4（⏳ pending: 2 / ▶ in_progress: 2）" in stdout


def test_stats_no_high_priority_line_when_no_active_high(store):
    """No 🔥 line when high-priority tasks are all archived/blocked/etc."""
    make_task(store, "h-blocked", status="blocked", priority="high")
    make_task(
        store, "h-archived", status="archived", priority="high",
        archived=True, archive_date="20260101",
    )
    make_task(store, "low", status="pending", priority="low")

    code, stdout, _ = run_stats(store)
    assert code == 0
    assert "🔥 高优先级任务" not in stdout


# ============================================================
#  Scenario 6: unknown frontmatter fields
# ============================================================


def test_stats_unknown_fields_do_not_affect_counts(store):
    """BDD §stats 6: extra fields land in Task.extra, never double-count."""
    make_task(
        store, "kemu1",
        status="pending", priority="high", deadline="2026-08-31",
        extra={"description": "自由描述", "paused_at": "2026-06-13", "pause_reason": "..."},
    )
    make_task(
        store, "weird",
        status="in_progress", priority="medium",
        extra={"custom_field": "x", "another": [1, 2, 3]},
    )

    code, stdout, _ = run_stats(store)
    assert code == 0
    assert "总任务数：2" in stdout
    assert "⏳ pending：1" in stdout
    assert "▶ in_progress：1" in stdout
    # Stats don't contain the unknown field names
    assert "description" not in stdout
    assert "paused_at" not in stdout
    assert "custom_field" not in stdout


# ============================================================
#  Scenario 7: broken YAML
# ============================================================


def test_stats_broken_yaml_reports_error_and_exits_5(store):
    """BDD §stats 7: broken TODO.md → exit code 5 + error report + best-effort stats."""
    # One good task
    make_task(store, "good", status="pending", priority="high")
    # One broken task (active)
    bad = store.active_dir / "科目一"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / "TODO.md").write_text(
        "no frontmatter at all, just plain text",
        encoding="utf-8",
    )
    # One broken task (archived)
    bad_arch = store.archive_dir / "20260101-bad"
    bad_arch.mkdir(parents=True, exist_ok=True)
    (bad_arch / "TODO.md").write_text(
        "no frontmatter at all\nplain text only\n",
        encoding="utf-8",
    )

    code, stdout, stderr = run_stats(store)
    assert code == 5
    # Error report goes to stderr with the relative path
    assert "❌ 解析任务失败" in stderr
    assert "任务/科目一" in stderr
    assert "归档/20260101-bad" in stderr
    # Best-effort stats: the 1 good task is still counted
    assert "总任务数：1" in stdout
    assert "⏳ pending：1" in stdout


def test_stats_no_broken_yaml_returns_zero(store):
    """Sanity: with no broken files, exit code stays 0."""
    make_task(store, "good", status="pending", priority="high")
    code, _, stderr = run_stats(store)
    assert code == 0
    assert stderr == ""


# ============================================================
#  Regression: legacy archive tasks with stale frontmatter status
# ============================================================


def _write_raw_task(
    store: TaskStore,
    *,
    folder_rel: str,
    name: str,
    status: str,
    priority: str = "high",
) -> None:
    """Drop a raw TODO.md with a custom ``folder:`` line (no Task model).

    Used to reproduce the real-world data drift where an archived task
    was moved on disk but its frontmatter ``status:`` line was never
    updated from ``in_progress`` (e.g. legacy archive entries in the
    real ``~/.xavier/TODO/归档/``).
    """
    folder = store.todo_dir / folder_rel
    folder.mkdir(parents=True, exist_ok=True)
    text = (
        "---\n"
        f"id: {name}\n"
        f"name: {name}\n"
        f"status: {status}\n"
        f"priority: {priority}\n"
        f"folder: {folder_rel}\n"
        "---\n"
    )
    (folder / "TODO.md").write_text(text, encoding="utf-8")


def test_stats_legacy_archive_with_stale_in_progress_counts_as_archived(store):
    """Regression for the attempt-3 bug.

    Two files live physically under ``归档/`` but their frontmatter
    still says ``status: in_progress`` (the file was moved on disk but
    the status line never got bumped — this matches two real legacy
    entries in ``~/.xavier/TODO/归档/``). Stats must trust the folder
    location and count them as archived.
    """
    # 4 active tasks that look like the real TODO.md inventory
    _write_raw_task(
        store, folder_rel="任务/zhuxuejin", name="助学金",
        status="in_progress",
    )
    _write_raw_task(
        store, folder_rel="任务/zizhushixi", name="自主实习",
        status="in_progress",
    )
    _write_raw_task(
        store, folder_rel="任务/kemu1", name="科目一", status="pending",
    )
    _write_raw_task(
        store, folder_rel="任务/zimeiti", name="自媒体", status="pending",
    )

    # 2 legacy archived tasks with stale status: in_progress
    _write_raw_task(
        store,
        folder_rel="归档/20260605-jiuye-tuijian-biao",
        name="就业推荐表",
        status="in_progress",
    )
    _write_raw_task(
        store,
        folder_rel="归档/20260615-laodong-jiaoyu-iii",
        name="劳动教育III",
        status="in_progress",
    )

    # Plus 28 cleanly-archived tasks to mirror the real inventory
    for i in range(28):
        _write_raw_task(
            store,
            folder_rel=f"归档/20260101-clean-{i}",
            name=f"clean-{i}",
            status="archived",
            priority="medium",
        )

    s = store.stats(today="2026-06-21")
    # The bug: stats used to count 4 in_progress and 28 archived; with
    # the fix it must count 2 in_progress and 30 archived.
    assert s["by_status"]["in_progress"] == 2, (
        f"legacy archive tasks leaked into in_progress: {s['by_status']}"
    )
    assert s["by_status"]["archived"] == 30, (
        f"legacy archive tasks not counted as archived: {s['by_status']}"
    )
    assert s["by_status"]["pending"] == 2
    assert s["by_status"]["blocked"] == 0
    assert s["by_status"]["waiting"] == 0
    assert s["total"] == 34
    # priority sum must equal total (no double-counting)
    psum = s["by_priority"]["high"] + s["by_priority"]["medium"] + s["by_priority"]["low"]
    assert psum == s["total"], (
        f"priority sum {psum} != total {s['total']}: {s['by_priority']}"
    )

    # And the command output must reflect these counts.
    code, stdout, _ = run_stats(store)
    assert code == 0
    assert "⏳ pending：2" in stdout
    assert "▶ in_progress：2" in stdout
    assert "✅ archived：30" in stdout


def test_list_with_all_archived_tasks_show_archived_status(store):
    """``x todo list --all`` must show legacy archive tasks as ``archived``.

    Same data-drift scenario as the stats regression test, but here we
    check that the user-facing list command also treats the folder as
    the source of truth for the Status column.
    """
    _write_raw_task(
        store, folder_rel="任务/kemu1", name="科目一", status="pending",
    )
    _write_raw_task(
        store,
        folder_rel="归档/20260615-laodong-jiaoyu-iii",
        name="劳动教育III",
        status="in_progress",  # stale — should still show as archived
    )

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        from x import _todo_list
        import argparse

        args = argparse.Namespace(
            status=None, priority=None, tag=None, include_archived=True,
        )
        code = _todo_list(args)
    assert code == 0
    rendered = out.getvalue()
    # The archived row must show archived, not the stale in_progress
    assert "archived" in rendered
    # The stale 'in_progress' label must NOT appear in the row for 劳动教育III
    for line in rendered.splitlines():
        if "劳动教育III" in line:
            assert "in_progress" not in line, (
                f"legacy archive task should show as 'archived' not "
                f"'{line}': {rendered!r}"
            )


def test_update_legacy_archived_task_is_blocked(store):
    """Updating a legacy archive task must fail with the 'already archived'
    error, not silently succeed and write into ``任务/``.

    This guards against the same data-drift scenario: if a user runs
    ``x todo update <id> --priority low`` on a task whose file lives
    under ``归档/`` but whose frontmatter says ``status: in_progress``,
    the CLI must treat it as archived (folder wins).
    """
    _write_raw_task(
        store,
        folder_rel="归档/20260615-laodong-jiaoyu-iii",
        name="劳动教育III",
        status="in_progress",  # stale
    )

    from x import _todo_update
    import argparse

    args = argparse.Namespace(
        id="劳动教育III",
        status=None,
        priority="low",
        deadline=None,
        tags=None,
        time=None,        # v0.5 Phase A
        end_time=None,    # v0.5 Phase A
        duration=None,    # v0.5 Phase A
        parent=None,      # v0.5 Phase B
    )
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = _todo_update(args)
    assert code == 4, (
        f"expected exit 4 (already archived), got {code}: {err.getvalue()!r}"
    )
    assert "已归档" in err.getvalue()


def test_main_dispatches_todo_stats(monkeypatch, tmp_path):
    """`x todo stats` runs through the main entry point."""
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
    # Empty repo so output is deterministic
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(["todo", "stats"])
    assert code == 0
    assert "📊" in out.getvalue()
    assert "总任务数：0" in out.getvalue()
    assert err.getvalue() == ""


def test_main_todo_stats_unknown_flag_errors(monkeypatch, tmp_path):
    """`x todo stats --something` is an argparse usage error (exit 2)."""
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
    with pytest.raises(SystemExit) as exc_info:
        main(["todo", "stats", "--bogus"])
    assert exc_info.value.code == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))