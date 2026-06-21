"""E2E subprocess tests for ``x todo`` commands.

These tests launch the installed ``x`` script as a **separate process**
(via ``subprocess.run``) and assert on the real exit code / stdout /
stderr a user would see in PowerShell. They complement the in-process
tests in ``tests/test_todo_*.py`` by catching issues that only show up
in the actual entry point:

* ``pyproject.toml`` script entry wiring (``[project.scripts] x = "x:main"``)
* ``XCLI_TODO_DIR`` env-var routing through ``core.storage``
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
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
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
    """Run ``x <args>`` as a subprocess with XCLI_TODO_DIR=todo_dir.

    Returns ``(returncode, stdout, stderr)`` decoded as UTF-8.
    """
    env = os.environ.copy()
    env["XCLI_TODO_DIR"] = str(todo_dir)
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


# ============================================================
#  v0.4.0 — x todo init / import (storage decoupling)
# ============================================================


def test_e2e_init_creates_independent_dir(x_path: str, tmp_path: Path):
    """BDD §todo-init 1: x todo init creates a fresh TODO dir at the requested path."""
    target = tmp_path / "fresh-todo"
    code, out, _ = _run_x(
        x_path, ["todo", "init", "--dir", str(target)], tmp_path
    )
    assert code == 0
    assert (target / "任务").is_dir()
    assert (target / "归档").is_dir()
    assert (target / "README.md").is_file()
    assert "TODO 目录" in out
    assert "💡" in out  # the "try x todo add" hint


def test_e2e_init_is_idempotent(x_path: str, tmp_path: Path):
    """BDD §todo-init 2: running init twice doesn't fail or overwrite README."""
    target = tmp_path / "idempotent"
    _run_x(x_path, ["todo", "init", "--dir", str(target)], tmp_path)
    # User edits README
    (target / "README.md").write_text("# My Custom Note\n", encoding="utf-8")
    # Re-run init
    code, out, _ = _run_x(
        x_path, ["todo", "init", "--dir", str(target)], tmp_path
    )
    assert code == 0
    # README not overwritten
    assert (target / "README.md").read_text(encoding="utf-8") == "# My Custom Note\n"


def test_e2e_import_from_xavier_dir_migrates_tasks(x_path: str, tmp_path: Path):
    """BDD §todo-import 1: copy tasks from a xavier-style dir to x-cli's lib."""
    # Build a fake xavier dir
    src = tmp_path / "xavier-todo"
    (src / "任务").mkdir(parents=True)
    (src / "归档").mkdir(parents=True)
    (src / "任务" / "kemu1").mkdir()
    (src / "任务" / "kemu1" / "TODO.md").write_text(
        "---\nid: kemu1\nname: kemu1\nstatus: pending\npriority: high\n---\n\nbody",
        encoding="utf-8",
    )
    (src / "任务" / "zizhu").mkdir()
    (src / "任务" / "zizhu" / "TODO.md").write_text(
        "---\nid: zizhu\nname: zizhu\nstatus: in_progress\npriority: medium\n---\n\n",
        encoding="utf-8",
    )

    dst = tmp_path / "xcli-todo"
    _run_x(x_path, ["todo", "init", "--dir", str(dst)], tmp_path)

    # Import
    code, out, _ = _run_x(
        x_path,
        ["todo", "import", "--from", str(src), "--to", str(dst)],
        tmp_path,
    )
    assert code == 0
    assert "迁移完成" in out
    assert "2 个" in out  # imported 2

    # Verify both tasks now at destination
    assert (dst / "任务" / "kemu1" / "TODO.md").is_file()
    assert (dst / "任务" / "zizhu" / "TODO.md").is_file()
    # Source untouched
    assert (src / "任务" / "kemu1" / "TODO.md").is_file()


def test_e2e_import_skips_duplicates(x_path: str, tmp_path: Path):
    """BDD §todo-import 2: same name at destination is skipped, not overwritten."""
    src = tmp_path / "src"
    (src / "任务").mkdir(parents=True)
    (src / "任务" / "shared").mkdir()
    (src / "任务" / "shared" / "TODO.md").write_text(
        "---\nid: shared\nname: shared\nstatus: pending\npriority: low\n---\n",
        encoding="utf-8",
    )

    dst = tmp_path / "dst"
    _run_x(x_path, ["todo", "init", "--dir", str(dst)], tmp_path)
    _run_x(x_path, ["todo", "import", "--from", str(src), "--to", str(dst)], tmp_path)

    # User modifies destination
    dest_md = dst / "任务" / "shared" / "TODO.md"
    dest_md.write_text(
        "---\nid: shared\nname: shared\nstatus: done\npriority: high\n---\n",
        encoding="utf-8",
    )

    # Re-import: should NOT overwrite
    code, out, _ = _run_x(
        x_path,
        ["todo", "import", "--from", str(src), "--to", str(dst)],
        tmp_path,
    )
    assert code == 0
    # Status still "done" (user's version preserved)
    assert "status: done" in dest_md.read_text(encoding="utf-8")


def test_e2e_import_source_missing_exits_1(x_path: str, tmp_path: Path):
    """BDD §todo-import 3: nonexistent source dir → exit 1 + clear error."""
    code, _, err = _run_x(
        x_path,
        ["todo", "import", "--from", "/nonexistent/xavier/todo"],
        tmp_path,
    )
    assert code == 1
    assert "源目录不存在" in err or "不存在" in err


def test_e2e_import_dry_run_does_not_write(x_path: str, tmp_path: Path):
    """BDD §todo-import 6: --dry-run reports counts but writes nothing."""
    src = tmp_path / "src"
    (src / "任务").mkdir(parents=True)
    (src / "任务" / "would_be_added").mkdir()
    (src / "任务" / "would_be_added" / "TODO.md").write_text(
        "---\nid: x\nname: x\nstatus: pending\npriority: low\n---\n",
        encoding="utf-8",
    )

    dst = tmp_path / "dst"
    _run_x(x_path, ["todo", "init", "--dir", str(dst)], tmp_path)

    code, out, _ = _run_x(
        x_path,
        ["todo", "import", "--from", str(src), "--to", str(dst), "--dry-run"],
        tmp_path,
    )
    assert code == 0
    assert "dry-run" in out.lower() or "🔍" in out
    # Destination unchanged
    assert not (dst / "任务" / "would_be_added").exists()


def test_e2e_default_path_is_independent_from_xavier(
    x_path: str, tmp_path: Path
):
    """BDD §todo-storage: no env var → default NEVER lands under ~/.xavier/.

    We must use a custom env (not ``_run_x``) because that helper always
    sets ``XCLI_TODO_DIR``. Here we want to test the **default**
    path resolution (no env override).
    """
    import re
    env = os.environ.copy()
    env.pop("XCLI_TODO_DIR", None)

    proc = subprocess.run(
        [x_path, "todo", "init"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=15,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr!r}"

    # Extract the path from output
    m = re.search(r"已[存创]在：(.+)", proc.stdout)
    assert m, f"could not extract path from {proc.stdout!r}"
    default_path = m.group(1).strip()

    # The path must contain 'x-cli' and must NOT contain a '.xavier' segment
    parts = Path(default_path).parts
    assert any(p == "x-cli" for p in parts), (
        f"default TODO path {default_path!r} missing 'x-cli' segment"
    )
    assert ".xavier" not in parts, (
        f"default TODO path {default_path!r} still lands in xavier system"
    )


# ============================================================
#  v0.4.x — x todo restore (归档还原)
# ============================================================


def _seed_archived_task(
    todo_dir: Path,
    *,
    name: str,
    task: Task,
    archive_prefix: str | None = None,
) -> Path:
    """Drop a Task's TODO.md into ``归档/<prefix>-<name>/TODO.md``.

    Returns the folder path. ``archive_prefix`` defaults to today's date
    in ``YYYYMMDD`` form (matching the production ``x todo archive``
    folder-naming convention). Tests that need to seed an older archive
    (e.g. for BDD §场景 7: multiple archives) can pass an explicit
    ``archive_prefix`` like ``"20260521"``.
    """
    prefix = archive_prefix or date.today().strftime("%Y%m%d")
    folder = todo_dir / "归档" / f"{prefix}-{name}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "TODO.md").write_text(task.to_markdown(), encoding="utf-8")
    return folder


def test_e2e_restore_basic_round_trip(x_path: str, todo_dir: Path):
    """BDD §todo-restore 1: archive then restore, content survives.

    After ``x todo restore kemu1`` the task must be back under
    ``任务/kemu1/TODO.md`` with ``status: pending`` and ``reason`` removed.
    The original ``归档/...`` folder stays (audit trail) and the task
    shows up in ``x todo list`` again.
    """
    _seed_archived_task(
        todo_dir,
        name="kemu1",
        task=_make_task(
            "kemu1",
            status=TaskStatus.ARCHIVED,
            priority=Priority.HIGH,
            deadline="2026-08-31",
            reason=ArchiveReason.DONE,
        ),
    )

    code, out, err = _run_x(x_path, ["todo", "restore", "kemu1"], todo_dir)
    assert code == 0, f"stderr={err!r}"
    assert "✅" in out
    assert "kemu1" in out

    # active task folder exists
    active_md = todo_dir / "任务" / "kemu1" / "TODO.md"
    assert active_md.is_file(), f"missing restored file at {active_md}"
    body = active_md.read_text(encoding="utf-8")
    assert "status: pending" in body
    # reason is removed on restore
    assert "reason: done" not in body

    # list now shows the restored task
    _, out2, _ = _run_x(x_path, ["todo", "list"], todo_dir)
    assert "kemu1" in out2


def test_e2e_restore_via_archive_name(x_path: str, todo_dir: Path):
    """BDD §todo-restore 2B: ``x todo restore YYYYMMDD-<name>`` works.

    When the user passes the full archive folder name (with the date
    prefix), restore must still locate and restore the task. The active
    folder is created under ``任务/<name>`` (date prefix stripped).
    """
    _seed_archived_task(
        todo_dir,
        name="kemu1",
        task=_make_task(
            "kemu1",
            status=TaskStatus.ARCHIVED,
            reason=ArchiveReason.DONE,
        ),
    )
    today_prefix = date.today().strftime("%Y%m%d")
    archive_name = f"{today_prefix}-kemu1"

    code, out, err = _run_x(
        x_path, ["todo", "restore", archive_name], todo_dir
    )
    assert code == 0, f"stderr={err!r}"
    assert "✅" in out
    # Active folder stripped of the date prefix
    assert (todo_dir / "任务" / "kemu1" / "TODO.md").is_file()
    # Source archive preserved
    assert (todo_dir / "归档" / archive_name / "TODO.md").is_file()


def test_e2e_restore_active_conflict_exits_3(x_path: str, todo_dir: Path):
    """BDD §todo-restore 2C + 8: active folder with same name → exit 3.

    If a task is already active AND a same-named archive exists, the
    user must disambiguate (e.g. use the full archive name). Restoring
    the bare name must NOT silently overwrite the active copy.
    """
    _seed_task(
        todo_dir,
        name="kemu1",
        task=_make_task("kemu1", status=TaskStatus.PENDING,
                        priority=Priority.HIGH),
    )
    _seed_archived_task(
        todo_dir,
        name="kemu1",
        task=_make_task(
            "kemu1",
            status=TaskStatus.ARCHIVED,
            reason=ArchiveReason.DONE,
        ),
    )

    code, _, err = _run_x(x_path, ["todo", "restore", "kemu1"], todo_dir)
    assert code == 3
    assert "已存在" in err or "kemu1" in err
    # Active file untouched (still status: pending, no reason)
    body = (todo_dir / "任务" / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    assert "status: pending" in body
    assert "reason" not in body


def test_e2e_restore_nonexistent_exits_3(x_path: str, todo_dir: Path):
    """BDD §todo-restore 3: missing task id → exit 3."""
    code, _, err = _run_x(
        x_path, ["todo", "restore", "nonexistent"], todo_dir
    )
    assert code == 3
    assert "不存在" in err
    assert "nonexistent" in err


def test_e2e_restore_active_task_exits_4(x_path: str, todo_dir: Path):
    """BDD §todo-restore 4: task exists but is not archived → exit 4.

    An active task cannot be "restored" — it's already there. The
    handler should refuse and tell the user to use ``x todo update``
    to change status instead.
    """
    _seed_task(
        todo_dir,
        name="kemu1",
        task=_make_task("kemu1", status=TaskStatus.PENDING),
    )

    code, _, err = _run_x(x_path, ["todo", "restore", "kemu1"], todo_dir)
    assert code == 4
    assert "未归档" in err or "已存在" in err or "kemu1" in err


def test_e2e_restore_defaults_to_pending(x_path: str, todo_dir: Path):
    """BDD §todo-restore 5 (revised): restore defaults to pending.

    Implementation choice: archive frontmatter always has ``status:
    archived`` (set during archive), so the loader can't recover the
    pre-archive "last known" status. Restore forces PENDING unless
    ``--status`` overrides. See BDD §5 design-choice box.
    """
    _seed_archived_task(
        todo_dir,
        name="kemu1",
        task=_make_task(
            "kemu1",
            status=TaskStatus.IN_PROGRESS,  # the pre-archive value
            priority=Priority.HIGH,
            reason=ArchiveReason.DONE,
        ),
    )

    code, out, _ = _run_x(x_path, ["todo", "restore", "kemu1"], todo_dir)
    assert code == 0, f"stdout={out!r}"
    body = (todo_dir / "任务" / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    # Forced to pending (NOT in_progress, NOT the original pre-archive value)
    assert "status: pending" in body
    # reason gone
    assert "reason: done" not in body


def test_e2e_restore_broken_yaml_treated_as_not_found(x_path: str, todo_dir: Path):
    """BDD §todo-restore 6 (revised): broken YAML is silently skipped.

    Implementation choice: ``_load_task_from_folder`` returns None for
    unparseable frontmatter, consistent with ``list_tasks`` / ``stats``
    behavior. Restore surfaces as ``TaskNotFoundError`` (exit 3, not 5).
    See BDD §6 design-choice box.
    """
    bad = todo_dir / "归档" / f"{date.today().strftime('%Y%m%d')}-bad"
    bad.mkdir(parents=True)
    (bad / "TODO.md").write_text("not valid frontmatter", encoding="utf-8")

    code, _, err = _run_x(x_path, ["todo", "restore", "bad"], todo_dir)
    # Exit 3 (not found), NOT 5 (data integrity)
    assert code == 3
    assert "不存在" in err
    # No new active file written
    assert not (todo_dir / "任务" / "bad").exists()


def test_e2e_restore_picks_newest_archive(x_path: str, todo_dir: Path):
    """BDD §todo-restore 7: multiple archives → pick newest by date prefix.

    If a task was archived on two different days, restore must
    deterministically pick the latest one (so the user gets the most
    recent state) and leave the older copy as audit history.
    """
    # Newer archive (priority changed → mid-flight revision)
    _seed_archived_task(
        todo_dir,
        name="kemu1",
        task=_make_task(
            "kemu1",
            status=TaskStatus.ARCHIVED,
            priority=Priority.LOW,
            reason=ArchiveReason.DONE,
        ),
        archive_prefix="20260601",
    )
    # Older archive (original high-priority state)
    _seed_archived_task(
        todo_dir,
        name="kemu1",
        task=_make_task(
            "kemu1",
            status=TaskStatus.ARCHIVED,
            priority=Priority.HIGH,
            reason=ArchiveReason.DONE,
        ),
        archive_prefix="20260521",
    )

    code, out, _ = _run_x(x_path, ["todo", "restore", "kemu1"], todo_dir)
    assert code == 0, f"stdout={out!r}"
    # Older archive untouched
    assert (todo_dir / "归档" / "20260521-kemu1" / "TODO.md").is_file()
    # Newer archive untouched too
    assert (todo_dir / "归档" / "20260601-kemu1" / "TODO.md").is_file()
    # Active folder was created and contains the NEWER archive's content
    body = (todo_dir / "任务" / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    assert "priority: low" in body


def test_e2e_restore_with_status_override(x_path: str, todo_dir: Path):
    """BDD §todo-restore 9: ``--status`` overrides archived status.

    The ``--status`` flag lets the user explicitly choose the
    post-restore status. Other fields (priority, deadline) are kept
    from the archive.
    """
    _seed_archived_task(
        todo_dir,
        name="kemu1",
        task=_make_task(
            "kemu1",
            status=TaskStatus.IN_PROGRESS,  # original last status
            priority=Priority.HIGH,
            deadline="2026-08-31",
            reason=ArchiveReason.DONE,
        ),
    )

    code, out, _ = _run_x(
        x_path, ["todo", "restore", "kemu1", "--status", "in_progress"],
        todo_dir,
    )
    assert code == 0, f"stdout={out!r}"
    body = (todo_dir / "任务" / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    # status explicitly forced to in_progress
    assert "status: in_progress" in body
    # priority preserved
    assert "priority: high" in body
    # deadline preserved
    assert "deadline: 2026-08-31" in body


def test_e2e_restore_dry_run_does_not_write(x_path: str, todo_dir: Path):
    """BDD §todo-restore 10: ``--dry-run`` reports but never writes.

    A dry-run must leave both the archive and (absence of) active
    folder untouched. Output indicates "would restore" semantics.
    """
    _seed_archived_task(
        todo_dir,
        name="kemu1",
        task=_make_task(
            "kemu1",
            status=TaskStatus.ARCHIVED,
            priority=Priority.HIGH,
            reason=ArchiveReason.DONE,
        ),
    )

    code, out, _ = _run_x(
        x_path, ["todo", "restore", "kemu1", "--dry-run"], todo_dir
    )
    assert code == 0
    assert "🔍" in out or "dry-run" in out.lower()
    # No active folder created
    assert not (todo_dir / "任务" / "kemu1").exists()
    # Archive untouched
    assert (todo_dir / "归档" / f"{date.today().strftime('%Y%m%d')}-kemu1").is_dir()


# ============================================================
#  v0.4.x — x todo search (跨字段关键词搜索)
# ============================================================


def _write_raw_todo(
    todo_dir: Path,
    *,
    name: str,
    frontmatter: str,
    body: str = "",
    archive: bool = False,
) -> Path:
    """Write a hand-crafted TODO.md (used to inject fields like ``note``)."""
    root = todo_dir / ("归档" if archive else "任务")
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    md = folder / "TODO.md"
    md.write_text(
        f"---\n{frontmatter}\n---\n\n{body}",
        encoding="utf-8",
    )
    return md


def test_e2e_search_matches_name(x_path: str, todo_dir: Path):
    """BDD §todo-search 1: substring match on ``name`` field."""
    _run_x(x_path, ["todo", "add", "kemu1"], todo_dir)
    _run_x(x_path, ["todo", "add", "zijiashixi"], todo_dir)

    code, out, _ = _run_x(x_path, ["todo", "search", "kemu1"], todo_dir)
    assert code == 0
    assert "kemu1" in out
    # No false match
    assert "zijiashixi" not in out


def test_e2e_search_matches_note(x_path: str, todo_dir: Path):
    """BDD §todo-search 2: ``note`` field is part of the search corpus."""
    _write_raw_todo(
        todo_dir,
        name="kemu1",
        frontmatter=(
            "id: kemu1\n"
            "name: 驾驶证考取\n"
            "status: pending\n"
            "priority: high\n"
            "note: 跟朋友 AA 分摊"
        ),
    )

    code, out, _ = _run_x(x_path, ["todo", "search", "AA"], todo_dir)
    assert code == 0
    assert "kemu1" in out or "驾驶证考取" in out


def test_e2e_search_matches_tag(x_path: str, todo_dir: Path):
    """BDD §todo-search 3: tag values are searchable substrings."""
    _run_x(
        x_path,
        ["todo", "add", "kemu1", "--tags", "驾照,暑假"],
        todo_dir,
    )

    code, out, _ = _run_x(x_path, ["todo", "search", "驾照"], todo_dir)
    assert code == 0
    assert "kemu1" in out


def test_e2e_search_is_case_insensitive(x_path: str, todo_dir: Path):
    """BDD §todo-search 4: search is case-insensitive (ASCII)."""
    _run_x(x_path, ["todo", "add", "aliyun"], todo_dir)

    code, out, _ = _run_x(x_path, ["todo", "search", "ALIYUN"], todo_dir)
    assert code == 0
    assert "aliyun" in out


def test_e2e_search_includes_archived_by_default(x_path: str, todo_dir: Path):
    """BDD §todo-search 5: default search spans active + archived.

    The most common pain point is "I archived it but can't find it" —
    so search must include archived results unless the user opts out
    with ``--active-only``.
    """
    _run_x(x_path, ["todo", "add", "kemu1"], todo_dir)
    _run_x(x_path, ["todo", "done", "kemu1"], todo_dir)

    code, out, _ = _run_x(x_path, ["todo", "search", "kemu1"], todo_dir)
    assert code == 0
    # Task appears, with archived indicator
    assert "kemu1" in out
    assert "archived" in out.lower() or "✅" in out


def test_e2e_search_active_only_excludes_archived(x_path: str, todo_dir: Path):
    """BDD §todo-search 6: ``--active-only`` hides archived matches."""
    _run_x(x_path, ["todo", "add", "kemu1"], todo_dir)
    _run_x(x_path, ["todo", "done", "kemu1"], todo_dir)

    code, out, _ = _run_x(
        x_path, ["todo", "search", "kemu1", "--active-only"], todo_dir
    )
    assert code == 0
    # No match → empty result / mail icon
    assert "kemu1" not in out or "📭" in out or "没有匹配" in out


def test_e2e_search_archived_only(x_path: str, todo_dir: Path):
    """BDD §todo-search 7: ``--archived-only`` shows archived matches only."""
    _run_x(x_path, ["todo", "add", "kemu1"], todo_dir)
    # Archive the task
    _run_x(x_path, ["todo", "done", "kemu1"], todo_dir)

    code, out, _ = _run_x(
        x_path, ["todo", "search", "kemu1", "--archived-only"], todo_dir
    )
    assert code == 0
    assert "kemu1" in out
    assert "archived" in out.lower() or "✅" in out


def test_e2e_search_empty_keyword_exits_2(x_path: str, todo_dir: Path):
    """BDD §todo-search 8: empty keyword → exit 2 (defensive).

    An empty keyword would otherwise dump the whole DB, which mirrors
    ``x secret search`` behavior (no surprise data leak).
    """
    code, _, err = _run_x(x_path, ["todo", "search", ""], todo_dir)
    assert code == 2
    assert "不能为空" in err or "required" in err.lower() or "缺少" in err


def test_e2e_search_no_match_exits_0(x_path: str, todo_dir: Path):
    """BDD §todo-search 9: zero matches is exit 0 (not an error)."""
    code, out, _ = _run_x(
        x_path, ["todo", "search", "no_match_xyz"], todo_dir
    )
    assert code == 0
    assert "📭" in out or "没有匹配" in out


def test_e2e_search_combined_with_status(x_path: str, todo_dir: Path):
    """BDD §todo-search 10: search + ``--status`` filter (AND)."""
    _write_raw_todo(
        todo_dir,
        name="A",
        frontmatter="id: A\nname: X-proj-A\nstatus: in_progress\npriority: high",
    )
    _write_raw_todo(
        todo_dir,
        name="B",
        frontmatter="id: B\nname: X-proj-B\nstatus: pending\npriority: high",
    )

    code, out, _ = _run_x(
        x_path,
        ["todo", "search", "X", "--status", "in_progress"],
        todo_dir,
    )
    assert code == 0
    # Only A (pending) shown
    assert "A" in out and "X-proj-A" in out
    assert "B" not in out and "X-proj-B" not in out


def test_e2e_search_fuzzy_multi_char(x_path: str, todo_dir: Path):
    """BDD §todo-search 11: multi-char fuzzy (every char present).

    Search accepts a hit when the keyword is a contiguous substring OR
    every character of the keyword appears in the field. This is a
    pragmatic middle ground between exact-substring and full fuzzy.
    """
    _write_raw_todo(
        todo_dir,
        name="zijin",
        frontmatter="id: zijin\nname: 助学金-下学期材料\nstatus: pending\npriority: medium",
    )

    code, out, _ = _run_x(x_path, ["todo", "search", "助材"], todo_dir)
    assert code == 0
    assert "zijin" in out or "助学金" in out


def test_e2e_search_silently_skips_broken_yaml(x_path: str, todo_dir: Path):
    """BDD §todo-search 12: broken frontmatter is silently skipped.

    A task whose YAML can't parse must not crash the search. The
    valid tasks are returned normally; broken ones are reported via
    ``x todo stats`` (not the search output).
    """
    _write_raw_todo(
        todo_dir,
        name="坏任务",
        frontmatter="this is: not valid: yaml: :::",
    )
    _write_raw_todo(
        todo_dir,
        name="good",
        frontmatter="id: good\nname: goodX\nstatus: pending\npriority: low",
    )

    code, out, _ = _run_x(x_path, ["todo", "search", "goodX"], todo_dir)
    # Search must NOT crash (no exit 5)
    assert code == 0, f"stderr not captured, but exit code was {code}"
    # Valid task surfaces
    assert "good" in out
    # No warning chatter about the broken file
    assert "坏任务" not in out


# ============================================================
#  v0.4.x — x todo done (语义化快捷归档)
# ============================================================


def test_e2e_done_archives_with_reason_done(x_path: str, todo_dir: Path):
    """BDD §todo-done 1: ``x todo done <id>`` archives with reason=done.

    Shortcut for the 80% case. The on-disk result must match
    ``x todo archive <id> --reason done`` byte-for-byte in shape
    (same frontmatter fields, same folder move to 归档/YYYYMMDD-name/).
    """
    _run_x(
        x_path,
        ["todo", "add", "kemu1", "--priority", "high"],
        todo_dir,
    )

    code, out, _ = _run_x(x_path, ["todo", "done", "kemu1"], todo_dir)
    assert code == 0
    assert "✅" in out
    assert "done" in out.lower()

    # Active folder gone, archive folder exists with today's date
    assert not (todo_dir / "任务" / "kemu1").exists()
    archive = todo_dir / "归档" / f"{date.today().strftime('%Y%m%d')}-kemu1"
    assert archive.is_dir(), f"expected archive folder {archive}"
    body = (archive / "TODO.md").read_text(encoding="utf-8")
    assert "status: archived" in body
    assert "reason: done" in body

    # ``list --all`` still shows the task
    _, out2, _ = _run_x(x_path, ["todo", "list", "--all"], todo_dir)
    assert "kemu1" in out2


def test_e2e_done_equivalent_to_archive_reason_done(x_path: str, todo_dir: Path):
    """BDD §todo-done 2: ``done`` and ``archive --reason done`` behave identically.

    The shortcut must be a true alias — same exit code, same on-disk
    state, same frontmatter fields. We compare the two states after
    fresh seeding.
    """
    # First task: archive via --reason done
    _run_x(x_path, ["todo", "add", "taskA", "--priority", "medium"], todo_dir)
    code_a, _, _ = _run_x(
        x_path, ["todo", "archive", "taskA", "--reason", "done"], todo_dir
    )
    assert code_a == 0

    # Second task: via done
    _run_x(x_path, ["todo", "add", "taskB", "--priority", "medium"], todo_dir)
    code_b, _, _ = _run_x(x_path, ["todo", "done", "taskB"], todo_dir)
    assert code_b == 0

    # Both folders exist with same shape
    prefix = date.today().strftime("%Y%m%d")
    body_a = (todo_dir / "归档" / f"{prefix}-taskA" / "TODO.md").read_text(
        encoding="utf-8"
    )
    body_b = (todo_dir / "归档" / f"{prefix}-taskB" / "TODO.md").read_text(
        encoding="utf-8"
    )
    # Both must carry the same archived + done markers
    for marker in ("status: archived", "reason: done"):
        assert marker in body_a, f"archive --reason done missing {marker!r}"
        assert marker in body_b, f"done shortcut missing {marker!r}"


def test_e2e_done_nonexistent_exits_3(x_path: str, todo_dir: Path):
    """BDD §todo-done 3: missing id → exit 3."""
    code, _, err = _run_x(x_path, ["todo", "done", "ghost"], todo_dir)
    assert code == 3
    assert "不存在" in err
    assert "ghost" in err


def test_e2e_done_already_archived_exits_4(x_path: str, todo_dir: Path):
    """BDD §todo-done 4: second done on same id → exit 4.

    Mirrors the archive behavior: once archived, the task is no longer
    an active target. Restoring it (``x todo restore``) is the only way
    to re-target it.
    """
    _run_x(x_path, ["todo", "add", "kemu1"], todo_dir)
    code_first, _, _ = _run_x(x_path, ["todo", "done", "kemu1"], todo_dir)
    assert code_first == 0

    code, _, err = _run_x(x_path, ["todo", "done", "kemu1"], todo_dir)
    assert code == 4
    assert "已归档" in err or "kemu1" in err


def test_e2e_done_in_help_output(x_path: str, todo_dir: Path):
    """BDD §todo-done 5/6: ``done`` is advertised in ``x todo`` help.

    The shortcut only saves typing if users discover it. We verify
    it's listed alongside archive / update etc. in the action table.
    """
    code, out, _ = _run_x(x_path, ["todo"], todo_dir)
    assert code == 0
    assert "done" in out, f"done action missing from help:\n{out}"


def test_e2e_done_does_not_accept_reason_flag(x_path: str, todo_dir: Path):
    """BDD §todo-done 5/不变量: ``done`` has no ``--reason`` flag.

    The shortcut is opinionated — it's *always* ``reason=done``.
    Other reasons require ``x todo archive --reason <X>``. The CLI
    must reject any attempt to pass ``--reason`` to ``done``.
    """
    _run_x(x_path, ["todo", "add", "kemu1"], todo_dir)
    # ``done --reason cancelled`` must fail (argparse unknown flag or
    # handler error). Either way: non-zero exit.
    code, _, _ = _run_x(
        x_path,
        ["todo", "done", "kemu1", "--reason", "cancelled"],
        todo_dir,
    )
    assert code != 0, "done must reject --reason (semantic opinionation)"
