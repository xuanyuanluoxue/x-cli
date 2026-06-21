"""Tests for ``x todo update <id>`` (Phase 1 inline in x.py).

Each test maps to a scenario in
``docs/behaviors/todo-update-behavior.md``:

1. update status (single field, others unchanged)            → test_update_status
2. update priority + deadline + tags (multi-field, replace)  → test_update_multi_fields
3. ID not found (error)                                      → test_update_missing_id_errors
4. invalid --status value (error)                            → test_update_invalid_status_errors
5. clear deadline with --deadline ""                         → test_update_clear_deadline_via_empty_string
6. preserve unknown fields (description, paused_at, …)      → test_update_preserves_unknown_fields
7. update archived task (error)                              → test_update_archived_task_errors
8. no --option at all (argparse error)                       → test_update_no_options_errors

Plus an end-to-end test through ``main()`` to make sure the
argparse wiring works when invoked exactly as a user would.

All tests use ``XAVIER_TODO_DIR`` pointed at ``tmp_path`` so the
real ``~/.xavier/TODO`` is never modified. The implementation
under test (``x._todo_update``) reads the env var via
``TaskStore()``.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

import pytest

from core.models import ArchiveReason, Priority as Prio, Task, TaskStatus
from core.parser import parse_frontmatter
from core.storage import TaskStore
from x import main


# ============================================================
#  Helpers (mirror test_storage.write_task so each test stays focused)
# ============================================================


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskStore:
    """Root the TaskStore at ``tmp_path``; never touches the real TODO dir."""
    monkeypatch.setenv("XAVIER_TODO_DIR", str(tmp_path))
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
) -> None:
    """Drop a TODO.md on disk that matches the BDD scenario 1 fixture."""
    if archived:
        target_dir = store.archive_dir / f"{archive_date}-{name}"
        relative_folder = f"归档/{archive_date}-{name}"
        status_to_write = status if status != "pending" else "archived"
    else:
        target_dir = store.active_dir / name
        relative_folder = folder or f"任务/{name}"
        status_to_write = status
    target_dir.mkdir(parents=True, exist_ok=True)
    task = Task(
        id=task_id or name,
        name=name,
        status=TaskStatus(status_to_write),
        priority=Prio(priority),
        created=created,
        updated=updated,
        deadline=deadline,
        folder=relative_folder,
        tags=tags,
        reason=ArchiveReason.DONE if archived else None,
        extra=extra or {},
    )
    (target_dir / "TODO.md").write_text(task.to_markdown(), encoding="utf-8")


def _invoke(*argv: str) -> tuple[int, str, str]:
    """Call ``main`` with the given argv (relative to ``x todo update``)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        exit_code = main(["todo", "update", *argv])
    return exit_code, out.getvalue(), err.getvalue()


# ============================================================
#  Scenario 1: 更新任务状态（最常见）
# ============================================================


def test_update_status_changes_only_status(store: TaskStore) -> None:
    """对应 BDD 场景 1：仅更新 status，其它字段保持不变。"""
    _write_task(
        store,
        "科目一模拟考",
        task_id="kemu1",
        status="pending",
        priority="high",
        deadline="2026-08-31",
        created="2026-03-27",
        updated="2026-03-27",
    )

    exit_code, stdout, stderr = _invoke("kemu1", "--status", "in_progress")

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    assert "✅ 任务已更新" in stdout
    assert "kemu1" in stdout

    # On-disk frontmatter
    on_disk = (store.active_dir / "科目一模拟考" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["status"] == "in_progress"
    assert metadata["priority"] == "high"
    assert metadata["deadline"] == "2026-08-31"
    assert metadata["created"] == "2026-03-27"
    assert metadata["updated"] == "2026-06-21"  # auto-set
    assert metadata["folder"] == "任务/科目一模拟考"  # 未变（不移动）


# ============================================================
#  Scenario 2: 同时更新多字段
# ============================================================


def test_update_multi_fields_replaces_tags_and_others(store: TaskStore) -> None:
    """对应 BDD 场景 2：priority/deadline/tags 一起改；tags 是替换而非合并。"""
    _write_task(
        store,
        "kemu1",
        tags=["驾照", "暑假"],
        deadline="2026-08-31",
    )

    exit_code, stdout, _ = _invoke(
        "kemu1",
        "--priority", "medium",
        "--deadline", "2026-07-15",
        "--tags", "驾照",
    )

    assert exit_code == 0, f"expected 0, got {exit_code}; stdout={stdout!r}"
    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["priority"] == "medium"
    assert metadata["deadline"] == "2026-07-15"
    assert metadata["tags"] == ["驾照"]
    assert metadata["updated"] == "2026-06-21"


# ============================================================
#  Scenario 3: ID 不存在
# ============================================================


def test_update_missing_id_errors(store: TaskStore) -> None:
    """对应 BDD 场景 3：ID 不存在 → 退出码 3 + 友好提示。"""
    _write_task(store, "kemu1")  # 存在别的任务，确保不是空仓库

    exit_code, stdout, stderr = _invoke("nonexistent-id", "--status", "in_progress")

    assert exit_code == 3
    assert "❌ 任务不存在：nonexistent-id" in stderr
    assert "💡 提示" in stderr
    assert "x todo list" in stderr
    # 没有写入
    assert stdout == "" or "✅" not in stdout


# ============================================================
#  Scenario 4: 非法 status 值
# ============================================================


def test_update_invalid_status_errors(store: TaskStore) -> None:
    """对应 BDD 场景 4：--status active（非法值）→ 退出码 2 + 列出合法值。"""
    _write_task(store, "kemu1", status="pending", priority="high")

    exit_code, _stdout, stderr = _invoke("kemu1", "--status", "active")

    assert exit_code == 2
    assert "❌ 无效的 status 值" in stderr
    assert "active" in stderr
    # 列出全部合法值
    for legal in ("pending", "in_progress", "blocked", "waiting", "archived"):
        assert legal in stderr, f"legal status {legal!r} not in stderr: {stderr!r}"

    # 文件未被修改
    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["status"] == "pending"


def test_update_invalid_priority_errors(store: TaskStore) -> None:
    """对 priority 同样做合法性校验（场景 4 隐含的同类规则）。"""
    _write_task(store, "kemu1")

    exit_code, _, stderr = _invoke("kemu1", "--priority", "urgent")

    assert exit_code == 2
    assert "❌ 无效的 priority 值" in stderr
    assert "urgent" in stderr
    for legal in ("high", "medium", "low"):
        assert legal in stderr


# ============================================================
#  Scenario 5: 清除 deadline（边界）
# ============================================================


def test_update_clear_deadline_via_empty_string(store: TaskStore) -> None:
    """对应 BDD 场景 5：--deadline "" 显式清除（不是设为空字符串，是删除字段）。"""
    _write_task(store, "kemu1", deadline="2026-08-31")

    exit_code, _stdout, stderr = _invoke("kemu1", "--deadline", "")

    assert exit_code == 0, f"stderr={stderr!r}"

    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert "deadline" not in metadata
    assert metadata["updated"] == "2026-06-21"


# ============================================================
#  Scenario 6: 保留未知字段（关键兼容性）
# ============================================================


def test_update_preserves_unknown_fields(store: TaskStore) -> None:
    """对应 BDD 场景 6：paused_at / description / pause_reason 必须保留。"""
    _write_task(
        store,
        "kemu1",
        extra={
            "description": "科目一学时已刷完",
            "paused_at": "2026-06-13",
            "pause_reason": "用户 6/13 01:11 「不刷题了，长期规划中」",
        },
    )

    exit_code, _stdout, _stderr = _invoke("kemu1", "--status", "in_progress")

    assert exit_code == 0

    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["description"] == "科目一学时已刷完"
    assert metadata["paused_at"] == "2026-06-13"
    assert metadata["pause_reason"] == "用户 6/13 01:11 「不刷题了，长期规划中」"
    # 同时也确认更新生效
    assert metadata["status"] == "in_progress"


# ============================================================
#  Scenario 7: 更新已归档任务
# ============================================================


def test_update_archived_task_errors(store: TaskStore) -> None:
    """对应 BDD 场景 7：归档任务不可更新（需先 restore）→ 退出码 4。"""
    _write_task(
        store,
        "xiangjifanmai",
        task_id="20260521-xiangjifanmai",
        archived=True,
        archive_date="20260521",
    )

    exit_code, _stdout, stderr = _invoke("20260521-xiangjifanmai", "--priority", "high")

    assert exit_code == 4
    assert "❌ 已归档任务不可更新" in stderr
    assert "20260521-xiangjifanmai" in stderr
    assert "💡" in stderr
    assert "restore" in stderr.lower()


# ============================================================
#  Scenario 8: 无任何选项（argparse 报错）
# ============================================================


def test_update_no_options_errors() -> None:
    """对应 BDD 场景 8：x todo update <id> 不带任何 --xxx → argparse 报错退出码 2。"""
    # argparse 自己会调 parser.error()，触发 SystemExit(2)
    with pytest.raises(SystemExit) as exc_info:
        main(["todo", "update", "kemu1"])
    assert exc_info.value.code == 2
    # 错误信息通过 stderr；通过 capsys 验证在 pytest 的另一处检查
    # 这里只验证退出码符合 BDD（场景 8 写「如 2」）。


def test_update_no_options_error_message_via_capsys(
    store: TaskStore, capsys: pytest.CaptureFixture
) -> None:
    """对应 BDD 场景 8：标准错误里要出现「至少一个选项」的提示文本。"""
    _write_task(store, "kemu1")
    with pytest.raises(SystemExit) as exc_info:
        main(["todo", "update", "kemu1"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "at least one of --status / --priority / --deadline / --tags is required" in captured.err


# ============================================================
#  End-to-end: 通过 main() 走完整路径（保证 argparse 接线正确）
# ============================================================


def test_update_e2e_via_main(store: TaskStore) -> None:
    """端到端：x todo update <id> --priority medium（覆盖 CLI 接线）。"""
    _write_task(store, "kemu1", priority="high")

    exit_code, stdout, _stderr = _invoke("kemu1", "--priority", "medium")

    assert exit_code == 0
    assert "✅" in stdout
    assert "kemu1" in stdout

    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["priority"] == "medium"


def test_update_real_today_used_when_no_today_override(store: TaskStore) -> None:
    """当不传 today 时，handler 应使用 date.today()（与 TaskStore 默认行为一致）。"""
    _write_task(store, "kemu1")

    exit_code, _, _ = _invoke("kemu1", "--priority", "high")

    assert exit_code == 0
    on_disk = (store.active_dir / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    assert metadata["updated"] == date.today().isoformat()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
