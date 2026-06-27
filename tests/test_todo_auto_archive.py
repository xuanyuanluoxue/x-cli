"""Tests for ``x todo`` 自动归档 (auto-archive) feature.

每个测试对应一个 BDD 场景 ——
``docs/behaviors/todo-auto-archive-behavior.md``.

覆盖范围：
- 启用方式 A：YAML ``todo.auto_archive: true``
- 启用方式 B：环境变量 ``XCLI_TODO_AUTO_ARCHIVE=1``
- 触发命令：``x todo list`` / ``x todo stats`` / ``x todo search``
- 默认禁用（不破坏现有用户）
- stdout 顶部摘要 + reason=expired

测试策略：
- 每个测试用 ``XCLI_TODO_DIR=tmp_path`` 隔离任务仓库
- 每个测试 ``monkeypatch.delenv("XCLI_TODO_AUTO_ARCHIVE", raising=False)``
  清理环境变量，避免泄漏
- config 路径走 ``<data_dir>/config.yaml`` —— 测试同时把
  ``LOCALAPPDATA`` / ``XDG_DATA_HOME`` 钉到 tmp_path
"""

from __future__ import annotations

import io
import os
import sys
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

import pytest

from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.storage import TaskStore
from x import _todo_list, _todo_search, _todo_stats


_TODAY_YMD = date.today().strftime("%Y%m%d")


# ============================================================
#  Fixtures and helpers
# ============================================================


@pytest.fixture
def isolated_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, TaskStore]:
    """Pin TODO root + x-cli data dir to ``tmp_path``; return both.

    总是清理 ``XCLI_TODO_AUTO_ARCHIVE`` —— 否则其他测试的
    ``monkeypatch.setenv`` 可能泄漏到这里。
    """
    monkeypatch.delenv("XCLI_TODO_AUTO_ARCHIVE", raising=False)
    monkeypatch.delenv("XCLI_CONFIG", raising=False)
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    data_dir = tmp_path / "x-cli"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir, TaskStore()


def _write_config(data_dir: Path, content: str) -> Path:
    """Write a config.yaml under ``<data_dir>/config.yaml`` and return its path."""
    cfg = data_dir / "config.yaml"
    cfg.write_text(content, encoding="utf-8")
    return cfg


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
    """Drop a TODO.md on disk matching the on-disk layout.

    Mirrors the helper in ``test_todo_list.py`` — kept local to keep
    the test file self-contained (the secret subagent is also editing
    test files in parallel).
    """
    if archived:
        target_dir = store.archive_dir / f"{archive_date}-{name}"
        relative_folder = f"归档/{archive_date}-{name}"
        if status == "pending":
            status_to_write = "archived"
        else:
            status_to_write = status
        reason_to_write = reason if reason is not None else "done"
    else:
        target_dir = store.active_dir / name
        relative_folder = f"任务/{name}"
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
        body=body,
    )
    (target_dir / "TODO.md").write_text(task.to_markdown(), encoding="utf-8")
    return task


def _run_list(
    args: list[str], store: TaskStore
) -> tuple[int, str, str]:
    """Invoke ``_todo_list`` with a pre-built Namespace.

    Mirrors ``test_todo_list._run_list_handler``.
    """
    ns = Namespace(
        status=None,
        priority=None,
        tag=None,
        include_archived=False,
    )
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
    os.environ["XCLI_TODO_DIR"] = str(store.todo_dir)
    try:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = _todo_list(ns)
        return code, out.getvalue(), err.getvalue()
    finally:
        os.environ.pop("XCLI_TODO_DIR", None)


def _run_stats(store: TaskStore) -> tuple[int, str, str]:
    """Invoke ``_todo_stats`` (no flags)."""
    os.environ["XCLI_TODO_DIR"] = str(store.todo_dir)
    try:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = _todo_stats([])
        return code, out.getvalue(), err.getvalue()
    finally:
        os.environ.pop("XCLI_TODO_DIR", None)


def _run_search(
    keyword: str, args: list[str], store: TaskStore
) -> tuple[int, str, str]:
    """Invoke ``_todo_search`` with a pre-built Namespace."""
    ns = Namespace(
        keyword=keyword,
        active_only=False,
        archived_only=False,
        status=None,
    )
    for tok in args:
        if tok == "--active-only":
            ns.active_only = True
        elif tok == "--archived-only":
            ns.archived_only = True
        elif tok == "--status":
            # Need next token
            raise AssertionError("--status needs a value; build ns manually")
        else:
            raise AssertionError(f"unexpected token in test: {tok}")
    os.environ["XCLI_TODO_DIR"] = str(store.todo_dir)
    try:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = _todo_search(ns)
        return code, out.getvalue(), err.getvalue()
    finally:
        os.environ.pop("XCLI_TODO_DIR", None)


# ============================================================
#  BDD §场景 1：YAML 启用 + list + 有 overdue → 自动归档 + 顶部提示
# ============================================================


def test_bdd_scenario_1_yaml_enable_list_archives_overdue_and_prints_summary(
    isolated_env: tuple[Path, TaskStore],
) -> None:
    """YAML ``todo.auto_archive: true`` + list + 有逾期 → 顶部摘要 + 归档。

    对应 BDD §场景 1。
    """
    data_dir, store = isolated_env
    _write_config(
        data_dir,
        "todo:\n  auto_archive: true\n",
    )

    # overdue: deadline 2026-05-01, today is 2026-06-26 (in BDD)
    make_task(
        store, "kemu1", task_id="kemu1",
        status="pending", priority="high",
        deadline="2026-05-01",
    )
    # not overdue: 2026-08-31
    make_task(
        store, "zizhushixi", task_id="zizhushixi",
        status="in_progress", priority="medium",
        deadline="2026-08-31",
    )

    code, out, err = _run_list([], store)

    assert code == 0
    assert err == ""

    # The summary line must appear FIRST, before the table
    lines = out.splitlines()
    assert lines, "stdout should not be empty"
    assert lines[0].startswith("⏰ 自动归档 1 个逾期任务："), (
        f"expected summary line first, got: {lines[0]!r}"
    )
    assert "kemu1" in lines[0]

    # kemu1 must be physically archived (reason=expired)
    archived_dir = store.archive_dir / f"{_TODAY_YMD}-kemu1"
    assert archived_dir.is_dir(), "kemu1 should be moved to 归档/"
    frontmatter = (archived_dir / "TODO.md").read_text(encoding="utf-8")
    assert "reason: expired" in frontmatter

    # The table below the summary should list only zizhushixi
    assert "zizhushixi" in out
    # kemu1 must NOT appear in the table (it's been archived → under list it
    # would not show up by default; with the summary it should appear exactly
    # once — in the summary line itself).
    table_section = lines[1:] if lines else []
    table_text = "\n".join(table_section)
    assert "kemu1" not in table_text, (
        f"kemu1 should not appear in the table after auto-archive; "
        f"table was:\n{table_text}"
    )


# ============================================================
#  BDD §场景 2：YAML 启用 + list + 无 overdue → 无提示
# ============================================================


def test_bdd_scenario_2_yaml_enable_no_overdue_silent(
    isolated_env: tuple[Path, TaskStore],
) -> None:
    """YAML 启用 + 无逾期任务 → 不打摘要，输出原 list。

    对应 BDD §场景 2。
    """
    data_dir, store = isolated_env
    _write_config(data_dir, "todo:\n  auto_archive: true\n")

    # All tasks have non-overdue or no deadlines
    make_task(store, "kemu1", deadline="2026-08-31")
    make_task(store, "no-deadline", deadline=None)

    code, out, err = _run_list([], store)

    assert code == 0
    assert err == ""
    # NO summary line
    assert "⏰ 自动归档" not in out
    # Normal list output still present
    assert "kemu1" in out
    assert "no-deadline" in out
    # Nothing got archived (archive_dir may not exist at all — that's fine)
    if store.archive_dir.is_dir():
        assert not any(store.archive_dir.iterdir())


# ============================================================
#  BDD §场景 3：默认禁用 + list → 不归档，无提示
# ============================================================


def test_bdd_scenario_3_default_disabled_does_not_archive(
    isolated_env: tuple[Path, TaskStore],
) -> None:
    """默认禁用（无 YAML + 无 env var）→ 逾期任务**不**归档，无摘要。

    对应 BDD §场景 3 — 关键，不能破坏现有用户。
    """
    _data_dir, store = isolated_env
    # Deliberately NO config.yaml — default disabled
    # Deliberately NO env var — _isolate_env fixture clears it

    # Overdue task
    make_task(
        store, "kemu1",
        status="pending", deadline="2025-12-31",
    )

    code, out, err = _run_list([], store)

    assert code == 0
    assert err == ""
    # No summary
    assert "⏰ 自动归档" not in out
    # Task STILL in active (not archived)
    assert (store.active_dir / "kemu1").is_dir(), (
        "kemu1 must stay in 任务/ when auto-archive is disabled"
    )
    assert not (store.archive_dir / f"{_TODAY_YMD}-kemu1").exists()
    # Output still lists it
    assert "kemu1" in out


# ============================================================
#  BDD §场景 4：YAML 启用 + stats + overdue → 顶部摘要 + 计数 +N
# ============================================================


def test_bdd_scenario_4_yaml_enable_stats_archives_and_counts_correctly(
    isolated_env: tuple[Path, TaskStore],
) -> None:
    """YAML 启用 + stats → 顶部摘要 + 归档后 archived 计数正确。

    对应 BDD §场景 4。
    """
    data_dir, store = isolated_env
    _write_config(data_dir, "todo:\n  auto_archive: true\n")

    # 2 overdue + 1 not overdue
    make_task(store, "kemu1", status="pending", deadline="2026-05-01")
    make_task(store, "kemu2", status="pending", deadline="2026-04-01")
    make_task(store, "zizhushixi", status="in_progress", deadline="2026-08-31")

    code, out, err = _run_stats(store)

    assert code == 0
    assert err == ""

    lines = out.splitlines()
    assert lines, "stdout should not be empty"
    assert lines[0].startswith("⏰ 自动归档 2 个逾期任务："), (
        f"expected summary first; got: {lines[0]!r}"
    )
    # Summary should mention both ids
    assert "kemu1" in lines[0]
    assert "kemu2" in lines[0]

    # Stats body: archived should reflect +2
    body = "\n".join(lines[1:])
    # The stats format prints "archived：N" — N must be 2 (no pre-existing
    # archived tasks in this test).
    assert "archived：2" in body, f"expected archived:2 in stats body; got:\n{body}"
    # And pending dropped from 3 → 1 (only zizhushixi is in_progress, but
    # pending went 2 → 0 after archive)
    assert "pending：0" in body
    assert "in_progress：1" in body

    # Both overdue tasks physically archived
    assert (store.archive_dir / f"{_TODAY_YMD}-kemu1").is_dir()
    assert (store.archive_dir / f"{_TODAY_YMD}-kemu2").is_dir()
    assert "reason: expired" in (
        (store.archive_dir / f"{_TODAY_YMD}-kemu1" / "TODO.md").read_text(
            encoding="utf-8"
        )
    )


# ============================================================
#  BDD §场景 5：YAML 启用 + search + overdue → 顶部摘要 + 结果不含已归档
# ============================================================


def test_bdd_scenario_5_yaml_enable_search_excludes_archived_overdue(
    isolated_env: tuple[Path, TaskStore],
) -> None:
    """YAML 启用 + search → 顶部摘要 + search 结果不含已归档的逾期任务。

    对应 BDD §场景 5。
    """
    data_dir, store = isolated_env
    _write_config(data_dir, "todo:\n  auto_archive: true\n")

    # Use Chinese task names so ``search 模拟考`` actually matches.
    # The folder name (= task.name) carries the searchable Chinese text;
    # the task_id stays short Latin for stable assertions below.
    make_task(
        store, "科目一模拟考", task_id="kemu1",
        deadline="2026-05-01",  # overdue
    )
    make_task(
        store, "科目二模拟考", task_id="kemu2",
        deadline="2026-08-31",  # not overdue
    )

    code, out, err = _run_search("模拟考", [], store)

    assert code == 0
    assert err == ""

    lines = out.splitlines()
    assert lines, "stdout should not be empty"
    assert lines[0].startswith("⏰ 自动归档 1 个逾期任务：kemu1"), (
        f"expected summary first; got: {lines[0]!r}"
    )

    # The table after the summary should only contain kemu2
    body = "\n".join(lines[1:])
    assert "kemu2" in body
    # kemu1 must NOT be in the search result table. BDD §场景 5 says
    # search 结果不含 — the implementation forces include_archived=False
    # when auto-archive just fired (unless --archived-only is set).
    table_lines = lines[1:]
    leaked = [
        ln for ln in table_lines if "kemu1" in ln
    ]
    assert not leaked, (
        f"kemu1 leaked into search result table: {leaked}"
    )

    # And kemu1 physically archived (folder is 归档/<date>-科目一模拟考/)
    archived_folders = [p.name for p in store.archive_dir.iterdir()]
    assert any(
        name.startswith(f"{_TODAY_YMD}-") and "科目一" in name
        for name in archived_folders
    ), f"expected archived folder for kemu1; got: {archived_folders}"


# ============================================================
#  BDD §场景 6：环境变量 XCLI_TODO_AUTO_ARCHIVE=1 启用（无 YAML）
# ============================================================


def test_bdd_scenario_6_env_var_enables_without_yaml(
    isolated_env: tuple[Path, TaskStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``XCLI_TODO_AUTO_ARCHIVE=1`` 启用 —— 无 YAML 也生效。

    对应 BDD §场景 6。
    """
    _data_dir, store = isolated_env
    # NO config.yaml written
    # Enable via env var only
    monkeypatch.setenv("XCLI_TODO_AUTO_ARCHIVE", "1")

    make_task(store, "kemu1", deadline="2026-05-01")  # overdue

    code, out, err = _run_list([], store)

    assert code == 0
    assert err == ""
    assert out.startswith("⏰ 自动归档 1 个逾期任务：kemu1"), (
        f"expected summary at top; got: {out[:200]!r}"
    )
    # Archived
    assert (store.archive_dir / f"{_TODAY_YMD}-kemu1").is_dir()
    frontmatter = (
        (store.archive_dir / f"{_TODAY_YMD}-kemu1" / "TODO.md")
        .read_text(encoding="utf-8")
    )
    assert "reason: expired" in frontmatter


# ============================================================
#  反向 case：env var + YAML 一致时 OR 关系（额外 sanity check）
# ============================================================


def test_env_var_wins_over_disabled_yaml(
    isolated_env: tuple[Path, TaskStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``XCLI_TODO_AUTO_ARCHIVE=1`` + YAML ``todo.auto_archive: false``
    → 启用（env 优先）。
    """
    data_dir, store = isolated_env
    _write_config(data_dir, "todo:\n  auto_archive: false\n")
    monkeypatch.setenv("XCLI_TODO_AUTO_ARCHIVE", "1")

    make_task(store, "kemu1", deadline="2026-05-01")

    code, out, _ = _run_list([], store)

    assert code == 0
    assert "⏰ 自动归档 1 个逾期任务：kemu1" in out
    assert (store.archive_dir / f"{_TODAY_YMD}-kemu1").is_dir()


def test_yaml_disable_does_not_override_unset_env(
    isolated_env: tuple[Path, TaskStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``XCLI_TODO_AUTO_ARCHIVE`` 未设置 + YAML ``todo.auto_archive: false``
    → 禁用（不归档）。

    这与场景 3 一致 —— 但显式 YAML=false 也要尊重。
    """
    data_dir, store = isolated_env
    _write_config(data_dir, "todo:\n  auto_archive: false\n")
    # env var unset (fixture cleared it)
    assert "XCLI_TODO_AUTO_ARCHIVE" not in os.environ

    make_task(store, "kemu1", deadline="2026-05-01")

    code, out, _ = _run_list([], store)

    assert code == 0
    assert "⏰ 自动归档" not in out
    assert (store.active_dir / "kemu1").is_dir()
    assert not (store.archive_dir / f"{_TODAY_YMD}-kemu1").exists()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))