"""Tests for --parent subtask feature (v0.5 Phase B).

Each test maps to a scenario in
``docs/behaviors/todo-parent-behavior.md``:

1. add --parent creates child                      → test_add_parent_creates_child
2. add --parent creates grandchild (2-level)       → test_add_parent_creates_grandchild
3. add --parent references non-existent (error)    → test_add_parent_nonexistent_errors
4. add --parent exceeds 2 levels (error)           → test_add_parent_exceeds_depth
5. update --parent sets parent                     → test_update_parent_sets
6. update --parent "" clears parent                → test_update_empty_parent_clears
7. list auto tree view (parent → child → grand)    → test_list_auto_tree_view
8. list --tree explicit                            → test_list_explicit_tree_no_effect
9. archive parent cascades to child + grandchild   → test_archive_parent_cascades
10. archive single child leaves parent active      → test_archive_single_child_only
11. update child doesn't affect parent             → test_update_child_doesnt_affect_parent
12. backward compat (v0.4 task no parent field)    → test_backward_compat_no_parent
13. (cyclic detection: documented, not enforced)   → (skipped)
14. update cannot set parent to descendant         → test_update_parent_to_descendant_errors

All tests use ``XCLI_TODO_DIR`` pointed at ``tmp_path`` so the real
``~/.xavier/TODO`` is never modified.
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


def _invoke_archive(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "archive", *argv)


def _invoke_list(*argv: str) -> tuple[int, str, str]:
    return _invoke("todo", "list", *argv)


def _read_frontmatter(folder: Path) -> dict:
    text = (folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(text)
    return metadata


def _id_of(stdout: str) -> str:
    """Extract the task id from ``...（ID: <id>）`` line."""
    m = re.search(r"ID:\s*(\S+)", stdout)
    assert m is not None, f"no id in stdout: {stdout!r}"
    return m.group(1).rstrip(")）")


# ============================================================
#  Scenario 1: add --parent creates child
# ============================================================


def test_add_parent_creates_child(store: TaskStore) -> None:
    """对应 BDD §场景 1：add --parent 在已有任务下创建子任务。"""
    # Setup: create root task
    exit_code, stdout, _ = _invoke_add("退宿离校")
    assert exit_code == 0
    root_id = _id_of(stdout)

    # Act: create child
    exit_code, stdout, _ = _invoke_add("清扫宿舍", "--parent", root_id)

    assert exit_code == 0, f"add child failed: stdout={stdout!r}"
    assert "✅ 任务已创建" in stdout
    child_id = _id_of(stdout)

    # Verify: child has parent field
    folder = store.active_dir / "清扫宿舍"
    metadata = _read_frontmatter(folder)
    assert metadata["parent"] == root_id
    assert metadata["id"] == child_id


# ============================================================
#  Scenario 2: add --parent creates grandchild (2-level)
# ============================================================


def test_add_parent_creates_grandchild(store: TaskStore) -> None:
    """对应 BDD §场景 2：子任务再有子任务 = 孙任务（2 层深度）。"""
    # Setup: root + child
    _, s1, _ = _invoke_add("退宿离校")
    root_id = _id_of(s1)
    _, s2, _ = _invoke_add("清扫宿舍", "--parent", root_id)
    child_id = _id_of(s2)

    # Act: grandchild
    exit_code, stdout, _ = _invoke_add("擦窗户", "--parent", child_id)

    assert exit_code == 0, f"add grandchild failed: stdout={stdout!r}"

    # Verify: grandchild's parent points to child
    folder = store.active_dir / "擦窗户"
    metadata = _read_frontmatter(folder)
    assert metadata["parent"] == child_id


# ============================================================
#  Scenario 3: add --parent references non-existent
# ============================================================


def test_add_parent_nonexistent_errors(store: TaskStore) -> None:
    """对应 BDD §场景 3：parent 引用不存在的任务 → 退出码 3。"""
    exit_code, stdout, stderr = _invoke_add("子任务", "--parent", "t-nope")

    assert exit_code == 3, f"expected 3, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "父任务不存在" in combined or "不存在" in combined
    assert not (store.active_dir / "子任务").exists()


# ============================================================
#  Scenario 4: add --parent exceeds 2 levels
# ============================================================


def test_add_parent_exceeds_depth(store: TaskStore) -> None:
    """对应 BDD §场景 4：3 层链（root → child → grand → 重孙）报错。"""
    # Setup: root → child → grand
    _, s1, _ = _invoke_add("root-task")
    root_id = _id_of(s1)
    _, s2, _ = _invoke_add("child-task", "--parent", root_id)
    child_id = _id_of(s2)
    _, s3, _ = _invoke_add("grand-task", "--parent", child_id)
    grand_id = _id_of(s3)

    # Act: try to create great-grandchild
    exit_code, stdout, stderr = _invoke_add("gg-grand", "--parent", grand_id)

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "2 层" in combined or "层数" in combined or "深度" in combined
    assert not (store.active_dir / "gg-grand").exists()


# ============================================================
#  Scenario 5: update --parent sets parent
# ============================================================


def test_update_parent_sets(store: TaskStore) -> None:
    """对应 BDD §场景 5：update --parent 关联已有任务。"""
    _, s1, _ = _invoke_add("root")
    _, s2, _ = _invoke_add("orphan")
    root_id = _id_of(s1)
    orphan_id = _id_of(s2)

    exit_code, _, _ = _invoke_update(orphan_id, "--parent", root_id)
    assert exit_code == 0

    folder = store.active_dir / "orphan"
    metadata = _read_frontmatter(folder)
    assert metadata["parent"] == root_id


# ============================================================
#  Scenario 6: update --parent "" clears
# ============================================================


def test_update_empty_parent_clears(store: TaskStore) -> None:
    """对应 BDD §场景 6：--parent "" 显式清除（不是设为空字符串）。"""
    _, s1, _ = _invoke_add("root")
    _, s2, _ = _invoke_add("child", "--parent", _id_of(s1))
    child_id = _id_of(s2)

    exit_code, _, _ = _invoke_update(child_id, "--parent", "")
    assert exit_code == 0

    folder = store.active_dir / "child"
    metadata = _read_frontmatter(folder)
    assert "parent" not in metadata, (
        f"parent should be removed, got: {metadata!r}"
    )


# ============================================================
#  Scenario 7: list auto tree view
# ============================================================


def test_list_auto_tree_view(store: TaskStore) -> None:
    """对应 BDD §场景 7：存在 parent 关系时 list 自动树形展示。"""
    _, s1, _ = _invoke_add("root-task")
    root_id = _id_of(s1)
    _, s2, _ = _invoke_add("child-task", "--parent", root_id)
    child_id = _id_of(s2)
    _, s3, _ = _invoke_add("grand-task", "--parent", child_id)

    exit_code, stdout, _ = _invoke_list()

    assert exit_code == 0
    # root line appears unindented
    assert root_id in stdout
    # child line appears with "└" or "  └" indent (depends on depth)
    assert "└" in stdout or "│" in stdout or "├" in stdout, (
        f"tree indent missing: {stdout!r}"
    )
    # grandchild appears further indented
    lines = stdout.splitlines()
    root_line = next((l for l in lines if root_id in l), None)
    child_line = next((l for l in lines if child_id in l), None)
    assert root_line is not None and child_line is not None
    # child has more leading whitespace than root (tree indent)
    assert len(child_line) - len(child_line.lstrip()) > len(root_line) - len(root_line.lstrip()), (
        f"child not indented deeper than root: root={root_line!r} child={child_line!r}"
    )


# ============================================================
#  Scenario 8: list --tree explicit (no parent relationships)
# ============================================================


def test_list_explicit_tree_no_effect(store: TaskStore) -> None:
    """对应 BDD §场景 8：无 parent 关系时 --tree 不影响输出。"""
    _invoke_add("standalone-A")
    _invoke_add("standalone-B")

    exit_code, stdout, _ = _invoke_list("--tree")
    assert exit_code == 0
    # Both tasks present, no tree symbols (no parent relationship)
    assert "standalone-A" in stdout
    assert "standalone-B" in stdout


# ============================================================
#  Scenario 9: archive parent cascades to all descendants
# ============================================================


def test_archive_parent_cascades(store: TaskStore) -> None:
    """对应 BDD §场景 9：archive 父任务 → 子 + 孙一起归档。"""
    _, s1, _ = _invoke_add("root-task")
    root_id = _id_of(s1)
    _, s2, _ = _invoke_add("child-task", "--parent", root_id)
    child_id = _id_of(s2)
    _, s3, _ = _invoke_add("grand-task", "--parent", child_id)
    grand_id = _id_of(s3)

    exit_code, stdout, _ = _invoke_archive(root_id, "--reason", "done")

    assert exit_code == 0, f"archive failed: stdout={stdout!r}"
    # All three IDs should be referenced in the output (summary)
    combined = stdout
    assert root_id in combined
    assert child_id in combined
    assert grand_id in combined, (
        f"grandchild {grand_id} not in archive output: {stdout!r}"
    )

    # All three folders moved to archive
    assert not (store.active_dir / "root-task").exists()
    assert not (store.active_dir / "child-task").exists()
    assert not (store.active_dir / "grand-task").exists()

    # Archived folders exist
    assert len(list(store.archive_dir.iterdir())) == 3


# ============================================================
#  Scenario 10: archive single child leaves parent active
# ============================================================


def test_archive_single_child_only(store: TaskStore) -> None:
    """对应 BDD §场景 10：只 archive 子任务，父任务保持 active。"""
    _, s1, _ = _invoke_add("parent-task")
    parent_id = _id_of(s1)
    _, s2, _ = _invoke_add("child-task", "--parent", parent_id)
    child_id = _id_of(s2)

    exit_code, stdout, _ = _invoke_archive(child_id, "--reason", "done")

    assert exit_code == 0
    # Child archived
    assert not (store.active_dir / "child-task").exists()
    # Parent still active
    assert (store.active_dir / "parent-task").exists(), (
        "parent should remain active when archiving single child"
    )


# ============================================================
#  Scenario 11: update child doesn't affect parent
# ============================================================


def test_update_child_doesnt_affect_parent(store: TaskStore) -> None:
    """对应 BDD §场景 11：update 子任务不影响父任务任何字段。"""
    _, s1, _ = _invoke_add("parent-task", "--priority", "high")
    parent_id = _id_of(s1)
    _, s2, _ = _invoke_add("child-task", "--parent", parent_id, "--priority", "medium")
    child_id = _id_of(s2)

    exit_code, _, _ = _invoke_update(child_id, "--priority", "low")
    assert exit_code == 0

    # Child priority changed
    child_folder = store.active_dir / "child-task"
    child_metadata = _read_frontmatter(child_folder)
    assert child_metadata["priority"] == "low"

    # Parent priority unchanged
    parent_folder = store.active_dir / "parent-task"
    parent_metadata = _read_frontmatter(parent_folder)
    assert parent_metadata["priority"] == "high", (
        f"parent priority changed unexpectedly: {parent_metadata!r}"
    )


# ============================================================
#  Scenario 12: backward compat (v0.4 task no parent field)
# ============================================================


def test_backward_compat_no_parent(store: TaskStore) -> None:
    """对应 BDD §场景 12：v0.4 旧任务无 parent 字段，list 正常显示为 root。"""
    # Manually write a v0.4-style task without parent
    root = Path(__import__("os").environ["XCLI_TODO_DIR"])
    folder = root / "任务" / "legacy-task"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "TODO.md").write_text(
        "---\nid: v04-legacy\nname: legacy-task\nstatus: pending\n"
        "priority: medium\ncreated: 2026-06-01\nupdated: 2026-06-01\n"
        "folder: 任务/legacy-task\n---\n",
        encoding="utf-8",
    )

    exit_code, stdout, _ = _invoke_list()
    assert exit_code == 0
    assert "legacy-task" in stdout

    # Update still works
    exit_code2, _, stderr2 = _invoke_update("v04-legacy", "--priority", "high")
    assert exit_code2 == 0


# ============================================================
#  Scenario 14: update cannot set parent to descendant
# ============================================================


def test_update_parent_to_descendant_errors(store: TaskStore) -> None:
    """对应 BDD §场景 14：不能把 parent 设为自己的子任务（避免环）。"""
    _, s1, _ = _invoke_add("parent-task")
    parent_id = _id_of(s1)
    _, s2, _ = _invoke_add("child-task", "--parent", parent_id)
    child_id = _id_of(s2)

    # Try to set parent's parent to child (would create cycle)
    exit_code, stdout, stderr = _invoke_update(parent_id, "--parent", child_id)

    assert exit_code == 2, f"expected 2, got {exit_code}; stdout={stdout!r}"
    combined = stdout + stderr
    assert "后代" in combined or "循环" in combined or "环" in combined

    # Parent's parent field should NOT be set
    folder = store.active_dir / "parent-task"
    metadata = _read_frontmatter(folder)
    assert "parent" not in metadata, (
        f"parent's parent should not be set: {metadata!r}"
    )


# ============================================================
#  Regression: cascade must work when --parent uses task NAME
#  (v0.5 Phase D subagent discovered P0 bug)
# ============================================================


def test_archive_cascade_works_with_name_based_parent(store: TaskStore) -> None:
    """子 agent 报告 P0 bug 修复：cascade 必须按 name + id 双向匹配。

    真实用户场景：``x todo add "parent-x"`` 然后 ``x todo add "child-x" --parent parent-x``，
    parent 字段存的是 name "parent-x"（不是自动生成的 id）。
    之前的 find_descendants 只按 id 比较，导致 cascade 漏掉子任务。
    """
    _invoke_add("parent-x")
    _invoke_add("child-x", "--parent", "parent-x")
    _invoke_add("grand-x", "--parent", "child-x")

    # Archive via ID (the most common case)
    folder_p = store.active_dir / "parent-x"
    metadata = _read_frontmatter(folder_p)
    parent_id = metadata["id"]

    rc, out, _ = _invoke_archive(parent_id, "--reason", "done")
    assert rc == 0, f"archive failed: {out!r}"
    assert "已级联归档 3" in out, f"expected 3 tasks cascaded, got: {out!r}"

    # All 3 should be gone from active
    assert not (store.active_dir / "parent-x").exists()
    assert not (store.active_dir / "child-x").exists()
    assert not (store.active_dir / "grand-x").exists()