"""Tests for core/models.py — Task dataclass + enums."""

from __future__ import annotations

import sys
from datetime import date

import pytest

from core.models import (
    ArchiveReason,
    Priority,
    Task,
    TaskStatus,
)
from core.parser import dump_frontmatter, parse_frontmatter


# ============================================================
#  Enum basics
# ============================================================


def test_task_status_values():
    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.IN_PROGRESS == "in_progress"
    assert TaskStatus.BLOCKED == "blocked"
    assert TaskStatus.WAITING == "waiting"
    assert TaskStatus.ARCHIVED == "archived"


def test_priority_values():
    assert Priority.HIGH == "high"
    assert Priority.MEDIUM == "medium"
    assert Priority.LOW == "low"


def test_archive_reason_values():
    assert ArchiveReason.DONE == "done"
    assert ArchiveReason.CANCELLED == "cancelled"
    assert ArchiveReason.EXPIRED == "expired"
    assert ArchiveReason.FAILED == "failed"


def test_enums_are_strings():
    """StrEnum members must be usable as strings (YAML round-trip)."""
    assert isinstance(TaskStatus.PENDING, str)
    assert f"status: {TaskStatus.PENDING}" == "status: pending"
    assert Priority.HIGH + "-priority" == "high-priority"


# ============================================================
#  Task.from_frontmatter
# ============================================================


def test_task_from_minimal_frontmatter_uses_defaults():
    metadata = {"id": "t1", "name": "Task 1"}
    task = Task.from_frontmatter(metadata)
    assert task.id == "t1"
    assert task.name == "Task 1"
    assert task.status == TaskStatus.PENDING
    assert task.priority == Priority.MEDIUM
    assert task.created is None
    assert task.updated is None
    assert task.deadline is None
    assert task.folder is None
    assert task.tags is None
    assert task.subtasks is None
    assert task.reason is None
    assert task.body == ""
    assert task.extra == {}


def test_task_from_full_frontmatter():
    metadata = {
        "id": "kemu1",
        "name": "科目一",
        "status": "pending",
        "priority": "high",
        "created": "2026-03-27",
        "updated": "2026-06-13",
        "deadline": "2026-08-31",
        "folder": "任务/科目一",
        "tags": ["驾照", "暑假"],
        "subtasks": [{"id": "k1", "text": "模拟考", "done": False}],
    }
    task = Task.from_frontmatter(metadata, body="# 科目一\n")
    assert task.status is TaskStatus.PENDING
    assert task.priority is Priority.HIGH
    assert task.deadline == "2026-08-31"
    assert task.tags == ["驾照", "暑假"]
    assert task.subtasks == [{"id": "k1", "text": "模拟考", "done": False}]
    assert task.folder == "任务/科目一"
    assert task.body == "# 科目一\n"
    assert task.extra == {}


def test_task_preserves_unknown_fields_in_extra():
    metadata = {
        "id": "kemu1",
        "name": "科目一",
        "description": "自由描述",
        "paused_at": "2026-06-13",
        "pause_reason": "用户表态",
    }
    task = Task.from_frontmatter(metadata)
    assert task.extra == {
        "description": "自由描述",
        "paused_at": "2026-06-13",
        "pause_reason": "用户表态",
    }


def test_task_preserves_body_unchanged():
    body = "# 标题\n\n## 节\n\n- 项目 1\n- 项目 2\n"
    task = Task.from_frontmatter({"id": "x"}, body=body)
    assert task.body == body


def test_task_coerces_invalid_enum_value_to_raw_string():
    """An unknown status string does not crash — it's kept as-is for the
    caller to validate (matches the BDD's "invalid value" error path
    being handled at the plugin layer)."""
    metadata = {"id": "t1", "status": "weird_value"}
    task = Task.from_frontmatter(metadata)
    assert task.status == "weird_value"


# ============================================================
#  Task.to_frontmatter_body
# ============================================================


def test_task_to_frontmatter_omits_none_values():
    task = Task(id="t1", name="Task 1")
    metadata, body = task.to_frontmatter_body()
    assert "deadline" not in metadata
    assert "created" not in metadata
    assert "tags" not in metadata


def test_task_to_frontmatter_emits_enum_values_as_strings():
    task = Task(id="t1", name="t", status=TaskStatus.IN_PROGRESS, priority=Priority.HIGH)
    metadata, _ = task.to_frontmatter_body()
    assert metadata["status"] == "in_progress"
    assert metadata["priority"] == "high"


def test_task_to_frontmatter_omits_empty_tags_and_subtasks():
    task = Task(id="t1", name="t", tags=[], subtasks=[])
    metadata, _ = task.to_frontmatter_body()
    assert "tags" not in metadata
    assert "subtasks" not in metadata


def test_task_to_frontmatter_includes_extra_fields():
    task = Task(
        id="t1",
        name="t",
        extra={"paused_at": "2026-06-13", "description": "自由描述"},
    )
    metadata, _ = task.to_frontmatter_body()
    assert metadata["paused_at"] == "2026-06-13"
    assert metadata["description"] == "自由描述"


def test_task_to_frontmatter_extra_does_not_overwrite_known():
    """If an extra field happens to share a name with a known field,
    the known field wins (defensive)."""
    task = Task(id="t1", name="t", extra={"id": "WRONG"})
    metadata, _ = task.to_frontmatter_body()
    assert metadata["id"] == "t1"


# ============================================================
#  Round-trip
# ============================================================


@pytest.mark.parametrize(
    "task",
    [
        Task(id="t1", name="t"),
        Task(id="t1", name="t", status=TaskStatus.IN_PROGRESS, priority=Priority.HIGH),
        Task(id="t1", name="t", deadline="2026-08-31", tags=["a", "b"]),
        Task(
            id="t1",
            name="t",
            subtasks=[{"id": "k1", "text": "x", "done": False}],
        ),
        Task(
            id="t1",
            name="t",
            status=TaskStatus.ARCHIVED,
            reason=ArchiveReason.DONE,
        ),
        Task(
            id="kemu1",
            name="科目一",
            extra={"paused_at": "2026-06-13", "description": "free text"},
            body="# 科目一\n\n笔记\n",
        ),
    ],
)
def test_task_round_trip_via_markdown(task: Task):
    """Render to markdown, parse back, expect an equal Task."""
    text = task.to_markdown()
    metadata, body = parse_frontmatter(text)
    task2 = Task.from_frontmatter(metadata, body=body)
    assert task2 == task


def test_task_to_markdown_produces_valid_yaml_frontmatter():
    task = Task(
        id="t1",
        name="任务一",
        status=TaskStatus.PENDING,
        priority=Priority.MEDIUM,
    )
    text = task.to_markdown()
    assert text.startswith("---\n")
    assert "\n---\n" in text
    metadata, _ = parse_frontmatter(text)
    assert metadata["id"] == "t1"
    assert metadata["name"] == "任务一"


def test_task_round_trip_real_sample_preserves_unknown_fields():
    """The real 科目一 TODO.md must survive Task.from_frontmatter → to_markdown
    → Task.from_frontmatter with all unknown fields intact."""
    import os

    sample = r"C:\Users\Chatxavier\.xavier\TODO\任务\科目一\TODO.md"
    if not os.path.exists(sample):
        pytest.skip(f"sample file not available: {sample}")
    text = open(sample, encoding="utf-8").read()
    metadata, body = parse_frontmatter(text)
    task1 = Task.from_frontmatter(metadata, body=body)

    # All known fields captured
    assert task1.id == "kemu1"
    assert task1.status is TaskStatus.PENDING
    assert task1.priority is Priority.HIGH

    # Unknown fields land in extra
    assert task1.extra.get("paused_at") == "2026-06-13"
    assert "不刷题了" in task1.extra.get("pause_reason", "")

    # Round-trip back
    text2 = task1.to_markdown()
    metadata2, body2 = parse_frontmatter(text2)
    task2 = Task.from_frontmatter(metadata2, body=body2)
    assert task2 == task1


# ============================================================
#  Task.folder_path
# ============================================================


def test_folder_path_relative_to_base():
    from pathlib import Path

    task = Task(id="t1", name="科目一", folder="任务/科目一")
    path = task.folder_path(base=Path("/tmp/x"))
    assert path == Path("/tmp/x/任务/科目一")


def test_folder_path_absolute_ignores_base():
    from pathlib import Path

    task = Task(id="t1", name="t", folder=r"C:\abs\path")
    path = task.folder_path(base=Path("/tmp/x"))
    assert path == Path(r"C:\abs\path")


def test_folder_path_without_base_returns_just_folder():
    from pathlib import Path

    task = Task(id="t1", name="t", folder="任务/科目一")
    path = task.folder_path()
    assert path == Path("任务/科目一")


def test_folder_path_raises_when_folder_not_set():
    task = Task(id="t1", name="t")
    with pytest.raises(ValueError, match="no folder"):
        task.folder_path()


# ============================================================
#  Default body handling
# ============================================================


def test_default_body_is_empty_string():
    task = Task(id="t1", name="t")
    assert task.body == ""


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
