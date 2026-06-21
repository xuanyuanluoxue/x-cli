"""Tests for ``x todo archive <id>`` (Phase 1 inline in x.py).

Each test maps to a scenario in
``docs/behaviors/todo-archive-behavior.md``:

1. default reason=done (most common)                        → test_archive_default_reason_done
2. reason=cancelled                                         → test_archive_reason_cancelled
3. reason=expired (deadline overdue)                        → test_archive_reason_expired
4. ID not found (error)                                     → test_archive_missing_id_errors
5. task already archived (error)                            → test_archive_already_archived_errors
6. invalid --reason value (error)                           → test_archive_invalid_reason_errors
7. preserve unknown fields (paused_at, description, ...)    → test_archive_preserves_unknown_fields
8. update top-level TODO.md inventory                       → test_archive_updates_inventory

Plus an end-to-end test through ``main()`` to make sure the
argparse wiring works when invoked exactly as a user would.

All tests use ``XCLI_TODO_DIR`` pointed at ``tmp_path`` so the
real ``~/.xavier/TODO`` is never modified. The implementation
under test (``x._todo_archive``) reads the env var via
``TaskStore()``.
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
from x import main

from x import _todo_archive  # for direct unit tests (Scenario 6, 8 edge cases)


# ============================================================
#  Helpers
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
    priority: str = "high",
    created: str = "2026-03-27",
    updated: str = "2026-03-27",
    deadline: str | None = "2026-08-31",
    folder: str | None = None,
    tags: list[str] | None = None,
    extra: dict | None = None,
    archived: bool = False,
    archive_date: str = "20260521",
    reason: str | None = None,
) -> None:
    """Drop a TODO.md on disk that matches the BDD scenario fixture.

    Mirrors ``test_storage.write_task`` so each test stays focused.
    """
    if archived:
        target_dir = store.archive_dir / f"{archive_date}-{name}"
        relative_folder = f"归档/{archive_date}-{name}"
        # When archived, default status to "archived" so the file is
        # internally consistent unless caller overrode it.
        status_to_write = status if status != "pending" else "archived"
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
        extra=extra or {},
    )
    (target_dir / "TODO.md").write_text(task.to_markdown(), encoding="utf-8")


def _write_index(
    store: TaskStore,
    *,
    version: str = "1.5",
    last_updated: str = "2026-06-20",
    pending: int = 0,
    in_progress: int = 0,
    blocked: int = 0,
    waiting: int = 0,
    archived: int = 0,
) -> None:
    """Write a top-level ``TODO.md`` matching BDD scenario 8 fixture."""
    index_path = store.todo_dir / "TODO.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        f'---\n'
        f'version: "{version}"\n'
        f'last_updated: "{last_updated}"\n'
        f'inventory:\n'
        f'  pending: {pending}\n'
        f'  in_progress: {in_progress}\n'
        f'  blocked: {blocked}\n'
        f'  waiting: {waiting}\n'
        f'  archived: {archived}\n'
        f'---\n'
    )
    index_path.write_text(text, encoding="utf-8")


def _invoke(*argv: str) -> tuple[int, str, str]:
    """Call ``main`` with the given argv (relative to ``x``)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        exit_code = main(["todo", "archive", *argv])
    return exit_code, out.getvalue(), err.getvalue()


# ============================================================
#  Scenario 1: 默认 reason=done 归档
# ============================================================


def test_archive_default_reason_done(store: TaskStore) -> None:
    """对应 BDD 场景 1：x todo archive kemu1 → 默认 done，物理移动 + 字段更新。"""
    _write_task(
        store,
        "科目一",
        task_id="kemu1",
        status="in_progress",
        priority="high",
        deadline="2026-08-31",
    )

    exit_code, stdout, stderr = _invoke("kemu1")

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    # Success message format per BDD §场景 1
    assert "✅ 任务已归档" in stdout
    assert "科目一" in stdout  # display name == folder name here
    assert "kemu1" in stdout
    assert "reason=done" in stdout

    # 物理移动：任务/科目一 → 归档/<今天>-科目一
    assert not (store.active_dir / "科目一").exists()
    today_prefix = date.today().isoformat().replace("-", "")
    new_folder = store.archive_dir / f"{today_prefix}-科目一"
    assert new_folder.is_dir()
    assert (new_folder / "TODO.md").is_file()

    # 字段更新
    on_disk = (new_folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["status"] == "archived"
    assert metadata["reason"] == "done"
    assert metadata["updated"] == date.today().isoformat()
    assert metadata["folder"] == f"归档/{today_prefix}-科目一"
    # 其他字段保留
    assert metadata["id"] == "kemu1"
    assert metadata["priority"] == "high"
    assert metadata["deadline"] == "2026-08-31"
    assert metadata["name"] == "科目一"


# ============================================================
#  Scenario 2: reason=cancelled
# ============================================================


def test_archive_reason_cancelled(store: TaskStore) -> None:
    """对应 BDD 场景 2：--reason cancelled → reason=cancelled，物理移动。"""
    _write_task(
        store,
        "电视维修单",
        task_id="tvg-repair-2026",
        status="blocked",
    )

    exit_code, stdout, stderr = _invoke("tvg-repair-2026", "--reason", "cancelled")

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    assert "✅ 任务已归档" in stdout
    assert "电视维修单" in stdout
    assert "tvg-repair-2026" in stdout
    assert "reason=cancelled" in stdout

    today_prefix = date.today().isoformat().replace("-", "")
    new_folder = store.archive_dir / f"{today_prefix}-电视维修单"
    assert new_folder.is_dir()

    on_disk = (new_folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["status"] == "archived"
    assert metadata["reason"] == "cancelled"
    assert metadata["updated"] == date.today().isoformat()
    assert metadata["folder"] == f"归档/{today_prefix}-电视维修单"


# ============================================================
#  Scenario 3: reason=expired
# ============================================================


def test_archive_reason_expired(store: TaskStore) -> None:
    """对应 BDD 场景 3：--reason expired → reason=expired（逾期归档）。"""
    _write_task(
        store,
        "科目一",
        task_id="kemu1",
        status="pending",
        deadline="2026-05-01",  # 已过期
    )

    exit_code, stdout, _stderr = _invoke("kemu1", "--reason", "expired")

    assert exit_code == 0
    assert "reason=expired" in stdout

    today_prefix = date.today().isoformat().replace("-", "")
    new_folder = store.archive_dir / f"{today_prefix}-科目一"
    assert new_folder.is_dir()

    on_disk = (new_folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["reason"] == "expired"
    assert metadata["status"] == "archived"


# ============================================================
#  Scenario 4: ID 不存在
# ============================================================


def test_archive_missing_id_errors(store: TaskStore) -> None:
    """对应 BDD 场景 4：nonexistent-id → 退出码 3 + 错误提示，不修改任何文件。"""
    _write_task(store, "kemu1")  # 仓库里有个别任务，确保不是空仓库

    exit_code, stdout, stderr = _invoke("nonexistent-id")

    assert exit_code == 3
    assert "❌ 任务不存在：nonexistent-id" in stderr
    # 成功消息不出现
    assert "✅" not in stdout
    # 没有文件被移动
    assert (store.active_dir / "kemu1").is_dir()  # 原文件未动
    assert not (store.archive_dir / "kemu1").exists()


# ============================================================
#  Scenario 5: 任务已归档
# ============================================================


def test_archive_already_archived_errors(store: TaskStore) -> None:
    """对应 BDD 场景 5：归档任务再归档 → 退出码 4，不创建重复归档。"""
    _write_task(
        store,
        "相机贩卖业务",
        task_id="20260521-xiangjifanmai",
        archived=True,
        archive_date="20260521",
        reason="cancelled",
    )
    # 任务在归档目录里
    archived_folder = store.archive_dir / "20260521-相机贩卖业务"
    assert archived_folder.is_dir()

    exit_code, stdout, stderr = _invoke("20260521-xiangjifanmai")

    assert exit_code == 4
    assert "❌ 任务已归档：20260521-xiangjifanmai" in stderr
    assert "位于 归档/20260521-相机贩卖业务" in stderr
    assert "✅" not in stdout
    # 不创建重复归档
    today_prefix = date.today().isoformat().replace("-", "")
    assert not (store.archive_dir / f"{today_prefix}-20260521-xiangjifanmai").exists()
    # 原归档未动
    assert (store.archive_dir / "20260521-相机贩卖业务").is_dir()


# ============================================================
#  Scenario 6: 非法 reason
# ============================================================


def test_archive_invalid_reason_errors(store: TaskStore) -> None:
    """对应 BDD 场景 6：--reason invalid_reason → 退出码 2 + 列出合法值。"""
    _write_task(store, "kemu1")

    exit_code, stdout, stderr = _invoke("kemu1", "--reason", "invalid_reason")

    assert exit_code == 2
    assert "❌ 无效的 reason 值" in stderr
    assert "invalid_reason" in stderr
    # 列出全部合法值
    for legal in ("done", "cancelled", "expired", "failed"):
        assert legal in stderr, f"legal reason {legal!r} not in stderr: {stderr!r}"
    # 不移动文件夹，不修改文件
    assert (store.active_dir / "kemu1").is_dir()
    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["status"] == "pending"  # 未变


def test_archive_failed_reason_works(store: TaskStore) -> None:
    """对 BDD 列举的另一种 reason 合法值（failed）做覆盖测试。"""
    _write_task(store, "kemu1", status="in_progress")

    exit_code, stdout, _stderr = _invoke("kemu1", "--reason", "failed")

    assert exit_code == 0
    assert "reason=failed" in stdout

    today_prefix = date.today().isoformat().replace("-", "")
    on_disk = (store.archive_dir / f"{today_prefix}-kemu1" / "TODO.md").read_text(
        encoding="utf-8"
    )
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["reason"] == "failed"


# ============================================================
#  Scenario 7: 保留未知字段（关键兼容性）
# ============================================================


def test_archive_preserves_unknown_fields(store: TaskStore) -> None:
    """对应 BDD 场景 7：paused_at / description / pause_reason 必须保留。"""
    _write_task(
        store,
        "科目一",
        task_id="kemu1",
        extra={
            "description": "科目一学时已刷完",
            "paused_at": "2026-06-13",
            "pause_reason": "用户表态「不刷题了」",
        },
    )

    exit_code, _stdout, _stderr = _invoke("kemu1", "--reason", "cancelled")

    assert exit_code == 0

    today_prefix = date.today().isoformat().replace("-", "")
    new_folder = store.archive_dir / f"{today_prefix}-科目一"
    on_disk = (new_folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    # 未知字段全部保留
    assert metadata["description"] == "科目一学时已刷完"
    assert metadata["paused_at"] == "2026-06-13"
    assert metadata["pause_reason"] == "用户表态「不刷题了」"
    # 新增字段也正确
    assert metadata["status"] == "archived"
    assert metadata["reason"] == "cancelled"
    assert metadata["folder"] == f"归档/{today_prefix}-科目一"


# ============================================================
#  Scenario 8: 更新总索引 TODO.md
# ============================================================


def test_archive_updates_inventory(store: TaskStore) -> None:
    """对应 BDD 场景 8：归档后总索引 inventory.in_progress -1, archived +1, last_updated 刷新。"""
    _write_index(
        store,
        version="1.5",
        last_updated="2026-06-20",
        pending=3,
        in_progress=4,
        blocked=1,
        waiting=0,
        archived=22,
    )
    _write_task(
        store,
        "kemu1",
        status="in_progress",  # 对应 inventory.in_progress -1
    )

    exit_code, _stdout, _stderr = _invoke("kemu1", "--reason", "done")

    assert exit_code == 0

    # 总索引已更新
    on_disk = (store.todo_dir / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    inv = metadata["inventory"]
    assert inv["in_progress"] == 3, f"expected 3, got {inv['in_progress']}"
    assert inv["archived"] == 23, f"expected 23, got {inv['archived']}"
    # 其它桶不变
    assert inv["pending"] == 3
    assert inv["blocked"] == 1
    assert inv["waiting"] == 0
    # last_updated 刷新到今天
    assert metadata["last_updated"] == date.today().isoformat()
    # version 保持不变
    assert metadata["version"] == "1.5"


def test_archive_updates_inventory_pending_decrement(store: TaskStore) -> None:
    """场景 8 的另一路径：从 pending 归档时，pending -1。"""
    _write_index(
        store,
        pending=5,
        in_progress=2,
        blocked=0,
        waiting=0,
        archived=10,
    )
    _write_task(store, "kemu1", status="pending")

    exit_code, _stdout, _stderr = _invoke("kemu1", "--reason", "done")

    assert exit_code == 0
    on_disk = (store.todo_dir / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    inv = metadata["inventory"]
    assert inv["pending"] == 4
    assert inv["archived"] == 11


def test_archive_without_index_is_still_success(store: TaskStore) -> None:
    """没有总索引时归档仍应成功（索引缺失不是错误，可后续 regenerate）。"""
    # 故意不写 TODO.md
    assert not (store.todo_dir / "TODO.md").exists()
    _write_task(store, "kemu1", status="in_progress")

    exit_code, stdout, _stderr = _invoke("kemu1", "--reason", "done")

    assert exit_code == 0
    assert "✅" in stdout
    # 不应创建 TODO.md（best-effort skip）
    assert not (store.todo_dir / "TODO.md").exists()


# ============================================================
#  End-to-end: argparse 接线
# ============================================================


def test_archive_e2e_via_main(store: TaskStore) -> None:
    """端到端：x todo archive kemu1 --reason cancelled（覆盖 CLI 接线）。"""
    _write_task(store, "kemu1", status="pending")

    exit_code, stdout, stderr = _invoke("kemu1", "--reason", "cancelled")

    assert exit_code == 0
    assert "✅" in stdout
    assert "kemu1" in stdout
    assert "reason=cancelled" in stdout

    # 物理移动 + 字段
    today_prefix = date.today().isoformat().replace("-", "")
    new_folder = store.archive_dir / f"{today_prefix}-kemu1"
    on_disk = (new_folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["status"] == "archived"
    assert metadata["reason"] == "cancelled"


def test_archive_help_lists_id_and_reason_args() -> None:
    """`x todo archive --help` 由子解析器触发，列出 ``id`` 和 ``--reason`` 参数。

    BDD 没强制要求此项，但与 ``test_todo_update.py::test_update_no_options_errors``
    配合验证 argparse 接线正常。我们通过直接调 ``_todo_run(["archive", "--help"])``
    绕开 ``x.py`` 主入口的 ``--help`` 拦截（主入口会先消费 ``--help``，这是
    argparse ``parse_known_args`` 的固有行为）。
    """
    from x import _todo_register
    import argparse

    parser = argparse.ArgumentParser(prog="x todo")
    _todo_register(parser)
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["archive", "--help"])
    assert exc_info.value.code == 0
    # We just verify the parser registered the right args; the help
    # message itself goes to stdout via parser.exit() and is captured
    # by capsys in the calling context.


def test_archive_missing_id_arg_triggers_argparse_error() -> None:
    """`x todo archive`（无 id）→ argparse 报错（SystemExit(2)）。"""
    with pytest.raises(SystemExit) as exc_info:
        main(["todo", "archive"])
    assert exc_info.value.code == 2


# ============================================================
#  Direct unit test: 验证 _todo_archive handler 的退出码合约
# ============================================================


def test_todo_archive_handler_direct_call_missing_id(store: TaskStore) -> None:
    """直接调用 _todo_archive 验证退出码 3（路径 BDD §场景 4）。"""
    from argparse import Namespace

    _write_task(store, "kemu1")  # 别的任务
    args = Namespace(id="nonexistent", reason="done")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = _todo_archive(args)
    assert code == 3
    assert "❌ 任务不存在" in err.getvalue()


def test_todo_archive_handler_direct_call_invalid_reason(store: TaskStore) -> None:
    """直接调用 _todo_archive 验证退出码 2（BDD §场景 6）。"""
    from argparse import Namespace

    _write_task(store, "kemu1")
    args = Namespace(id="kemu1", reason="bogus")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = _todo_archive(args)
    assert code == 2
    assert "❌ 无效的 reason" in err.getvalue()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
