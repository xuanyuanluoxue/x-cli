"""Tests for --remind feature (v0.5 Phase C, read-only mode).

Each test maps to a scenario in
``docs/behaviors/todo-remind-behavior.md``:

1. add --remind single value                → test_add_remind_single
2. add --remind multi-value                 → test_add_remind_multi
3. update --remind modifies                 → test_update_remind_modifies
4. update --remind "" clears                → test_update_empty_remind_clears
5. invalid remind format (error, 2 cases)  → test_invalid_remind_format_*
6. reminder list displays tasks            → test_reminder_list_displays
7. reminder clear multi-id                 → test_reminder_clear_multi
8. reminder clear nonexistent (error)      → test_reminder_clear_nonexistent_errors
9. list --reminding filters                 → test_list_reminding_filter
10. stats shows remind count                → test_stats_remind_count
11. backward compat (no remind field)       → test_backward_compat_no_remind
12. --remind "" empty string on add         → test_add_empty_remind_omits_field

v0.5 deliberately does NOT trigger notifications — these tests cover
only the storage / display / filter / stats / clear surface. Daemon
+ system scheduler come in v0.6+ after exe packaging.
"""

from __future__ import annotations

import io
import re
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from core.parser import parse_frontmatter
from core.storage import TaskStore
from x import main


# ============================================================
#  Fixtures / helpers
# ============================================================


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskStore:
    """Root the TaskStore at ``tmp_path``; never touches the real TODO dir."""
    real_todo = Path.home() / ".xavier" / "TODO"
    real_active_before = (
        sorted(p.name for p in (real_todo / "任务").iterdir())
        if (real_todo / "任务").is_dir()
        else []
    )
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
    yield TaskStore()

    real_active_after = (
        sorted(p.name for p in (real_todo / "任务").iterdir())
        if (real_todo / "任务").is_dir()
        else []
    )
    assert real_active_after == real_active_before, (
        f"Test leaked into ~/.xavier/TODO/任务! "
        f"before={real_active_before} after={real_active_after}"
    )


def _invoke(*argv: str) -> tuple[int, str, str]:
    """Call ``main([*argv])`` and capture stdout/stderr."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            exit_code = main(list(argv))
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 2
    return exit_code, out.getvalue(), err.getvalue()


def _invoke_add(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "add", *argv)


def _invoke_update(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "update", *argv)


def _invoke_reminder(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "reminder", *argv)


def _invoke_list(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "list", *argv)


def _invoke_stats() -> tuple[int, str, str]:
    return _invoke("todo", "stats")


def _read_frontmatter(folder: Path) -> dict:
    text = (folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(text)
    return metadata


def _id_of(stdout: str) -> str:
    """Extract the task id from ``...（ID: <id>）`` line."""
    m = re.search(r"ID:\s*(\S+)", stdout)
    assert m is not None, f"no id in stdout: {stdout!r}"
    return m.group(1).rstrip(")）")


def _create_v04_task_manually(folder_name: str, *, deadline: str | None = None) -> Path:
    """Write a v0.4-style TODO.md without ``remind`` field.

    Simulates an existing task created before v0.5 to verify backward
    compatibility (per BDD scenario 11).
    """
    import os
    from datetime import date

    root = Path(os.environ["XCLI_TODO_DIR"])
    folder = root / "任务" / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    lines = ["---"]
    lines.append(f"id: v04-{folder_name}")
    lines.append(f"name: {folder_name}")
    lines.append("status: pending")
    lines.append("priority: medium")
    lines.append(f"created: {today}")
    lines.append(f"updated: {today}")
    if deadline:
        lines.append(f"deadline: {deadline}")
    lines.append(f"folder: 任务/{folder_name}")
    lines.append("---")
    lines.append("")
    (folder / "TODO.md").write_text("\n".join(lines), encoding="utf-8")
    return folder


# ============================================================
#  Scenario 1: add --remind single value
# ============================================================


def test_add_remind_single(store: TaskStore) -> None:
    """对应 BDD §场景 1：add --remind 单值。"""
    exit_code, stdout, stderr = _invoke_add(
        "考试",
        "--deadline", "2026-07-03",
        "--time", "08:20",
        "--remind", "1d",
    )

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"

    folder = store.active_dir / "考试"
    metadata = _read_frontmatter(folder)
    assert metadata["remind"] == ["1d"], f"remind field wrong: {metadata!r}"


# ============================================================
#  Scenario 2: add --remind multi-value
# ============================================================


def test_add_remind_multi(store: TaskStore) -> None:
    """对应 BDD §场景 2：add --remind 多值（逗号分隔）。"""
    exit_code, stdout, stderr = _invoke_add(
        "重要会议",
        "--deadline", "2026-07-05",
        "--remind", "1d,2h,30m",
    )

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"

    folder = store.active_dir / "重要会议"
    metadata = _read_frontmatter(folder)
    assert metadata["remind"] == ["1d", "2h", "30m"], f"remind wrong: {metadata!r}"


# ============================================================
#  Scenario 3: update --remind modifies
# ============================================================


def test_update_remind_modifies(store: TaskStore) -> None:
    """对应 BDD §场景 3：update --remind 修改。"""
    exit_code, stdout, _ = _invoke_add(
        "task-A",
        "--deadline", "2026-07-10",
        "--remind", "1d",
    )
    assert exit_code == 0
    task_id = _id_of(stdout)

    exit_code, _, stderr = _invoke_update(task_id, "--remind", "2h,15m")
    assert exit_code == 0, f"update failed: {stderr!r}"

    folder = store.active_dir / "task-A"
    metadata = _read_frontmatter(folder)
    assert metadata["remind"] == ["2h", "15m"], f"remind wrong: {metadata!r}"


# ============================================================
#  Scenario 4: update --remind "" clears
# ============================================================


def test_update_empty_remind_clears(store: TaskStore) -> None:
    """对应 BDD §场景 4：--remind "" 显式清除（不是设为空数组）。"""
    _invoke_add("task-B", "--deadline", "2026-07-11", "--remind", "1d,2h")
    folder = store.active_dir / "task-B"
    task_id = _read_frontmatter(folder)["id"]

    exit_code, _, stderr = _invoke_update(task_id, "--remind", "")
    assert exit_code == 0, f"clear failed: {stderr!r}"

    metadata = _read_frontmatter(folder)
    assert "remind" not in metadata, f"remind should be removed: {metadata!r}"


# ============================================================
#  Scenario 5: invalid remind format
# ============================================================


def test_invalid_remind_format_garbage(store: TaskStore) -> None:
    """对应 BDD §场景 5 case 1：--remind abc（非 Nd/Nh/Nm 格式）。"""
    exit_code, stdout, stderr = _invoke_add("test", "--remind", "abc")

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "remind 格式错误" in combined and "abc" in combined
    assert not (store.active_dir / "test").exists()


def test_invalid_remind_format_negative(store: TaskStore) -> None:
    """对应 BDD §场景 5 case 2：--remind -5m（负数）。"""
    exit_code, stdout, stderr = _invoke_add("test", "--remind", "-5m")

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "remind" in combined and ("正数" in combined or "positive" in combined)


# ============================================================
#  Scenario 6: reminder list displays
# ============================================================


def test_reminder_list_displays(store: TaskStore) -> None:
    """对应 BDD §场景 6：x todo reminder list 只展示有 remind 字段的任务。"""
    # Setup: 2 with remind, 1 without
    _invoke_add("with-remind-1", "--deadline", "2026-07-10", "--remind", "1d")
    _invoke_add("with-remind-2", "--deadline", "2026-07-11", "--remind", "2h,30m")
    _invoke_add("no-remind", "--deadline", "2026-07-12")

    exit_code, stdout, _ = _invoke_reminder("list")

    assert exit_code == 0
    # Tasks with remind appear
    assert "with-remind-1" in stdout
    assert "with-remind-2" in stdout
    # Task without remind does NOT appear
    assert "no-remind" not in stdout
    # Reminders content rendered
    assert "1d" in stdout
    assert "2h, 30m" in stdout or "2h,30m" in stdout


# ============================================================
#  Scenario 7: reminder clear multi-id
# ============================================================


def test_reminder_clear_multi(store: TaskStore) -> None:
    """对应 BDD §场景 7：x todo reminder clear 多 id。"""
    _invoke_add("clear-A", "--deadline", "2026-07-10", "--remind", "1d")
    _invoke_add("clear-B", "--deadline", "2026-07-11", "--remind", "2h")
    _invoke_add("clear-C", "--deadline", "2026-07-12", "--remind", "30m")

    # Get IDs
    _, s_a, _ = _invoke_list()
    # Extract 3 IDs by listing; simpler: read frontmatter
    fa = _read_frontmatter(store.active_dir / "clear-A")["id"]
    fb = _read_frontmatter(store.active_dir / "clear-B")["id"]
    fc = _read_frontmatter(store.active_dir / "clear-C")["id"]

    exit_code, stdout, _ = _invoke_reminder("clear", fa, fb, fc)

    assert exit_code == 0, f"clear failed: stdout={stdout!r}"
    assert "已清除提醒" in stdout

    # All 3 tasks now have no remind field
    for folder in (store.active_dir / "clear-A",
                   store.active_dir / "clear-B",
                   store.active_dir / "clear-C"):
        metadata = _read_frontmatter(folder)
        assert "remind" not in metadata, f"remind should be cleared: {metadata!r}"


# ============================================================
#  Scenario 8: reminder clear nonexistent (error)
# ============================================================


def test_reminder_clear_nonexistent_errors(store: TaskStore) -> None:
    """对应 BDD §场景 8：reminder clear 不存在的任务。"""
    exit_code, stdout, stderr = _invoke_reminder("clear", "t-nope")

    assert exit_code == 3, f"expected 3, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "任务不存在" in combined or "不存在" in combined


# ============================================================
#  Scenario 9: list --reminding filter
# ============================================================


def test_list_reminding_filter(store: TaskStore) -> None:
    """对应 BDD §场景 9：x todo list --reminding 仅显示有 remind 字段的任务。"""
    _invoke_add("filt-A", "--deadline", "2026-07-10", "--remind", "1d")
    _invoke_add("filt-B", "--deadline", "2026-07-11", "--remind", "2h")
    _invoke_add("filt-C", "--deadline", "2026-07-12")  # no remind

    exit_code, stdout, _ = _invoke_list("--reminding")

    assert exit_code == 0
    assert "filt-A" in stdout
    assert "filt-B" in stdout
    assert "filt-C" not in stdout


# ============================================================
#  Scenario 10: stats shows remind count
# ============================================================


def test_stats_remind_count(store: TaskStore) -> None:
    """对应 BDD §场景 10：x todo stats 加 ⏰ 有提醒任务数。"""
    _invoke_add("s-A", "--deadline", "2026-07-10", "--remind", "1d")
    _invoke_add("s-B", "--deadline", "2026-07-11", "--remind", "2h,30m")
    _invoke_add("s-C", "--deadline", "2026-07-12")  # no remind
    _invoke_add("s-D", "--deadline", "2026-07-13")
    _invoke_add("s-E", "--deadline", "2026-07-14")

    exit_code, stdout, _ = _invoke_stats()

    assert exit_code == 0
    # Should mention "2" with a "remind" or similar context
    m = re.search(r"[⏰有提醒]\s*[:：]?\s*(\d+)", stdout) \
        or re.search(r"(\d+)\s*个?.*remind", stdout, re.IGNORECASE)
    # Looser: just check that "2" appears near "提醒" context
    assert "⏰" in stdout or "提醒" in stdout, (
        f"no remind stat line found: {stdout!r}"
    )
    # Extract the number that follows the remind emoji
    m = re.search(r"⏰\s*有提醒[任务数]*[：:]\s*(\d+)", stdout)
    assert m is not None, f"no remind count in stats output: {stdout!r}"
    assert int(m.group(1)) == 2, f"expected 2 reminded tasks, got {m.group(1)}"


# ============================================================
#  Scenario 11: backward compat
# ============================================================


def test_backward_compat_no_remind(store: TaskStore) -> None:
    """对应 BDD §场景 11：v0.4 任务无 remind 字段，reminder list 跳过，update 仍 OK。"""
    _create_v04_task_manually("legacy-task", deadline="2026-06-01")

    exit_code, stdout, _ = _invoke_reminder("list")
    assert exit_code == 0
    assert "legacy-task" not in stdout

    # Update on legacy task still works
    exit_code2, _, stderr2 = _invoke_update("v04-legacy-task", "--priority", "high")
    assert exit_code2 == 0, f"update on legacy failed: {stderr2!r}"


# ============================================================
#  Scenario 12: --remind "" on add omits field
# ============================================================


def test_add_empty_remind_omits_field(store: TaskStore) -> None:
    """对应 BDD §场景 12：add --remind "" 不写入字段（与不传等价）。"""
    exit_code, stdout, stderr = _invoke_add("test-empty", "--remind", "")

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"

    folder = store.active_dir / "test-empty"
    metadata = _read_frontmatter(folder)
    assert "remind" not in metadata, f"remind should NOT be set: {metadata!r}"