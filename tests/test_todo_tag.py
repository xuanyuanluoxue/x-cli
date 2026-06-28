"""Tests for ``x todo tag <id> [<tag>...]`` (v0.6.0 P1).

Each test maps to a scenario in
``docs/behaviors/todo-tag-behavior.md``:

  1.  add single tag                                     → test_tag_adds_single_tag
  2.  add multiple tags                                  → test_tag_adds_multiple_tags
  3.  add existing tag (idempotent)                      → test_tag_add_existing_is_idempotent
  4.  --remove single tag                                → test_tag_remove_single
  5.  --remove multiple tags                             → test_tag_remove_multiple
  6.  --remove non-existing (idempotent)                 → test_tag_remove_nonexistent_is_idempotent
  7.  --clear all tags                                   → test_tag_clear_removes_field
  8.  --remove and --clear mutually exclusive            → test_tag_remove_and_clear_mutex
  9.  missing task id                                    → test_tag_missing_id_errors
 10.  task not found                                     → test_tag_nonexistent_task_errors
 11.  task archived                                      → test_tag_archived_task_errors
 12.  add mode without tag                               → test_tag_add_without_tag_errors
 13.  --remove mode without tag                          → test_tag_remove_without_tag_errors
 14.  preserves unknown fields                           → test_tag_preserves_unknown_fields

All tests use ``XCLI_TODO_DIR`` pointed at ``tmp_path`` so the real
``xcli_todo_dir`` is never modified.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from core.models import ArchiveReason, Priority as Prio, Task, TaskStatus
from core.parser import parse_frontmatter
from core.storage import TaskStore
from x import main


# ============================================================
#  Helpers (mirror test_todo_update pattern)
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
) -> None:
    """Drop a TODO.md on disk matching the fixture pattern from other tests."""
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
    """Call ``main`` with the given argv (relative to ``x todo tag``)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        exit_code = main(["todo", "tag", *argv])
    return exit_code, out.getvalue(), err.getvalue()


def _read_metadata(store: TaskStore, name: str) -> dict:
    """Read the YAML frontmatter from the task's TODO.md."""
    on_disk = (store.active_dir / name / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(on_disk)
    return metadata


# ============================================================
#  Scenario 1: 添加单个 tag
# ============================================================


def test_tag_adds_single_tag(store: TaskStore) -> None:
    """对应 BDD 场景 1：x todo tag <id> <tag> 追加单个 tag。"""
    _write_task(store, "科目一模拟考", task_id="kemu1", tags=["驾照", "暑假"])

    exit_code, stdout, stderr = _invoke("kemu1", "冲刺")

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    assert "✅" in stdout
    assert "冲刺" in stdout
    assert "kemu1" in stdout

    metadata = _read_metadata(store, "科目一模拟考")
    assert metadata["tags"] == ["驾照", "暑假", "冲刺"]


# ============================================================
#  Scenario 2: 一次性添加多个 tag
# ============================================================


def test_tag_adds_multiple_tags(store: TaskStore) -> None:
    """对应 BDD 场景 2：x todo tag <id> <tag1> <tag2> ... 一次性添加。"""
    _write_task(store, "kemu1", tags=["驾照"])

    exit_code, stdout, stderr = _invoke("kemu1", "暑假", "冲刺", "高频错题")

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    assert "3" in stdout  # 报告添加 3 个

    metadata = _read_metadata(store, "kemu1")
    assert metadata["tags"] == ["驾照", "暑假", "冲刺", "高频错题"]


# ============================================================
#  Scenario 3: 已存在 tag 幂等
# ============================================================


def test_tag_add_existing_is_idempotent(store: TaskStore) -> None:
    """对应 BDD 场景 3：已存在的 tag 不重复加；只报告实际新增数。"""
    _write_task(store, "kemu1", tags=["驾照", "暑假"])

    exit_code, stdout, _ = _invoke("kemu1", "驾照", "冲刺")

    assert exit_code == 0
    assert "1" in stdout  # 报告添加 1 个（不是 2）

    metadata = _read_metadata(store, "kemu1")
    assert metadata["tags"] == ["驾照", "暑假", "冲刺"]  # 不重复


# ============================================================
#  Scenario 4: 移除单个 tag
# ============================================================


def test_tag_remove_single(store: TaskStore) -> None:
    """对应 BDD 场景 4：--remove <id> <tag> 移除单个 tag。"""
    _write_task(store, "kemu1", tags=["驾照", "暑假", "冲刺"])

    exit_code, stdout, _ = _invoke("--remove", "kemu1", "暑假")

    assert exit_code == 0
    assert "暑假" in stdout

    metadata = _read_metadata(store, "kemu1")
    assert metadata["tags"] == ["驾照", "冲刺"]


# ============================================================
#  Scenario 5: 移除多个 tag
# ============================================================


def test_tag_remove_multiple(store: TaskStore) -> None:
    """对应 BDD 场景 5：--remove 多个 tag。"""
    _write_task(store, "kemu1", tags=["驾照", "暑假", "冲刺", "高频错题"])

    exit_code, _stdout, _ = _invoke("--remove", "kemu1", "暑假", "冲刺")

    assert exit_code == 0
    metadata = _read_metadata(store, "kemu1")
    assert metadata["tags"] == ["驾照", "高频错题"]


# ============================================================
#  Scenario 6: 移除不存在的 tag 幂等
# ============================================================


def test_tag_remove_nonexistent_is_idempotent(store: TaskStore) -> None:
    """对应 BDD 场景 6：移除不存在的 tag 不报错，报告 0 移除。"""
    _write_task(store, "kemu1", tags=["驾照", "暑假"])

    exit_code, stdout, _ = _invoke("--remove", "kemu1", "不存在", "已移除")

    assert exit_code == 0
    assert "0" in stdout  # 报告 0 移除

    metadata = _read_metadata(store, "kemu1")
    assert metadata["tags"] == ["驾照", "暑假"]  # 未变


# ============================================================
#  Scenario 7: 清空所有 tag
# ============================================================


def test_tag_clear_removes_field(store: TaskStore) -> None:
    """对应 BDD 场景 7：--clear 删 tags 字段（不写 tags: []）。"""
    _write_task(store, "kemu1", tags=["驾照", "暑假", "冲刺"])

    exit_code, _stdout, _ = _invoke("--clear", "kemu1")

    assert exit_code == 0
    # 字段从 frontmatter 中完全删除
    assert "tags" not in _read_metadata(store, "kemu1")


# ============================================================
#  Scenario 8: --remove 与 --clear 互斥
# ============================================================


def test_tag_remove_and_clear_mutex(store: TaskStore) -> None:
    """对应 BDD 场景 8：--remove 与 --clear 同时给 → exit 2 + 互斥提示。"""
    _write_task(store, "kemu1", tags=["驾照"])

    exit_code, _stdout, stderr = _invoke("--remove", "--clear", "kemu1", "暑假")

    assert exit_code == 2
    assert "互斥" in stderr
    # 文件未变
    assert _read_metadata(store, "kemu1")["tags"] == ["驾照"]


# ============================================================
#  Scenario 9: 缺任务 ID
# ============================================================


def test_tag_missing_id_errors(store: TaskStore) -> None:
    """对应 BDD 场景 12：x todo tag（完全无参数）→ exit 2 + 缺 id 提示。

    注：argparse 用 ``nargs="?"`` 让 id 可选，所以 ``x todo tag 冲刺``
    会被解释成 ``id="冲刺", tags=[]``，触发"缺 tag"分支（场景 13）。
    本测试覆盖"完全无参数"的场景。
    """
    exit_code, _stdout, stderr = _invoke()

    assert exit_code == 2
    assert "缺少任务 ID" in stderr


# ============================================================
#  Scenario 10: 任务不存在
# ============================================================


def test_tag_nonexistent_task_errors(store: TaskStore) -> None:
    """对应 BDD 场景 10：x todo tag <unknown-id> <tag> → exit 3。"""
    _write_task(store, "kemu1")  # 仓库非空

    exit_code, _stdout, stderr = _invoke("nonexistent-id", "冲刺")

    assert exit_code == 3
    assert "❌ 任务不存在" in stderr
    assert "nonexistent-id" in stderr
    assert "x todo list" in stderr


# ============================================================
#  Scenario 11: 任务已归档
# ============================================================


def test_tag_archived_task_errors(store: TaskStore) -> None:
    """对应 BDD 场景 11：归档任务不可 tag → exit 4 + 提示用 restore。"""
    _write_task(
        store,
        "xiangjifanmai",
        task_id="20260521-xiangjifanmai",
        tags=["旧标签"],
        archived=True,
        archive_date="20260521",
    )

    exit_code, _stdout, stderr = _invoke("20260521-xiangjifanmai", "新标签")

    assert exit_code == 4
    assert "❌" in stderr
    assert "归档" in stderr
    assert "restore" in stderr.lower()


# ============================================================
#  Scenario 12: 添加模式缺 tag
# ============================================================


def test_tag_add_without_tag_errors(store: TaskStore) -> None:
    """对应 BDD 场景 13：x todo tag <id> 没 tag → exit 2。"""
    _write_task(store, "kemu1")

    exit_code, _stdout, stderr = _invoke("kemu1")

    assert exit_code == 2
    assert "至少指定一个 tag" in stderr


# ============================================================
#  Scenario 13: --remove 模式缺 tag
# ============================================================


def test_tag_remove_without_tag_errors(store: TaskStore) -> None:
    """对应 BDD 场景 14：x todo tag --remove <id> 没 tag → exit 2。"""
    _write_task(store, "kemu1")

    exit_code, _stdout, stderr = _invoke("--remove", "kemu1")

    assert exit_code == 2
    assert "至少指定一个 tag" in stderr
    assert "--remove" in stderr


# ============================================================
#  Scenario 14: 保留未知字段
# ============================================================


def test_tag_preserves_unknown_fields(store: TaskStore) -> None:
    """对应 BDD 场景 15：tag 操作不破坏 description / paused_at 等未知字段。"""
    _write_task(
        store,
        "kemu1",
        tags=["驾照"],
        extra={
            "description": "用户写的长文",
            "paused_at": "2026-05-10",
            "pause_reason": "用户主动暂停",
        },
    )

    exit_code, _stdout, _ = _invoke("kemu1", "冲刺")

    assert exit_code == 0
    metadata = _read_metadata(store, "kemu1")
    assert metadata["tags"] == ["驾照", "冲刺"]
    # 未知字段全部保留
    assert metadata["description"] == "用户写的长文"
    assert metadata["paused_at"] == "2026-05-10"
    assert metadata["pause_reason"] == "用户主动暂停"
