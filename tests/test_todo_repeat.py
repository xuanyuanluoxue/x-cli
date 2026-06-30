"""Tests for --repeat / repeat-fire (v0.5 Phase D).

Each test maps to a scenario in
``docs/behaviors/todo-repeat-behavior.md``:

1. add --repeat daily                     → test_add_repeat_daily
2. add --repeat weekly                    → test_add_repeat_weekly
3. add --repeat weekdays                  → test_add_repeat_weekdays
4. add --repeat monthly                   → test_add_repeat_monthly
5. add --repeat "<cron>"                  → test_add_repeat_cron
6. invalid cron format (error)            → test_invalid_repeat_cron
7. invalid kind (error)                   → test_invalid_repeat_kind
8. repeat-fire creates new instance       → test_repeat_fire_creates_instance
9. repeat-fire seq increments             → test_repeat_fire_seq_increments
10. repeat-fire on non-repeat task        → test_repeat_fire_no_repeat_field
11. repeat-fire nonexistent (error)        → test_repeat_fire_nonexistent
12. archive done does NOT auto-trigger     → test_archive_does_not_auto_fire
13. 6-field cron rejected                  → test_repeat_6_field_cron_rejected
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


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskStore:
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
    assert real_active_after == real_active_before


def _invoke(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            rc = main(list(argv))
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 2
    return rc, out.getvalue(), err.getvalue()


def _invoke_add(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "add", *argv)


def _invoke_repeat_fire(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "repeat-fire", *argv)


def _invoke_archive(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "archive", *argv)


def _id_of(stdout: str) -> str:
    m = re.search(r"ID:\s*(\S+)", stdout)
    assert m is not None, f"no id in stdout: {stdout!r}"
    return m.group(1).rstrip(")）")


def _read_frontmatter(folder: Path) -> dict:
    text = (folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(text)
    return metadata


# ============================================================
#  Scenario 1: add --repeat daily
# ============================================================


def test_add_repeat_daily(store: TaskStore) -> None:
    """对应 BDD §场景 1：add --repeat daily。"""
    rc, out, stderr = _invoke_add("吃药", "--repeat", "daily")
    assert rc == 0, f"add failed: stderr={stderr!r}"
    folder = store.active_dir / "吃药"
    metadata = _read_frontmatter(folder)
    assert metadata["repeat"] == {"kind": "daily"}


# ============================================================
#  Scenario 2: add --repeat weekly
# ============================================================


def test_add_repeat_weekly(store: TaskStore) -> None:
    rc, out, stderr = _invoke_add("周会", "--repeat", "weekly")
    assert rc == 0, f"add failed: stderr={stderr!r}"
    metadata = _read_frontmatter(store.active_dir / "周会")
    assert metadata["repeat"] == {"kind": "weekly"}


# ============================================================
#  Scenario 3: add --repeat weekdays
# ============================================================


def test_add_repeat_weekdays(store: TaskStore) -> None:
    rc, out, stderr = _invoke_add("打卡", "--repeat", "weekdays")
    assert rc == 0
    metadata = _read_frontmatter(store.active_dir / "打卡")
    assert metadata["repeat"] == {"kind": "weekdays"}


# ============================================================
#  Scenario 4: add --repeat monthly
# ============================================================


def test_add_repeat_monthly(store: TaskStore) -> None:
    rc, out, stderr = _invoke_add("月报", "--repeat", "monthly")
    assert rc == 0
    metadata = _read_frontmatter(store.active_dir / "月报")
    assert metadata["repeat"] == {"kind": "monthly"}


# ============================================================
#  Scenario 5: add --repeat "<cron>" 5-field
# ============================================================


def test_add_repeat_cron(store: TaskStore) -> None:
    rc, out, stderr = _invoke_add("备份", "--repeat", "0 8 * * 1-5")
    assert rc == 0
    metadata = _read_frontmatter(store.active_dir / "备份")
    assert metadata["repeat"] == {"cron": "0 8 * * 1-5"}


# ============================================================
#  Scenario 6: invalid cron
# ============================================================


def test_invalid_repeat_cron(store: TaskStore) -> None:
    rc, out, stderr = _invoke_add("test", "--repeat", "not a cron")
    assert rc == 2
    combined = out + stderr
    assert "repeat 格式错误" in combined
    assert not (store.active_dir / "test").exists()


# ============================================================
#  Scenario 7: invalid kind
# ============================================================


def test_invalid_repeat_kind(store: TaskStore) -> None:
    rc, out, stderr = _invoke_add("test", "--repeat", "yearly")
    assert rc == 2
    combined = out + stderr
    assert "repeat 格式错误" in combined
    assert "yearly" in combined


# ============================================================
#  Scenario 8: repeat-fire creates new instance
# ============================================================


def test_repeat_fire_creates_instance(store: TaskStore) -> None:
    """对应 BDD §场景 8：repeat-fire 显式触发创建新实例。"""
    rc, out, _ = _invoke_add("周会", "--repeat", "weekly")
    assert rc == 0
    task_id = _id_of(out)

    rc, out, stderr = _invoke_repeat_fire(task_id)
    assert rc == 0, f"repeat-fire failed: stderr={stderr!r}"
    assert "已创建下一次实例" in out
    # Extract new id
    m = re.search(r"已创建下一次实例：(\S+)", out)
    assert m is not None, f"no new id in output: {out!r}"
    new_id = m.group(1).rstrip(")）")
    assert new_id == f"{task_id}-001"

    # Both folders exist
    assert (store.active_dir / "周会").is_dir()
    assert (store.active_dir / "周会-001").is_dir()

    # New task inherits repeat
    new_metadata = _read_frontmatter(store.active_dir / "周会-001")
    assert new_metadata["repeat"] == {"kind": "weekly"}


# ============================================================
#  Scenario 9: repeat-fire seq increments
# ============================================================


def test_repeat_fire_seq_increments(store: TaskStore) -> None:
    """对应 BDD §场景 9：seq 自增。"""
    rc, out, _ = _invoke_add("zhihui", "--repeat", "daily")
    task_id = _id_of(out)

    # Create 001, 002, then fire again → should be 003
    _invoke_repeat_fire(task_id)
    _invoke_repeat_fire(task_id)

    rc, out, _ = _invoke_repeat_fire(task_id)
    assert rc == 0
    new_id = re.search(r"已创建下一次实例：(\S+)", out).group(1).rstrip(")）")
    assert new_id == f"{task_id}-003"


# ============================================================
#  Scenario 10: repeat-fire on non-repeat task
# ============================================================


def test_repeat_fire_no_repeat_field(store: TaskStore) -> None:
    rc, out, _ = _invoke_add("once-task")
    task_id = _id_of(out)

    rc, out, stderr = _invoke_repeat_fire(task_id)
    assert rc == 2
    combined = out + stderr
    assert "没有 repeat 字段" in combined


# ============================================================
#  Scenario 11: repeat-fire nonexistent
# ============================================================


def test_repeat_fire_nonexistent(store: TaskStore) -> None:
    rc, out, stderr = _invoke_repeat_fire("t-nope")
    assert rc == 3
    combined = out + stderr
    assert "任务不存在" in combined


# ============================================================
#  Scenario 12: archive does NOT auto-trigger
# ============================================================


def test_archive_does_not_auto_fire(store: TaskStore) -> None:
    """对应 BDD §场景 12：archive 不自动触发 repeat-fire。"""
    rc, out, _ = _invoke_add("zhihui", "--repeat", "daily")
    task_id = _id_of(out)

    # Fire once to create -001
    _invoke_repeat_fire(task_id)
    assert (store.active_dir / "zhihui-001").is_dir()

    # Archive -001
    rc, out, stderr = _invoke_archive(f"{task_id}-001", "--reason", "done")
    assert rc == 0

    # -002 should NOT have been auto-created
    assert not (store.active_dir / "zhihui-002").is_dir(), (
        "archive should NOT auto-fire repeat (v0.5 explicit-only)"
    )


# ============================================================
#  Scenario 13: 6-field cron rejected
# ============================================================


def test_repeat_6_field_cron_rejected(store: TaskStore) -> None:
    rc, out, stderr = _invoke_add("test", "--repeat", "0 0 8 * * *")
    assert rc == 2
    combined = out + stderr
    assert "5 字段" in combined or "6 字段" in combined or "不支持秒" in combined