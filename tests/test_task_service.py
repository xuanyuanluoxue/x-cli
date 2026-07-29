"""Application-service contract shared by CLI and Web task adapters."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.models import ArchiveReason, Priority, TaskStatus
from core.storage import (
    TaskAlreadyArchivedError,
    TaskAlreadyExistsError,
    TaskNotFoundError,
    TaskStore,
)
from core.task_service import TaskService


@pytest.fixture
def store(tmp_path: Path) -> TaskStore:
    return TaskStore(tmp_path / "todo")


@pytest.fixture
def service(store: TaskStore) -> TaskService:
    return TaskService(store)


def test_service_uses_injected_store_for_complete_web_lifecycle(
    service: TaskService,
    store: TaskStore,
) -> None:
    assert service.store is store

    created = service.create(
        "统一后端",
        priority="high",
        deadline="2026-08-01",
        tags=["web", "cli"],
        today="2026-07-29",
    )
    assert created.id == "1"
    assert created.folder == "任务/统一后端"
    assert created.created == "2026-07-29"
    assert created.updated == "2026-07-29"
    assert created.priority is Priority.HIGH
    assert service.get(created.id, include_archived=True) == created
    assert service.list(priority="high", tag="web") == [created]

    updated = service.update(
        created.id,
        status="in_progress",
        priority="urgent",
        tags=["shared"],
        today="2026-07-30",
    )
    assert updated.status is TaskStatus.IN_PROGRESS
    assert updated.priority is Priority.URGENT
    assert updated.updated == "2026-07-30"

    archived = service.archive(created.id, reason="done")
    assert archived.status is TaskStatus.ARCHIVED
    assert archived.reason is ArchiveReason.DONE
    assert service.list() == []
    assert service.get(created.id, include_archived=True) == archived


def test_service_generates_unique_ids_and_preserves_advanced_fields(
    service: TaskService,
) -> None:
    first = service.create("A B", today="2026-07-29")
    second = service.create(
        "A-B",
        time="09:00",
        duration_min=30,
        parent=first.id,
        remind=["1h"],
        repeat={"kind": "daily"},
        depends=[first.id],
        today="2026-07-29",
    )

    assert first.id == "ab"
    assert second.id == "ab-2"
    assert second.time == "09:00"
    assert second.duration_min == 30
    assert second.parent == first.id
    assert second.remind == ["1h"]
    assert second.repeat == {"kind": "daily"}
    assert second.depends == [first.id]


def test_service_filters_and_stats(service: TaskService) -> None:
    service.create(
        "高优先级",
        priority="high",
        tags=["shared"],
        deadline="2026-07-30",
        today="2026-07-29",
    )
    service.create(
        "低优先级",
        priority="low",
        tags=["cli"],
        today="2026-07-29",
    )

    assert [task.name for task in service.list(priority="high")] == ["高优先级"]
    assert [task.name for task in service.list(tag="shared")] == ["高优先级"]
    stats = service.stats(today="2026-07-29")
    assert stats["total"] == 2
    assert stats["by_priority"]["high"] == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"priority": "invalid"}, "invalid priority"),
        ({"status": "invalid"}, "invalid status"),
        ({"tags": "not-a-list"}, "tags must be a list"),
    ],
)
def test_service_rejects_invalid_create_values(
    service: TaskService,
    kwargs: dict,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        service.create("demo", **kwargs)


def test_service_preserves_storage_domain_exceptions(
    service: TaskService,
) -> None:
    created = service.create("demo", today=date.today().isoformat())

    with pytest.raises(TaskAlreadyExistsError):
        service.create("demo")
    with pytest.raises(TaskNotFoundError):
        service.update("missing", status="pending")

    service.archive(created.id)
    with pytest.raises(TaskAlreadyArchivedError):
        service.archive(created.id)


def test_default_service_uses_configured_todo_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    todo_dir = tmp_path / "configured"
    monkeypatch.setenv("XCLI_TODO_DIR", str(todo_dir))

    service = TaskService()
    service.create("default-store", today="2026-07-29")

    assert service.store.todo_dir == todo_dir
    assert service.get("default-store") is not None
