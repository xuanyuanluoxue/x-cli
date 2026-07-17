"""Tests for time precision (v0.5 Phase A).

Each test maps to a scenario in
``docs/behaviors/todo-time-precision-behavior.md``:

1. add --time only                              → test_add_time_only
2. add --time + --end-time                      → test_add_time_and_end_time
3. add --time + --duration                      → test_add_time_and_duration
4. add --duration multiple formats              → test_add_duration_formats
5. --end-time vs --duration mutex (error)       → test_end_time_and_duration_mutex
6. --time without --deadline                    → test_time_without_deadline
7. update --time modifies                       → test_update_time_modifies
8. update --time "" clears                      → test_update_empty_time_clears
9. invalid time format (error, 3 cases)         → test_invalid_time_format*
10. invalid duration format (error, 2 cases)    → test_invalid_duration_format*
11. list output Time column (3 tasks)            → test_list_time_column
12. backward compat (v0.4 task no time)          → test_backward_compat_no_time
13. end_time < time (error)                      → test_end_time_earlier_than_time
14. duration_min derives end_time in display     → test_duration_derives_end_time_in_display

All tests use ``XCLI_TODO_DIR`` pointed at ``tmp_path`` so the real
``~/.xavier/TODO`` is never modified (per test_todo_add convention).
"""

from __future__ import annotations

import io
import re
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
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


def _invoke_list(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "list", *argv)


def _read_frontmatter(folder: Path) -> dict:
    text = (folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(text)
    return metadata


def _create_v04_task_manually(
    folder_name: str, *, deadline: str | None = None, priority: str = "medium"
) -> Path:
    """Write a v0.4-style TODO.md with NO time/end_time/duration_min fields.

    Simulates an existing task created before v0.5 to verify backward
    compatibility (per BDD scenario 12).
    """
    root = Path(__import__("os").environ["XCLI_TODO_DIR"])
    folder = root / "任务" / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    lines = ["---"]
    lines.append(f"id: v04-{folder_name}")
    lines.append(f"name: {folder_name}")
    lines.append("status: pending")
    lines.append(f"priority: {priority}")
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
#  Scenario 1: add --time only
# ============================================================


def test_add_time_only(store: TaskStore) -> None:
    """对应 BDD §场景 1：add 带 --time，frontmatter 写入 time 字段。"""
    exit_code, stdout, stderr = _invoke_add(
        "科目一模拟考",
        "--deadline", "2026-08-31",
        "--time", "08:20",
    )

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    assert "✅ 任务已创建" in stdout

    folder = store.active_dir / "科目一模拟考"
    metadata = _read_frontmatter(folder)
    assert metadata["time"] == "08:20", f"time field missing/wrong: {metadata!r}"
    assert metadata["deadline"] == "2026-08-31"


# ============================================================
#  Scenario 2: add --time + --end-time
# ============================================================


def test_add_time_and_end_time(store: TaskStore) -> None:
    """对应 BDD §场景 2：时间段，frontmatter 同时存 time 和 end_time。"""
    exit_code, stdout, stderr = _invoke_add(
        "期末考试",
        "--deadline", "2026-07-03",
        "--time", "08:20",
        "--end-time", "09:50",
    )

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"

    folder = store.active_dir / "期末考试"
    metadata = _read_frontmatter(folder)
    assert metadata["time"] == "08:20"
    assert metadata["end_time"] == "09:50"


# ============================================================
#  Scenario 3: add --time + --duration
# ============================================================


def test_add_time_and_duration(store: TaskStore) -> None:
    """对应 BDD §场景 3：持续时间，存 duration_min（整数分钟）。"""
    exit_code, stdout, stderr = _invoke_add(
        "复习",
        "--deadline", "2026-07-02",
        "--time", "19:00",
        "--duration", "1.5h",
    )

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"

    folder = store.active_dir / "复习"
    metadata = _read_frontmatter(folder)
    assert metadata["time"] == "19:00"
    assert metadata["duration_min"] == 90, (
        f"duration_min should be 90 (1.5h), got {metadata.get('duration_min')!r}"
    )


# ============================================================
#  Scenario 4: --duration multiple formats
# ============================================================


def test_add_duration_formats(store: TaskStore) -> None:
    """对应 BDD §场景 4：90 / 90m / 1.5h / 2h 都正确换算为整数分钟。"""
    cases = [
        ("duration-A", "90", 90),
        ("duration-B", "90m", 90),
        ("duration-C", "1.5h", 90),
        ("duration-D", "2h", 120),
    ]

    for name, raw, expected_min in cases:
        exit_code, _, stderr = _invoke_add(
            name, "--time", "08:00", "--duration", raw,
        )
        assert exit_code == 0, f"{name}: expected 0, got {exit_code}; stderr={stderr!r}"
        folder = store.active_dir / name
        metadata = _read_frontmatter(folder)
        assert metadata["duration_min"] == expected_min, (
            f"{name}: duration {raw!r} should give {expected_min}, "
            f"got {metadata.get('duration_min')!r}"
        )


# ============================================================
#  Scenario 5: --end-time and --duration mutex (error)
# ============================================================


def test_end_time_and_duration_mutex(store: TaskStore) -> None:
    """对应 BDD §场景 5：--end-time 与 --duration 互斥，退出码 2，不创建文件。"""
    exit_code, stdout, stderr = _invoke_add(
        "考试",
        "--deadline", "2026-07-03",
        "--time", "08:20",
        "--end-time", "09:50",
        "--duration", "1.5h",
    )

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    assert "互斥" in stderr or "互斥" in stdout, (
        f"mutex message missing: stderr={stderr!r} stdout={stdout!r}"
    )

    # No folder created
    assert not (store.active_dir / "考试").exists(), (
        "folder should not be created when --end-time and --duration both given"
    )


# ============================================================
#  Scenario 6: --time without --deadline
# ============================================================


def test_time_without_deadline(store: TaskStore) -> None:
    """对应 BDD §场景 6：time 可独立于 deadline 存在。"""
    exit_code, stdout, stderr = _invoke_add(
        "每日站会", "--time", "09:00",
    )

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"

    folder = store.active_dir / "每日站会"
    metadata = _read_frontmatter(folder)
    assert metadata["time"] == "09:00"
    assert "deadline" not in metadata, (
        f"deadline field should NOT exist: {metadata!r}"
    )


# ============================================================
#  Scenario 7: update --time modifies
# ============================================================


def test_update_time_modifies(store: TaskStore) -> None:
    """对应 BDD §场景 7：update --time 修改时间字段。"""
    # Setup: create task with --time 08:20
    _invoke_add("update-time-test", "--time", "08:20")
    folder = store.active_dir / "update-time-test"
    metadata = _read_frontmatter(folder)
    assert metadata["time"] == "08:20"

    # Act: update --time to 09:00
    exit_code, stdout, stderr = _invoke_update(
        metadata["id"], "--time", "09:00",
    )

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    new_metadata = _read_frontmatter(folder)
    assert new_metadata["time"] == "09:00"


# ============================================================
#  Scenario 8: update --time "" clears the field
# ============================================================


def test_update_empty_time_clears(store: TaskStore) -> None:
    """对应 BDD §场景 8：--time "" 显式清除（不是设为空字符串）。"""
    _invoke_add("clear-time-test", "--time", "08:20")
    folder = store.active_dir / "clear-time-test"
    metadata = _read_frontmatter(folder)
    task_id = metadata["id"]

    exit_code, stdout, stderr = _invoke_update(task_id, "--time", "")

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    new_metadata = _read_frontmatter(folder)
    assert "time" not in new_metadata, (
        f"time field should be removed (not empty string): {new_metadata!r}"
    )


# ============================================================
#  Scenario 9: invalid time format (3 error cases)
# ============================================================


def test_invalid_time_format_hour_range(store: TaskStore) -> None:
    """对应 BDD §场景 9 case 1：HH 超出 00-23。"""
    exit_code, stdout, stderr = _invoke_add(
        "test", "--deadline", "2026-08-31", "--time", "25:00",
    )

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "time 格式错误" in combined and "25:00" in combined


def test_invalid_time_format_missing_leading_zero(store: TaskStore) -> None:
    """对应 BDD §场景 9 case 2：缺前导 0。"""
    exit_code, stdout, stderr = _invoke_add(
        "test", "--deadline", "2026-08-31", "--time", "8:20",
    )

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "time 格式错误" in combined


def test_invalid_time_format_non_digits(store: TaskStore) -> None:
    """对应 BDD §场景 9 case 3：非数字。"""
    exit_code, stdout, stderr = _invoke_add(
        "test", "--deadline", "2026-08-31", "--time", "abc",
    )

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "time 格式错误" in combined and "abc" in combined


# ============================================================
#  Scenario 10: invalid duration format (2 error cases)
# ============================================================


def test_invalid_duration_format_garbage(store: TaskStore) -> None:
    """对应 BDD §场景 10 case 1：非数字字符。"""
    exit_code, stdout, stderr = _invoke_add(
        "test", "--time", "08:00", "--duration", "abc",
    )

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "duration 格式错误" in combined and "abc" in combined


def test_invalid_duration_format_negative(store: TaskStore) -> None:
    """对应 BDD §场景 10 case 2：负数。"""
    exit_code, stdout, stderr = _invoke_add(
        "test", "--time", "08:00", "--duration", "-5m",
    )

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "duration" in combined and ("正数" in combined or "positive" in combined)


# ============================================================
#  Scenario 11: list Time column
# ============================================================


def test_list_time_column(store: TaskStore) -> None:
    """对应 BDD §场景 11：list 输出新增 Time 列。"""
    # Setup 3 tasks:
    # A: time + end_time
    _invoke_add(
        "list-A",
        "--deadline", "2026-07-03",
        "--time", "08:20",
        "--end-time", "09:50",
    )
    # B: time + duration
    _invoke_add(
        "list-B",
        "--deadline", "2026-07-02",
        "--time", "19:00",
        "--duration", "1.5h",
    )
    # C: no time (v0.4 style, simulated)
    _create_v04_task_manually("list-C", deadline="2026-07-04")

    exit_code, stdout, stderr = _invoke_list()

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    # Header must include "Time"
    assert "Time" in stdout, f"Time column missing in header: {stdout!r}"

    # Task A: time range display
    assert "08:20-09:50" in stdout, f"task A time range missing: {stdout!r}"
    # Task B: duration derived end_time
    assert "19:00-20:30" in stdout, f"task B derived range missing: {stdout!r}"
    # Task C: shows "-" for no-time
    # (the line for C should have "-" in the Time column;
    #  we just verify no crash and Time column header is present)


# ============================================================
#  Scenario 12: backward compat (v0.4 task with no time fields)
# ============================================================


def test_backward_compat_no_time(store: TaskStore) -> None:
    """对应 BDD §场景 12：v0.4 旧任务无 time 字段，list 正常显示 Time = -。"""
    _create_v04_task_manually("legacy-task", deadline="2026-06-15")

    exit_code, stdout, stderr = _invoke_list()

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    assert "legacy-task" in stdout
    assert "Time" in stdout  # column header present

    # update on legacy task should still work
    exit_code2, _, stderr2 = _invoke_update("v04-legacy-task", "--priority", "high")
    assert exit_code2 == 0, f"update on legacy task failed: {stderr2!r}"


# ============================================================
#  Scenario 13: end_time < time (error)
# ============================================================


def test_end_time_earlier_than_time(store: TaskStore) -> None:
    """对应 BDD §场景 13：end_time 必须 >= time。"""
    exit_code, stdout, stderr = _invoke_add(
        "test",
        "--deadline", "2026-07-03",
        "--time", "10:00",
        "--end-time", "09:00",
    )

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "早于" in combined or "earlier" in combined or "<" in combined
    assert not (store.active_dir / "test").exists()


# ============================================================
#  Scenario 14: duration_min derives end_time in display
# ============================================================


def test_duration_derives_end_time_in_display(store: TaskStore) -> None:
    """对应 BDD §场景 14：list 展示时由 time + duration_min 计算 end_time，不写回 YAML。"""
    _invoke_add(
        "derived-test",
        "--time", "19:00",
        "--duration", "1.5h",
    )
    folder = store.active_dir / "derived-test"
    metadata = _read_frontmatter(folder)
    # YAML should store duration_min, NOT a derived end_time
    assert "duration_min" in metadata
    assert "end_time" not in metadata, (
        f"end_time should NOT be stored when duration_min is given: {metadata!r}"
    )

    exit_code, stdout, stderr = _invoke_list()
    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    assert "19:00-20:30" in stdout