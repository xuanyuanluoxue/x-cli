"""Tests for --template / template subcommand (v0.5 Phase E).

Each test maps to a scenario in
``docs/behaviors/todo-template-behavior.md``.
"""

from __future__ import annotations

import io
import os
import re
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from core.storage import TaskStore
from x import main


@pytest.fixture
def isolated_xcli(monkeypatch, tmp_path: Path):
    r"""Run x with isolated XCLI_TODO_DIR + xcli_data_dir.

    BDD for templates writes to ``<xcli_data_dir>/templates/`` which is
    normally ``%LOCALAPPDATA%\x-cli\templates\``. We override it via
    patching ``core.paths.xcli_data_dir`` so the templates live under tmp.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    todo_dir = tmp_path / "todo"
    todo_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XCLI_TODO_DIR", str(todo_dir))
    monkeypatch.setenv("XCLI_DATA_DIR", str(data_dir))
    from core import paths as paths_mod
    monkeypatch.setattr(
        paths_mod, "xcli_data_dir", lambda *a, **kw: data_dir
    )
    return data_dir, todo_dir


def _run(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            rc = main(args)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 2
    return rc, out.getvalue(), err.getvalue()


def _id_of(stdout: str) -> str:
    m = re.search(r"ID:\s*(\S+)", stdout)
    assert m is not None, f"no id in stdout: {stdout!r}"
    return m.group(1).rstrip(")）")


# ============================================================
#  Scenario 1: template create with steps
# ============================================================


def test_template_create(isolated_xcli) -> None:
    """对应 BDD §场景 1：template create 含 steps。"""
    data_dir, _ = isolated_xcli
    rc, out, stderr = _run(["todo", "template", "create", "退宿流程",
                            "--steps", "清扫宿舍,清点物品,宿管核验"])
    assert rc == 0, f"create failed: stderr={stderr!r}"
    assert "✅" in out and "退宿流程" in out and "3" in out
    template_file = data_dir / "templates" / "退宿流程.yaml"
    assert template_file.exists(), f"template file not created: {template_file}"


# ============================================================
#  Scenario 2: template list
# ============================================================


def test_template_list(isolated_xcli) -> None:
    """对应 BDD §场景 2：template list 展示所有模板。"""
    _run(["todo", "template", "create", "退宿流程",
          "--steps", "A,B"])
    _run(["todo", "template", "create", "出差申请",
          "--steps", "X,Y,Z"])

    rc, out, _ = _run(["todo", "template", "list"])
    assert rc == 0
    assert "退宿流程" in out
    assert "出差申请" in out


# ============================================================
#  Scenario 3: template remove
# ============================================================


def test_template_remove(isolated_xcli) -> None:
    """对应 BDD §场景 3：template remove 删除模板。"""
    data_dir, _ = isolated_xcli
    _run(["todo", "template", "create", "退宿流程", "--steps", "A,B"])
    template_file = data_dir / "templates" / "退宿流程.yaml"
    assert template_file.exists()

    rc, out, _ = _run(["todo", "template", "remove", "退宿流程"])
    assert rc == 0, f"remove failed: {out!r}"
    assert not template_file.exists(), "template file should be gone"


# ============================================================
#  Scenario 4: template remove nonexistent
# ============================================================


def test_template_remove_nonexistent(isolated_xcli) -> None:
    """对应 BDD §场景 4：template remove 不存在的模板。"""
    rc, out, stderr = _run(["todo", "template", "remove", "不存在的模板"])
    assert rc == 3
    combined = out + stderr
    assert "模板不存在" in combined or "不存在" in combined


# ============================================================
#  Scenario 5: template create duplicate
# ============================================================


def test_template_create_duplicate(isolated_xcli) -> None:
    """对应 BDD §场景 5：template create 重名（已存在）。"""
    _run(["todo", "template", "create", "退宿流程", "--steps", "A"])

    rc, out, stderr = _run(["todo", "template", "create", "退宿流程",
                            "--steps", "X,Y"])
    assert rc == 5
    combined = out + stderr
    assert "已存在" in combined or "duplicate" in combined.lower()


# ============================================================
#  Scenario 6: template create empty
# ============================================================


def test_template_create_empty(isolated_xcli) -> None:
    """对应 BDD §场景 6：template create 空 steps。"""
    rc, out, stderr = _run(["todo", "template", "create", "空模板",
                            "--steps", ""])
    assert rc == 2
    combined = out + stderr
    assert "步骤" in combined


# ============================================================
#  Scenario 7: add --template expands to parent + N kids
# ============================================================


def test_add_with_template(isolated_xcli) -> None:
    """对应 BDD §场景 7：add --template 展开为父任务 + 3 个子任务。"""
    _, todo_dir = isolated_xcli
    _run(["todo", "template", "create", "退宿流程",
          "--steps", "清扫宿舍,清点物品,宿管核验"])

    rc, out, err = _run(["todo", "add", "退宿离校",
                         "--template", "退宿流程",
                         "--deadline", "2026-07-13"])
    assert rc == 0, f"add failed: out={out!r} err={err!r}"
    combined = out + err
    assert "4" in combined, f"expected 4 tasks (1 parent + 3 kids): {combined!r}"

    active = todo_dir / "任务"
    assert (active / "退宿离校").exists(), "parent folder missing"
    assert (active / "退宿离校-001").exists(), "child 1 folder missing"
    assert (active / "退宿离校-002").exists(), "child 2 folder missing"
    assert (active / "退宿离校-003").exists(), "child 3 folder missing"


# ============================================================
#  Scenario 8: add --template step name dedup
# ============================================================


def test_add_template_step_dedup(isolated_xcli) -> None:
    """对应 BDD §场景 8：add --template 步骤重名去重。"""
    _, todo_dir = isolated_xcli
    _run(["todo", "template", "create", "检查清单",
          "--steps", "检查,检查,检查"])

    rc, out, _ = _run(["todo", "add", "项目", "--template", "检查清单"])
    assert rc == 0, f"add failed: {out!r}"

    active = todo_dir / "任务"
    # 3 children with deduplicated names
    children = sorted([p.name for p in active.iterdir() if p.name.startswith("项目")])
    # Expect 4 folders total: 项目 + 项目-001/002/003
    assert len(children) == 4, f"expected 4 folders, got {children}"


# ============================================================
#  Scenario 9: add --template nonexistent
# ============================================================


def test_add_template_nonexistent(isolated_xcli) -> None:
    """对应 BDD §场景 9：add --template 不存在的模板。"""
    rc, out, stderr = _run(["todo", "add", "test", "--template", "不存在的模板"])
    assert rc == 3
    combined = out + stderr
    assert "模板不存在" in combined
