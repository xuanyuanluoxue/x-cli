"""E2E subprocess tests for ``x todo`` commands.

These tests launch the installed ``x`` script as a **separate process**
(via ``subprocess.run``) and assert on the real exit code / stdout /
stderr a user would see in PowerShell. They complement the in-process
tests in ``tests/test_todo_*.py`` by catching issues that only show up
in the actual entry point:

* ``pyproject.toml`` script entry wiring (``[project.scripts] x = "x:main"``)
* ``XAVIER_TODO_DIR`` env-var routing through ``core.storage``
* The full ``x`` -> ``x.main`` -> ``SUBCOMMAND_HANDLERS`` chain
* Setuptools-generated ``x.exe`` wrapper on Windows

Each test maps to a scenario in ``docs/behaviors/e2e-cli-behavior.md``.

Environment
-----------
System ``python`` on this machine is polluted with ``hydra-core`` which
imports ``antlr4`` at pytest collection time and breaks ``pytest`` on
Python 3.14. The tests therefore assume the project-local venv at
``.venv/`` exists and is used to run pytest. To set it up::

    py -3.14 -m venv .venv
    .venv/Scripts/python.exe -m pip install -e ".[dev]"
    .venv/Scripts/python.exe -m pytest tests/test_e2e_todo.py
"""

from __future__ import annotations

import os
import subprocess
import sysconfig
from datetime import date
from pathlib import Path
from typing import Sequence

import pytest

from core.models import ArchiveReason, Priority, Task, TaskStatus


# ============================================================
#  Fixtures and helpers
# ============================================================


def _x_executable() -> str:
    """Return the absolute path to the installed ``x`` script.

    setuptools-generated entry point lives in the venv's ``scripts/``
    directory. On Windows this is ``x.exe``; on POSIX it is ``x``.
    """
    scripts_dir = Path(sysconfig.get_path("scripts"))
    name = "x.exe" if os.name == "nt" else "x"
    return str(scripts_dir / name)


def _make_task(
    name: str,
    *,
    status: TaskStatus = TaskStatus.PENDING,
    priority: Priority = Priority.MEDIUM,
    deadline: str | None = None,
    tags: list[str] | None = None,
    reason: ArchiveReason | None = None,
) -> Task:
    """Build a :class:`Task` model for use as a fixture.

    Mirrors the helper pattern used by ``tests/test_todo_list.py`` so
    the on-disk TODO.md format stays in sync with the real production
    serializer (:meth:`core.models.Task.to_markdown`).
    """
    return Task(
        id=name,
        name=name,
        status=status,
        priority=priority,
        deadline=deadline,
        tags=list(tags) if tags else None,
        reason=reason,
        folder=f"任务/{name}",
        created=date.today().isoformat(),
    )


@pytest.fixture
def todo_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Empty TODO root; tests fill it in as needed."""
    monkeypatch.setenv("XAVIER_TODO_DIR", str(tmp_path))
    (tmp_path / "任务").mkdir()
    (tmp_path / "归档").mkdir()
    return tmp_path


@pytest.fixture
def x_path() -> str:
    """Absolute path to the installed ``x`` script (skip if missing)."""
    p = _x_executable()
    if not Path(p).exists():
        pytest.skip(f"x not installed at {p}; run `pip install -e .` in venv")
    return p


def _run_x(
    x_path: str,
    args: Sequence[str],
    todo_dir: Path,
    *,
    timeout: float = 30.0,
) -> tuple[int, str, str]:
    """Run ``x <args>`` as a subprocess with XAVIER_TODO_DIR=todo_dir.

    Returns ``(returncode, stdout, stderr)`` decoded as UTF-8.
    """
    env = os.environ.copy()
    env["XAVIER_TODO_DIR"] = str(todo_dir)
    proc = subprocess.run(
        [x_path, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _seed_task(
    todo_dir: Path,
    *,
    name: str,
    task: Task,
    archive: bool = False,
) -> None:
    """Drop a Task's TODO.md into 任务/<name>/ or 归档/<name>/."""
    root = todo_dir / ("归档" if archive else "任务")
    (root / name).mkdir(parents=True, exist_ok=True)
    (root / name / "TODO.md").write_text(task.to_markdown(), encoding="utf-8")


# ============================================================
#  Scenario 1: x todo list (no args)
# ============================================================


def test_e2e_list_no_args_shows_table(x_path: str, todo_dir: Path):
    """Scenario 1: list with no flags shows active tasks as a table."""
    _seed_task(
        todo_dir,
        name="科目一模拟考",
        task=_make_task(
            "科目一模拟考",
            status=TaskStatus.PENDING,
            priority=Priority.HIGH,
            deadline="2026-08-31",
        ),
    )
    code, out, err = _run_x(x_path, ["todo", "list"], todo_dir)
    assert code == 0, f"stderr={err!r}"
    assert err == "", f"unexpected stderr: {err!r}"
    lines = out.rstrip("\n").splitlines()
    # header + separator + 1 data row
    assert len(lines) == 3, f"expected 3 lines, got {lines!r}"
    assert "ID" in lines[0] and "Name" in lines[0]
    assert "─" in lines[1]  # separator line
    assert "科目一模拟考" in lines[2]
    assert "pending" in lines[2]
    assert "high" in lines[2]
    assert "2026-08-31" in lines[2]


def test_e2e_list_empty_repo_prints_mailbox(x_path: str, todo_dir: Path):
    """Empty store prints the empty-state message and exits 0."""
    code, out, _ = _run_x(x_path, ["todo", "list"], todo_dir)
    assert code == 0
    assert "没有任务" in out or "📭" in out


# ============================================================
#  Visualization scenarios: CJK alignment + status/priority icons
# ============================================================


def _display_width(s: str) -> int:
    """Approximate monospace display width of ``s`` for alignment tests.

    Mirrors the implementation in x.py: ASCII / Halfwidth = 1, CJK /
    Fullwidth / emoji = 2. Control characters (\t, \n) are treated as 0.
    """
    import unicodedata

    width = 0
    for ch in s:
        if ch in ("\t", "\n"):
            continue
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def test_e2e_list_columns_align_under_cjk_mixed(x_path: str, todo_dir: Path):
    """Column boundaries in the rendered table align on display width.

    The header and every data row must end at the same display width
    (so the table looks like a table, not a tab-separated mess).
    """
    _seed_task(
        todo_dir,
        name="科目一模拟考",
        task=_make_task("科目一模拟考", status=TaskStatus.PENDING,
                        priority=Priority.HIGH, deadline="2026-08-31"),
    )
    _seed_task(
        todo_dir,
        name="kemu2",
        task=_make_task("kemu2", status=TaskStatus.IN_PROGRESS,
                        priority=Priority.LOW),
    )
    _, out, _ = _run_x(x_path, ["todo", "list"], todo_dir)
    lines = out.rstrip("\n").splitlines()
    widths = [_display_width(line) for line in lines]
    assert len(widths) >= 2, f"expected header + rows, got {lines!r}"
    assert len(set(widths)) == 1, (
        f"rows have different display widths: {list(zip(lines, widths))}"
    )


def test_e2e_list_shows_status_icons(x_path: str, todo_dir: Path):
    """Each row in the table carries a status icon (⏳/▶/⏸/⌛/✅/🚫/⏰/❌)."""
    _seed_task(todo_dir, name="p",
               task=_make_task("p", status=TaskStatus.PENDING))
    _seed_task(todo_dir, name="ip",
               task=_make_task("ip", status=TaskStatus.IN_PROGRESS))
    _seed_task(todo_dir, name="b",
               task=_make_task("b", status=TaskStatus.BLOCKED))
    _seed_task(todo_dir, name="a",
               task=_make_task("a", status=TaskStatus.ARCHIVED,
                               reason=ArchiveReason.DONE),
               archive=True)

    _, out, _ = _run_x(x_path, ["todo", "list", "--all"], todo_dir)
    for icon in ("⏳", "▶", "⏸", "✅"):
        assert icon in out, f"missing status icon {icon!r} in output:\n{out}"


def test_e2e_list_shows_priority_icons(x_path: str, todo_dir: Path):
    """Each row carries a priority icon (🔥/⚡/🐢)."""
    _seed_task(todo_dir, name="hi",
               task=_make_task("hi", priority=Priority.HIGH))
    _seed_task(todo_dir, name="med",
               task=_make_task("med", priority=Priority.MEDIUM))
    _seed_task(todo_dir, name="lo",
               task=_make_task("lo", priority=Priority.LOW))

    _, out, _ = _run_x(x_path, ["todo", "list"], todo_dir)
    for icon in ("🔥", "⚡", "🐢"):
        assert icon in out, f"missing priority icon {icon!r} in output:\n{out}"


def test_e2e_list_uses_chinese_help_for_stats(x_path: str, todo_dir: Path):
    """`x todo` help output uses Chinese for stats action (not 'stats 命令')."""
    _, out, _ = _run_x(x_path, ["todo"], todo_dir)
    assert "stats 命令" not in out, (
        f"stats help should be Chinese, got:\n{out}"
    )
    assert "统计信息" in out or "统计" in out, (
        f"stats action should have Chinese help text, got:\n{out}"
    )


def test_e2e_stats_uses_status_icons(x_path: str, todo_dir: Path):
    """stats output uses the same status icons as list (⏳/▶/✅)."""
    _seed_task(todo_dir, name="p",
               task=_make_task("p", status=TaskStatus.PENDING,
                               priority=Priority.HIGH))
    _seed_task(todo_dir, name="ip",
               task=_make_task("ip", status=TaskStatus.IN_PROGRESS,
                               priority=Priority.HIGH))
    _seed_task(todo_dir, name="a",
               task=_make_task("a", status=TaskStatus.ARCHIVED,
                               priority=Priority.LOW,
                               reason=ArchiveReason.DONE),
               archive=True)

    _, out, _ = _run_x(x_path, ["todo", "stats"], todo_dir)
    assert "⏳" in out, f"missing ⏳ icon in stats:\n{out}"
    assert "▶" in out, f"missing ▶ icon in stats:\n{out}"
    assert "✅" in out, f"missing ✅ icon in stats:\n{out}"


# ============================================================
#  Scenario 2: add then list
# ============================================================


def test_e2e_add_then_list_round_trip(x_path: str, todo_dir: Path):
    """Scenario 2: add creates folder + TODO.md; subsequent list shows it."""
    code, out, err = _run_x(
        x_path,
        ["todo", "add", "科目一模拟考", "--priority", "high",
         "--deadline", "2026-08-31", "--tags", "驾照,暑假"],
        todo_dir,
    )
    assert code == 0, f"stderr={err!r}"
    assert "✅" in out and "科目一模拟考" in out

    todo_md = todo_dir / "任务" / "科目一模拟考" / "TODO.md"
    assert todo_md.is_file(), f"missing {todo_md}"
    body = todo_md.read_text(encoding="utf-8")
    assert "priority: high" in body
    assert "deadline: 2026-08-31" in body

    code2, out2, _ = _run_x(x_path, ["todo", "list"], todo_dir)
    assert code2 == 0
    assert "科目一模拟考" in out2


# ============================================================
#  Scenarios 3-6: filtering
# ============================================================


def test_e2e_list_filter_by_status(x_path: str, todo_dir: Path):
    """Scenario 3: --status in_progress filters to that status only."""
    _seed_task(todo_dir, name="taskA",
               task=_make_task("taskA", status=TaskStatus.IN_PROGRESS,
                               priority=Priority.HIGH))
    _seed_task(todo_dir, name="taskB",
               task=_make_task("taskB", status=TaskStatus.PENDING,
                               priority=Priority.HIGH))
    _seed_task(todo_dir, name="taskC",
               task=_make_task("taskC", status=TaskStatus.ARCHIVED,
                               priority=Priority.LOW),
               archive=True)

    code, out, _ = _run_x(x_path, ["todo", "list", "--status", "in_progress"],
                          todo_dir)
    assert code == 0
    assert "taskA" in out
    assert "taskB" not in out
    assert "taskC" not in out


def test_e2e_list_filter_by_priority(x_path: str, todo_dir: Path):
    """Scenario 4: --priority high filters to that priority only."""
    _seed_task(todo_dir, name="hi1",
               task=_make_task("hi1", priority=Priority.HIGH))
    _seed_task(todo_dir, name="hi2",
               task=_make_task("hi2", priority=Priority.HIGH))
    _seed_task(todo_dir, name="med",
               task=_make_task("med", priority=Priority.MEDIUM))

    code, out, _ = _run_x(x_path, ["todo", "list", "--priority", "high"],
                          todo_dir)
    assert code == 0
    assert "hi1" in out and "hi2" in out
    assert "med" not in out


def test_e2e_list_filter_by_tag(x_path: str, todo_dir: Path):
    """Scenario 5: --tag matches any tag in the task's tags list."""
    _seed_task(todo_dir, name="驾照任务",
               task=_make_task("驾照任务", tags=["驾照"]))
    _seed_task(todo_dir, name="暑假任务",
               task=_make_task("暑假任务", tags=["暑假"]))

    code, out, _ = _run_x(x_path, ["todo", "list", "--tag", "驾照"], todo_dir)
    assert code == 0
    assert "驾照任务" in out
    assert "暑假任务" not in out


def test_e2e_list_combined_filters_use_and(x_path: str, todo_dir: Path):
    """Scenario 6: status + priority + tag combine as AND."""
    _seed_task(todo_dir, name="A",
               task=_make_task("A", status=TaskStatus.IN_PROGRESS,
                               priority=Priority.HIGH, tags=["驾照"]))
    _seed_task(todo_dir, name="B",
               task=_make_task("B", status=TaskStatus.IN_PROGRESS,
                               priority=Priority.HIGH, tags=["暑假"]))
    _seed_task(todo_dir, name="C",
               task=_make_task("C", status=TaskStatus.PENDING,
                               priority=Priority.HIGH, tags=["驾照"]))

    code, out, _ = _run_x(
        x_path,
        ["todo", "list", "--status", "in_progress",
         "--priority", "high", "--tag", "驾照"],
        todo_dir,
    )
    assert code == 0
    assert "A" in out and "B" not in out and "C" not in out


# ============================================================
#  Scenario 7: --all includes archived
# ============================================================


def test_e2e_list_all_includes_archived(x_path: str, todo_dir: Path):
    """Scenario 7: --all shows archived tasks too, with reason in Status."""
    _seed_task(todo_dir, name="active",
               task=_make_task("active", status=TaskStatus.IN_PROGRESS))
    _seed_task(todo_dir, name="done",
               task=_make_task("done", status=TaskStatus.ARCHIVED,
                               reason=ArchiveReason.DONE),
               archive=True)

    code, out, _ = _run_x(x_path, ["todo", "list", "--all"], todo_dir)
    assert code == 0
    assert "active" in out
    assert "done" in out
    assert "archived" in out


# ============================================================
#  Scenarios 8-11: error / edge cases
# ============================================================


def test_e2e_list_invalid_status_exits_2(x_path: str, todo_dir: Path):
    """Scenario 8: bad --status value -> exit 2 + helpful error."""
    code, _, err = _run_x(
        x_path, ["todo", "list", "--status", "not_a_status"], todo_dir
    )
    assert code == 2
    assert "无效的 status 值" in err
    for v in ("pending", "in_progress", "blocked", "waiting", "archived"):
        assert v in err, f"legal value {v!r} missing from error message"


def test_e2e_add_missing_name_exits_2(x_path: str, todo_dir: Path):
    """Scenario 9: `x todo add` with no positional arg -> argparse exits 2."""
    code, _, err = _run_x(x_path, ["todo", "add"], todo_dir)
    assert code == 2
    assert "required" in err.lower() or "缺少" in err or "用法" in err


def test_e2e_add_duplicate_name_exits_3(x_path: str, todo_dir: Path):
    """Scenario 10: adding an existing task name -> exit 3."""
    _seed_task(todo_dir, name="dup", task=_make_task("dup"))
    code, _, err = _run_x(x_path, ["todo", "add", "dup"], todo_dir)
    assert code == 3
    assert "已存在" in err or "exists" in err.lower()


def test_e2e_add_invalid_priority_exits_2(x_path: str, todo_dir: Path):
    """Scenario 11: bad --priority -> exit 2 with valid-values hint."""
    code, _, err = _run_x(
        x_path, ["todo", "add", "测试", "--priority", "urgent"], todo_dir
    )
    assert code == 2
    assert "无效的 priority 值" in err
    for v in ("high", "medium", "low"):
        assert v in err


# ============================================================
#  Scenarios 12-13: update
# ============================================================


def test_e2e_update_changes_status(x_path: str, todo_dir: Path):
    """Scenario 12: update --status writes to TODO.md and reflects in list."""
    _seed_task(todo_dir, name="kemu1",
               task=_make_task("kemu1", status=TaskStatus.PENDING,
                               priority=Priority.HIGH))

    code, out, err = _run_x(
        x_path, ["todo", "update", "kemu1", "--status", "in_progress"],
        todo_dir,
    )
    assert code == 0, f"stderr={err!r}"
    assert "✅" in out and "kemu1" in out

    body = (todo_dir / "任务" / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    assert "status: in_progress" in body

    _, out2, _ = _run_x(x_path, ["todo", "list"], todo_dir)
    assert "in_progress" in out2


def test_e2e_update_nonexistent_exits_3(x_path: str, todo_dir: Path):
    """Scenario 13: update on missing id -> exit 3."""
    code, _, err = _run_x(
        x_path, ["todo", "update", "nope", "--status", "pending"], todo_dir
    )
    assert code == 3
    assert "不存在" in err


# ============================================================
#  Scenarios 14-16: archive
# ============================================================


def test_e2e_archive_moves_folder_and_marks_status(x_path: str, todo_dir: Path):
    """Scenario 14: archive moves folder to 归档/ and sets reason=done."""
    _seed_task(todo_dir, name="kemu1",
               task=_make_task("kemu1", status=TaskStatus.PENDING,
                               priority=Priority.HIGH))

    code, out, err = _run_x(x_path, ["todo", "archive", "kemu1"], todo_dir)
    assert code == 0, f"stderr={err!r}"
    assert "✅" in out and "归档" in out
    assert "reason=done" in out

    assert not (todo_dir / "任务" / "kemu1").exists()
    archived = list((todo_dir / "归档").iterdir())
    assert len(archived) == 1
    body = (archived[0] / "TODO.md").read_text(encoding="utf-8")
    assert "status: archived" in body
    assert "reason: done" in body

    _, out2, _ = _run_x(x_path, ["todo", "list"], todo_dir)
    assert "kemu1" not in out2


def test_e2e_archive_already_archived_exits_4(x_path: str, todo_dir: Path):
    """Scenario 15: archive twice -> exit 4."""
    _seed_task(todo_dir, name="dup",
               task=_make_task("dup", status=TaskStatus.ARCHIVED,
                               reason=ArchiveReason.DONE),
               archive=True)
    code, _, err = _run_x(x_path, ["todo", "archive", "dup"], todo_dir)
    assert code == 4
    assert "已归档" in err


def test_e2e_archive_invalid_reason_exits_2(x_path: str, todo_dir: Path):
    """Scenario 16: --reason <chinese> -> exit 2."""
    _seed_task(todo_dir, name="task", task=_make_task("task"))
    code, _, err = _run_x(
        x_path, ["todo", "archive", "task", "--reason", "已完成"], todo_dir
    )
    assert code == 2
    assert "无效的 reason 值" in err


# ============================================================
#  Scenario 17: stats
# ============================================================


def test_e2e_stats_prints_summary(x_path: str, todo_dir: Path):
    """Scenario 17: stats prints the formatted summary block."""
    _seed_task(todo_dir, name="p",
               task=_make_task("p", status=TaskStatus.PENDING,
                               priority=Priority.HIGH))
    _seed_task(todo_dir, name="ip",
               task=_make_task("ip", status=TaskStatus.IN_PROGRESS,
                               priority=Priority.HIGH))
    _seed_task(todo_dir, name="a",
               task=_make_task("a", status=TaskStatus.ARCHIVED,
                               priority=Priority.LOW,
                               reason=ArchiveReason.DONE),
               archive=True)

    code, out, err = _run_x(x_path, ["todo", "stats"], todo_dir)
    assert code == 0, f"stderr={err!r}"
    assert "📊" in out
    assert "总任务数：3" in out
    assert "pending" in out and "in_progress" in out and "archived" in out
    assert "🔥" in out


# ============================================================
#  Scenarios 18-21: top-level / help / error paths
# ============================================================


def test_e2e_version_flag(x_path: str, todo_dir: Path):
    """Scenario 18: `x --version` prints the version string."""
    code, out, err = _run_x(x_path, ["--version"], todo_dir)
    assert code == 0
    assert out.strip() == "x 0.2.0", f"got {out!r}"
    assert err == ""


def test_e2e_help_flag(x_path: str, todo_dir: Path):
    """Scenario 19: `x --help` lists subcommands."""
    code, out, _ = _run_x(x_path, ["--help"], todo_dir)
    assert code == 0
    assert "todo" in out


def test_e2e_todo_no_action_shows_help(x_path: str, todo_dir: Path):
    """Scenario 20: `x todo` with no action prints todo help, exits 0."""
    code, out, _ = _run_x(x_path, ["todo"], todo_dir)
    assert code == 0
    for action in ("list", "add", "update", "archive", "stats"):
        assert action in out, f"action {action!r} missing from todo help"


def test_e2e_unknown_subcommand_exits_1(x_path: str, todo_dir: Path):
    """Scenario 21: unknown subcommand -> exit 1 + error to stderr."""
    code, _, err = _run_x(x_path, ["nonexistent"], todo_dir)
    assert code == 1
    assert "未知子命令" in err or "unknown" in err.lower()
    assert "nonexistent" in err
