"""Tests for batch operations (v0.5 Phase D).

Each test maps to a scenario in
``docs/behaviors/todo-batch-behavior.md``:

1. done multi-id                                → test_done_multi_id
2. done partial fail (mixed existing + missing) → test_done_partial_fail
3. archive --filter                              → test_archive_filter
4. update --filter                               → test_update_filter
5. update --all on archived task (error)         → test_update_all_archived_blocked
6. remove (recycle bin)                          → test_remove_recycle_bin
7. remove --force                                → test_remove_force_skips_recycle
8. remove multi-id                               → test_remove_multi_id
9. remove --filter                               → test_remove_filter
10. remove nonexistent (error)                   → test_remove_nonexistent
11. remove y/N confirm (skipped per design)      → (not implemented, see docstring)
12. remove parent cascades                       → test_remove_parent_cascades
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


def _invoke_done(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "done", *argv)


def _invoke_archive(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "archive", *argv)


def _invoke_update(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "update", *argv)


def _invoke_remove(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "remove", *argv)


def _id_of(stdout: str) -> str:
    m = re.search(r"ID:\s*(\S+)", stdout)
    assert m is not None, f"no id in stdout: {stdout!r}"
    return m.group(1).rstrip(")）")


def _read_frontmatter(folder: Path) -> dict:
    text = (folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(text)
    return metadata


# ============================================================
#  Scenario 1: done multi-id
# ============================================================


def test_done_multi_id(store: TaskStore) -> None:
    """对应 BDD §场景 1：done 批量多 id。"""
    for n in ("ta", "tb", "tc"):
        rc, _, _ = _invoke_add(n)
        assert rc == 0

    rc, out, stderr = _invoke_done("ta", "tb", "tc")
    assert rc == 0, f"done failed: stderr={stderr!r}"
    # All 3 archived
    for n in ("ta", "tb", "tc"):
        assert not (store.active_dir / n).exists()
    assert len(list(store.archive_dir.iterdir())) == 3


# ============================================================
#  Scenario 2: done partial fail
# ============================================================


def test_done_partial_fail(store: TaskStore) -> None:
    """对应 BDD §场景 2：done 部分 id 不存在。"""
    rc, _, _ = _invoke_add("ta")
    assert rc == 0

    rc, out, stderr = _invoke_done("ta", "t-nope")
    # Per spec: partial success returns non-zero (3 = not found error)
    assert rc != 0
    combined = out + stderr
    # Should mention partial failure
    assert "t-nope" in combined or "未找到" in combined or "不存在" in combined


# ============================================================
#  Scenario 3: archive --filter
# ============================================================


def test_archive_filter(store: TaskStore) -> None:
    """对应 BDD §场景 3：archive --filter 模糊匹配。"""
    _invoke_add("买菜", "--tags", "周末")
    _invoke_add("买衣服", "--tags", "购物")
    _invoke_add("做饭", "--tags", "厨房")

    rc, out, stderr = _invoke_archive("--filter", "买")
    assert rc == 0, f"archive --filter failed: stderr={stderr!r}"

    # Tasks with "买" archived; 做饭 still active
    assert not (store.active_dir / "买菜").exists()
    assert not (store.active_dir / "买衣服").exists()
    assert (store.active_dir / "做饭").exists()


# ============================================================
#  Scenario 4: update --filter
# ============================================================


def test_update_filter(store: TaskStore) -> None:
    """对应 BDD §场景 4：update --filter 批量更新 deadline。"""
    rc, out1, _ = _invoke_add("买菜", "--deadline", "2026-06-01")
    aid = _id_of(out1)
    rc, out2, _ = _invoke_add("买衣服", "--deadline", "2026-06-01")
    bid = _id_of(out2)
    rc, out3, _ = _invoke_add("做饭", "--deadline", "2026-07-01")
    cid = _id_of(out3)

    rc, out, stderr = _invoke_update("--filter", "买", "--deadline", "2026-12-31")
    assert rc == 0, f"update --filter failed: stderr={stderr!r}"

    # A and B updated, C unchanged
    assert _read_frontmatter(store.active_dir / "买菜")["deadline"] == "2026-12-31"
    assert _read_frontmatter(store.active_dir / "买衣服")["deadline"] == "2026-12-31"
    assert _read_frontmatter(store.active_dir / "做饭")["deadline"] == "2026-07-01"


# ============================================================
#  Scenario 5: update --all on archived (error)
# ============================================================


def test_update_all_archived_blocked(store: TaskStore) -> None:
    """对应 BDD §场景 5：update --all 遇到已归档任务报错。"""
    rc, _, _ = _invoke_add("active-task")
    # Archive it manually
    _invoke_archive("active-task", "--reason", "done")

    rc, out, stderr = _invoke_update("--all", "--priority", "low")
    assert rc != 0, f"expected error, got rc={rc}, stderr={stderr!r}"
    combined = out + stderr
    assert "归档" in combined or "archived" in combined.lower()


# ============================================================
#  Scenario 6: remove → recycle bin
# ============================================================


def test_remove_recycle_bin(store: TaskStore) -> None:
    """对应 BDD §场景 6：remove 走回收站。

    注意：v0.5 跨平台回收站实现依赖系统工具（Win ctypes / macOS mv / Linux gio）。
    测试仅验证任务文件夹从 active 消失，不验证回收站内容（环境差异大）。
    """
    rc, _, _ = _invoke_add("trash-task")
    assert rc == 0

    rc, out, stderr = _invoke_remove("trash-task")
    assert rc == 0, f"remove failed: stderr={stderr!r}"
    # Folder no longer in active
    assert not (store.active_dir / "trash-task").exists()


# ============================================================
#  Scenario 7: remove --force
# ============================================================


def test_remove_force_skips_recycle(store: TaskStore) -> None:
    """对应 BDD §场景 7：remove --force 物理删除（不进回收站）。"""
    rc, _, _ = _invoke_add("perm-task")
    assert rc == 0

    rc, out, stderr = _invoke_remove("perm-task", "--force")
    assert rc == 0
    assert "物理删除" in out or "perm-task" in out
    assert not (store.active_dir / "perm-task").exists()


# ============================================================
#  Scenario 8: remove multi-id
# ============================================================


def test_remove_multi_id(store: TaskStore) -> None:
    """对应 BDD §场景 8：remove 批量多 id。"""
    _invoke_add("rm-a")
    _invoke_add("rm-b")

    rc, out, stderr = _invoke_remove("rm-a", "rm-b")
    assert rc == 0, f"remove multi failed: stderr={stderr!r}"
    assert not (store.active_dir / "rm-a").exists()
    assert not (store.active_dir / "rm-b").exists()


# ============================================================
#  Scenario 9: remove --filter
# ============================================================


def test_remove_filter(store: TaskStore) -> None:
    """对应 BDD §场景 9：remove --filter 模糊匹配。"""
    _invoke_add("买菜")
    _invoke_add("买衣服")
    _invoke_add("做饭")

    rc, out, stderr = _invoke_remove("--filter", "买")
    assert rc == 0, f"remove filter failed: stderr={stderr!r}"
    assert not (store.active_dir / "买菜").exists()
    assert not (store.active_dir / "买衣服").exists()
    assert (store.active_dir / "做饭").exists()


# ============================================================
#  Scenario 10: remove nonexistent
# ============================================================


def test_remove_nonexistent(store: TaskStore) -> None:
    rc, out, stderr = _invoke_remove("t-nope")
    assert rc == 3
    combined = out + stderr
    assert "任务不存在" in combined


# ============================================================
#  Scenario 12: remove parent cascades
# ============================================================


def test_remove_parent_cascades(store: TaskStore) -> None:
    """对应 BDD §场景 12：remove 父任务 → 子 + 孙一起进回收站。"""
    rc, s1, _ = _invoke_add("parent-task")
    pid = _id_of(s1)
    rc, s2, _ = _invoke_add("child-task", "--parent", pid)
    cid = _id_of(s2)
    rc, s3, _ = _invoke_add("grand-task", "--parent", cid)
    gid = _id_of(s3)

    rc, out, stderr = _invoke_remove(pid)
    assert rc == 0, f"remove parent failed: stderr={stderr!r}"

    # All 3 should be gone from active
    assert not (store.active_dir / "parent-task").exists()
    assert not (store.active_dir / "child-task").exists()
    assert not (store.active_dir / "grand-task").exists()