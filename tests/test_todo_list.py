"""Tests for ``x todo list`` command.

Each test maps to a scenario in
``docs/behaviors/todo-list-behavior.md``. The command wraps
:func:`x._todo_list` which delegates to
:meth:`core.storage.TaskStore.list_tasks`; tests here exercise the
filter logic, the table renderer, the empty-store branch, and the
integration through :func:`x.main`.

All tests use ``tmp_path`` (via :envvar:`XCLI_TODO_DIR`) so the real
``~/.xavier/TODO`` is never touched.
"""

from __future__ import annotations

import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.storage import TaskStore
from x import _todo_list, main


# ============================================================
#  Fixtures and helpers
# ============================================================


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskStore:
    """Return a TaskStore rooted at ``tmp_path`` (real ~/.xavier/TODO is safe)."""
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
    return TaskStore()  # picks up the env var


def _run_list(args: list[str], monkeypatch, tmp_path) -> tuple[int, str, str]:
    """Invoke ``main([\"todo\", \"list\", *args])`` and return ``(code, stdout, stderr)``."""
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(["todo", "list", *args])
    return code, out.getvalue(), err.getvalue()


def _run_list_handler(
    args: list[str], store: TaskStore
) -> tuple[int, str, str]:
    """Invoke :func:`x._todo_list` directly with a pre-built Namespace.

    Used for unit tests that want to control the parsed arguments
    without going through ``main``.
    """
    from argparse import Namespace

    ns = Namespace(
        status=None,
        priority=None,
        tag=None,
        include_archived=False,
    )
    # Tiny positional argument parser (just enough for these tests)
    it = iter(args)
    for tok in it:
        if tok == "--status":
            ns.status = next(it)
        elif tok == "--priority":
            ns.priority = next(it)
        elif tok == "--tag":
            ns.tag = next(it)
        elif tok == "--all":
            ns.include_archived = True
        else:
            raise AssertionError(f"unexpected token in test: {tok}")

    out, err = io.StringIO(), io.StringIO()
    # Override the env var so store reads from tmp_path
    os.environ["XCLI_TODO_DIR"] = str(store.todo_dir)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = _todo_list(ns)
    finally:
        # Restore to avoid leaking into other tests; fixtures re-set it anyway
        os.environ.pop("XCLI_TODO_DIR", None)
    return code, out.getvalue(), err.getvalue()


def _parse_list_output(out: str) -> tuple[list[str], list[list[str]]]:
    """Parse ``x todo list`` output into (header_cells, data_rows).

    The renderer writes header + ─── separator + N data rows, separated
    by 2 spaces (CJK-aware padding instead of tabs).
    """
    lines = out.rstrip("\n").splitlines()
    if not lines:
        return [], []
    header = [c.strip() for c in lines[0].split("  ") if c.strip()]
    data = [
        [c.strip() for c in line.split("  ") if c.strip()]
        for line in lines[1:]
        if not line.lstrip().startswith("─")
    ]
    return header, data


def make_task(
    store: TaskStore,
    name: str,
    *,
    task_id: str | None = None,
    status: str = "pending",
    priority: str = "medium",
    created: str = "2026-06-01",
    updated: str = "2026-06-01",
    deadline: str | None = None,
    tags: list[str] | None = None,
    reason: str | None = None,
    body: str = "",
    archived: bool = False,
    archive_date: str = "20260615",
) -> Task:
    """Create a Task on disk inside ``store`` and return it.

    The on-disk layout follows the real convention: active tasks go
    under ``任务/<name>`` and archived tasks under
    ``归档/<archive_date>-<name>``. When ``archived=True`` and the
    caller did not explicitly pass a ``status``, the status defaults
    to ``"archived"`` so the file on disk is internally consistent.
    """
    if archived:
        target_dir = store.archive_dir / f"{archive_date}-{name}"
        relative_folder = f"归档/{archive_date}-{name}"
        if status == "pending":  # caller didn't override
            status = "archived"
    else:
        target_dir = store.active_dir / name
        relative_folder = f"任务/{name}"
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
        reason=ArchiveReason(reason) if reason else None,
        body=body,
    )
    (target_dir / "TODO.md").write_text(task.to_markdown(), encoding="utf-8")
    return task


# ============================================================
#  BDD §场景 1：默认列出所有未归档任务
# ============================================================


def test_bdd_scenario_1_default_lists_only_active(store):
    """BDD §场景 1：默认 `x todo list` 列出 3 个未归档任务，不含归档任务。"""
    # 数据按 BDD 列出的顺序设置 deadline，使得 sort 后的输出与 BDD
    # 例子一致（kemu1 → zizhushixi → laodongjiaoyu3）。
    make_task(
        store, "kemu1",
        task_id="kemu1", status="pending", priority="high",
        deadline="2026-07-15", tags=["驾照", "暑假"],
    )
    make_task(
        store, "zizhushixi",
        task_id="zizhushixi", status="in_progress", priority="medium",
        deadline="2026-08-31", tags=["实习"],
    )
    make_task(
        store, "laodongjiaoyu3",
        task_id="laodongjiaoyu3", status="blocked", priority="low",
        deadline=None, tags=["学校"],
    )
    make_task(
        store, "xiangjifanmai",
        task_id="20260521-xiangjifanmai", priority="medium",
        tags=["相机"],
        archived=True, archive_date="20260521",
        reason="cancelled",
    )

    code, out, err = _run_list_handler([], store)
    assert code == 0
    assert err == ""

    header, data = _parse_list_output(out)
    # 表头与 BDD 一致
    assert header == ["ID", "Name", "Status", "Priority", "Deadline"]
    # 数据行：3 个未归档任务（按 deadline 升序，None 在末尾）
    data_ids = [row[0] for row in data]
    assert data_ids == ["kemu1", "zizhushixi", "laodongjiaoyu3"]
    # 归档任务 20260521-xiangjifanmai 不应出现
    assert "20260521-xiangjifanmai" not in out
    # 验证列顺序与表头一致
    assert data[0] == [
        "kemu1",
        "kemu1",  # name (folder name same as id)
        "⏳ pending",
        "🔥 high",
        "2026-07-15",
    ]


def test_bdd_scenario_1_deadline_sort_none_last(store):
    """BDD §场景 1：deadline 升序，None 排在末尾。"""
    make_task(store, "no-deadline", deadline=None, priority="high")
    make_task(store, "late", deadline="2026-09-01", priority="low")
    make_task(store, "early", deadline="2026-07-01", priority="medium")

    code, out, _ = _run_list_handler([], store)
    assert code == 0
    _, data = _parse_list_output(out)
    ids = [row[0] for row in data]
    assert ids == ["early", "late", "no-deadline"]


# ============================================================
#  BDD §场景 2：按 --status 过滤
# ============================================================


def test_bdd_scenario_2_filter_by_status(store):
    """BDD §场景 2：`--status in_progress` 只显示 in_progress 任务。"""
    make_task(store, "kemu1", status="pending", priority="high")
    make_task(store, "zizhushixi", status="in_progress", priority="medium")
    make_task(store, "laodongjiaoyu3", status="blocked", priority="low")

    code, out, err = _run_list_handler(["--status", "in_progress"], store)
    assert code == 0
    assert err == ""

    _, data = _parse_list_output(out)
    ids = [row[0] for row in data]
    assert ids == ["zizhushixi"]
    assert "kemu1" not in out
    assert "laodongjiaoyu3" not in out


# ============================================================
#  BDD §场景 3：按 --priority 过滤
# ============================================================


def test_bdd_scenario_3_filter_by_priority(store):
    """BDD §场景 3：`--priority high` 只显示 high 任务。"""
    make_task(store, "kemu1", priority="high")
    make_task(store, "zizhushixi", priority="medium")
    make_task(store, "laodongjiaoyu3", priority="low")

    code, out, err = _run_list_handler(["--priority", "high"], store)
    assert code == 0
    assert err == ""

    _, data = _parse_list_output(out)
    ids = [row[0] for row in data]
    assert ids == ["kemu1"]


# ============================================================
#  BDD §场景 4：按 --tag 过滤
# ============================================================


def test_bdd_scenario_4_filter_by_tag(store):
    """BDD §场景 4：`--tag 暑假` 只显示含该标签的任务。"""
    make_task(store, "kemu1", tags=["驾照", "暑假"])
    make_task(store, "zizhushixi", tags=["实习"])
    make_task(store, "laodongjiaoyu3", tags=["学校"])

    code, out, err = _run_list_handler(["--tag", "暑假"], store)
    assert code == 0
    assert err == ""

    _, data = _parse_list_output(out)
    ids = [row[0] for row in data]
    assert ids == ["kemu1"]


def test_filter_by_tag_matches_no_task(store):
    """`--tag` 找不到匹配时输出空提示。"""
    make_task(store, "kemu1", tags=["驾照"])
    code, out, _ = _run_list_handler(["--tag", "不存在的标签"], store)
    assert code == 0
    assert "📭 没有任务" in out


# ============================================================
#  BDD §场景 5：--all 显示全部（含归档）
# ============================================================


def test_bdd_scenario_5_all_includes_archived(store):
    """BDD §场景 5：`--all` 包含归档任务，状态列显示 `archived (reason)`。"""
    # 3 active + 1 archived = 4 行（与 BDD 一致）
    make_task(store, "kemu1", status="pending", priority="high", deadline="2026-07-15")
    make_task(store, "zizhushixi", status="in_progress", priority="medium", deadline="2026-08-31")
    make_task(store, "laodongjiaoyu3", status="blocked", priority="low", deadline=None)
    make_task(
        store, "xiangjifanmai",
        priority="medium", tags=["相机"],
        archived=True, archive_date="20260521", reason="cancelled",
    )

    code, out, err = _run_list_handler(["--all"], store)
    assert code == 0
    assert err == ""

    # 4 行数据：3 active + 1 archived（跳过 ─── 分隔线）
    all_lines = out.rstrip("\n").splitlines()
    data_lines = [l for l in all_lines[1:] if not l.lstrip().startswith("─")]
    assert len(data_lines) == 4

    # 归档任务的 status 列应包含 `archived (cancelled)`（CJK 格式带 🚫 icon，因为 reason=cancelled）
    archived_line = next(
        line for line in data_lines if "xiangjifanmai" in line
    )
    cells = [c.strip() for c in archived_line.split("  ") if c.strip()]
    assert cells[2] == "🚫 archived (cancelled)"

    # 未归档任务在前（按 deadline 升序，None 末尾），归档在后
    ordered = [([c.strip() for c in line.split("  ") if c.strip()][0]) for line in data_lines]
    assert ordered[0] == "kemu1"           # deadline 2026-07-15
    assert ordered[1] == "zizhushixi"       # deadline 2026-08-31
    assert ordered[2] == "laodongjiaoyu3"   # deadline None
    assert ordered[3] == "xiangjifanmai"   # 归档


# ============================================================
#  BDD §场景 6：空仓库（无任务）
# ============================================================


def test_bdd_scenario_6_empty_store_prints_message_and_exits_zero(store):
    """BDD §场景 6：空仓库输出 `📭 没有任务`，不打印空表格。"""
    # store 已被 tmp_path 隔离，且没有创建任何任务
    assert not store.active_dir.exists() or not any(store.active_dir.iterdir())
    assert not store.archive_dir.exists() or not any(store.archive_dir.iterdir())

    code, out, err = _run_list_handler([], store)
    assert code == 0
    assert err == ""
    assert "📭 没有任务" in out
    # 不打印空表格
    assert "ID\tName\tStatus\tPriority\tDeadline" not in out


# ============================================================
#  BDD §场景 7：多过滤条件组合（AND）
# ============================================================


def test_bdd_scenario_7_multiple_filters_are_and(store):
    """BDD §场景 7：多个过滤条件同时满足才显示（AND 关系）。"""
    make_task(
        store, "kemu1",
        status="pending", priority="high", tags=["驾照", "暑假"],
    )
    make_task(
        store, "kemu1-medium",
        status="pending", priority="medium", tags=["驾照", "暑假"],
    )
    make_task(
        store, "zizhushixi",
        status="in_progress", priority="medium", tags=["实习"],
    )

    code, out, _ = _run_list_handler(
        ["--status", "pending", "--priority", "high", "--tag", "暑假"],
        store,
    )
    assert code == 0
    _, data = _parse_list_output(out)
    ids = [row[0] for row in data]
    assert ids == ["kemu1"]


# ============================================================
#  BDD §场景 8：过滤值无效（错误路径）
# ============================================================


def test_bdd_scenario_8_invalid_status_errors_with_exit_2(store):
    """BDD §场景 8：非法 status → 退出码 2 + 错误信息，不打印表格。"""
    make_task(store, "kemu1")

    code, out, err = _run_list_handler(["--status", "invalid_status"], store)
    assert code == 2
    assert "❌" in err
    assert "invalid_status" in err
    # 错误信息应列出所有合法值
    for legal in ("pending", "in_progress", "blocked", "waiting", "archived"):
        assert legal in err
    # 不应打印表格
    assert "ID\tName" not in out


def test_invalid_priority_errors_with_exit_2(store):
    """`--priority` 非法值 → 退出码 2 + 错误信息。"""
    code, _, err = _run_list_handler(["--priority", "ultra"], store)
    assert code == 2
    assert "❌" in err
    assert "ultra" in err
    for legal in ("high", "medium", "low"):
        assert legal in err


# ============================================================
#  Integration: x main entry dispatches list
# ============================================================


def test_main_dispatches_todo_list(monkeypatch, tmp_path):
    """`x todo list` 通过主入口可正常运行（空仓库 → 提示信息）。"""
    code, out, err = _run_list([], monkeypatch, tmp_path)
    assert code == 0
    assert "📭 没有任务" in out
    assert err == ""


def test_main_dispatches_todo_list_with_filters(monkeypatch, tmp_path):
    """`x todo list --status in_progress` 通过主入口可正常运行。"""
    # 真实创建一个任务
    os.environ["XCLI_TODO_DIR"] = str(tmp_path)
    try:
        store = TaskStore()
        make_task(store, "kemu1", status="pending", priority="high")
        make_task(store, "zizhushixi", status="in_progress", priority="medium")
    finally:
        os.environ.pop("XCLI_TODO_DIR", None)

    code, out, err = _run_list(["--status", "in_progress"], monkeypatch, tmp_path)
    assert code == 0
    assert err == ""
    assert "zizhushixi" in out
    assert "kemu1" not in out


def test_main_dispatches_todo_list_with_unknown_flag(monkeypatch, tmp_path):
    """`x todo list --bogus` 触发 argparse 用法错误（SystemExit 2）。"""
    with pytest.raises(SystemExit) as exc_info:
        main(["todo", "list", "--bogus"])
    assert exc_info.value.code == 2


# ============================================================
#  Table schema sanity checks
# ============================================================


def test_table_header_matches_bdd_columns(store):
    """表头列与 BDD 一致：ID / Name / Status / Priority / Deadline。

    列与列之间用 2 空格分隔（CJK 对齐后的格式）；不再用 tab。
    """
    make_task(store, "kemu1")
    _, out, _ = _run_list_handler([], store)
    first_line = out.splitlines()[0]
    header_cells = [c.strip() for c in first_line.split("  ") if c.strip()]
    assert header_cells == ["ID", "Name", "Status", "Priority", "Deadline"]


def test_table_columns_separated_by_two_spaces(store):
    """表格用 2 空格对齐（CJK 友好）。

    第 2 行是 ─── 分隔线，要跳过。
    """
    make_task(store, "kemu1", deadline="2026-08-31")
    _, out, _ = _run_list_handler([], store)
    lines = out.strip().splitlines()
    data_lines = [l for l in lines if not l.lstrip().startswith("─")]
    for line in data_lines:
        cells = [c.strip() for c in line.split("  ") if c.strip()]
        assert len(cells) == 5, f"line {line!r} has {len(cells)} cells, expected 5"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
