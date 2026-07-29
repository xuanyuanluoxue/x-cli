"""Shared application service for CLI and Web task operations.

The service owns protocol-agnostic task defaults, construction, filtering and
storage orchestration. CLI adapters retain argparse, terminal output and exit
codes; Web adapters retain HTTP parsing, status codes and JSON responses.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.slug import unique_slug, validate_deadline, validate_time
from core.storage import TaskStore


class TaskService:
    """Application API shared by the CLI and Web task adapters."""

    def __init__(self, store: TaskStore | None = None) -> None:
        self.store = store if store is not None else TaskStore()

    def list(
        self,
        *,
        include_archived: bool = False,
        status: TaskStatus | str | None = None,
        priority: Priority | str | None = None,
        tag: str | None = None,
    ) -> list[Task]:
        tasks = self.store.list_tasks(include_archived=include_archived)
        status_value = (
            _coerce_enum(status, TaskStatus, "status")
            if status is not None
            else None
        )
        priority_value = (
            _coerce_enum(priority, Priority, "priority")
            if priority is not None
            else None
        )

        if status_value is not None:
            tasks = [task for task in tasks if task.status is status_value]
        if priority_value is not None:
            tasks = [
                task for task in tasks if task.priority is priority_value
            ]
        if tag is not None:
            tasks = [
                task for task in tasks if task.tags and tag in task.tags
            ]
        return tasks

    def get(
        self,
        name_or_id: str,
        *,
        include_archived: bool = True,
    ) -> Task | None:
        return self.store.get_task(
            name_or_id,
            include_archived=include_archived,
        )

    def search(
        self,
        keyword: str,
        *,
        include_archived: bool = True,
        include_active: bool = True,
    ) -> list[Task]:
        return self.store.search_tasks(
            keyword,
            include_archived=include_archived,
            include_active=include_active,
        )

    def create(
        self,
        name: str,
        *,
        status: TaskStatus | str = TaskStatus.PENDING,
        priority: Priority | str = Priority.MEDIUM,
        deadline: str | None = None,
        tags: list[str] | None = None,
        time: str | None = None,
        end_time: str | None = None,
        duration_min: int | None = None,
        parent: str | None = None,
        remind: list[str] | None = None,
        repeat: dict[str, str] | None = None,
        depends: list[str] | None = None,
        body: str = "",
        extra: dict[str, Any] | None = None,
        today: str | None = None,
    ) -> Task:
        normalized_name = name.strip() if isinstance(name, str) else ""
        if not normalized_name:
            raise ValueError("name is required")

        status_value = _coerce_enum(status, TaskStatus, "status")
        priority_value = _coerce_enum(priority, Priority, "priority")
        _validate_optional_string_list(tags, "tags")
        _validate_optional_string_list(remind, "remind")
        _validate_optional_string_list(depends, "depends")

        if deadline is not None:
            if not isinstance(deadline, str):
                raise ValueError("deadline must be a string (YYYY-MM-DD)")
            validate_deadline(deadline)
        if time is not None:
            validate_time(time)
        if end_time is not None:
            validate_time(end_time)
        if duration_min is not None:
            if (
                not isinstance(duration_min, int)
                or isinstance(duration_min, bool)
                or duration_min <= 0
            ):
                raise ValueError("duration_min must be a positive integer")
        if end_time is not None and duration_min is not None:
            raise ValueError(
                "end_time and duration_min cannot be provided together"
            )
        if repeat is not None and not isinstance(repeat, dict):
            raise ValueError("repeat must be a mapping")
        if extra is not None and not isinstance(extra, dict):
            raise ValueError("extra must be a mapping")

        current_day = today or date.today().isoformat()
        existing_ids = {
            task.id
            for task in self.store.list_tasks(include_archived=True)
            if task.id
        }
        task_id = unique_slug(normalized_name, existing_ids)
        task = Task(
            id=task_id,
            name=normalized_name,
            status=status_value,
            priority=priority_value,
            created=current_day,
            updated=current_day,
            deadline=deadline,
            time=time,
            end_time=end_time,
            duration_min=duration_min,
            parent=parent,
            remind=list(remind) if remind else None,
            repeat=dict(repeat) if repeat else None,
            depends=list(depends) if depends else None,
            folder=f"任务/{normalized_name}",
            tags=list(tags) if tags else None,
            body=body,
            extra=dict(extra) if extra else {},
        )
        self.store.add_task(task)
        return task

    def update(self, name_or_id: str, **changes: Any) -> Task:
        if "status" in changes and changes["status"] is not None:
            changes["status"] = _coerce_enum(
                changes["status"],
                TaskStatus,
                "status",
            )
        if "priority" in changes and changes["priority"] is not None:
            changes["priority"] = _coerce_enum(
                changes["priority"],
                Priority,
                "priority",
            )
        if "deadline" in changes and changes["deadline"] is not None:
            deadline = changes["deadline"]
            if not isinstance(deadline, str):
                raise ValueError(
                    "deadline must be a string (YYYY-MM-DD)"
                )
            validate_deadline(deadline)
        if "tags" in changes:
            _validate_optional_string_list(changes["tags"], "tags")
        return self.store.update_task(name_or_id, **changes)

    def archive(
        self,
        name_or_id: str,
        *,
        reason: ArchiveReason | str | None = None,
    ) -> Task:
        reason_value = (
            ArchiveReason.DONE
            if reason is None
            else _coerce_enum(reason, ArchiveReason, "reason")
        )
        return self.store.archive_task(name_or_id, reason=reason_value)

    def restore(
        self,
        name_or_id: str,
        *,
        target_status: TaskStatus | str | None = None,
        dry_run: bool = False,
        today: str | None = None,
    ) -> Task:
        status_value = (
            _coerce_enum(target_status, TaskStatus, "status")
            if target_status is not None
            else None
        )
        return self.store.restore_task(
            name_or_id,
            target_status=status_value,
            dry_run=dry_run,
            today=today,
        )

    def remove(
        self,
        name_or_id: str,
        *,
        force: bool = False,
    ) -> tuple[Task, bool]:
        return self.store.remove_task(name_or_id, force=force)

    def find_overdue(self, today: date | str | None = None) -> list[Task]:
        return self.store.find_overdue_tasks(today=today)

    def stats(self, *, today: str | None = None) -> dict[str, Any]:
        return self.store.stats(today=today)


def _coerce_enum(value: Any, enum_cls: type, field_name: str):
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc


def _validate_optional_string_list(
    value: list[str] | None,
    field_name: str,
) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} entries must be strings")
