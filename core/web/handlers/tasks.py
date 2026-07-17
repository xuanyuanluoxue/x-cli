"""core.web.handlers.tasks — task CRUD REST handlers.

Routes handled here:
    GET    /api/tasks          — list with optional filters
    POST   /api/tasks          — create
    GET    /api/tasks/<id>     — get one
    PATCH  /api/tasks/<id>     — update fields
    POST   /api/tasks/<id>/archive  — archive
    GET    /api/tasks/stats    — summary stats

The handlers translate :class:`Task` objects (from :mod:`core.models`)
into plain JSON dicts — keeping the on-disk schema separate from the
wire format so we can evolve them independently.
"""

from __future__ import annotations

from datetime import date
from http import HTTPStatus

from core.web.response import error_response, json_response, read_json_body


# ============================================================
#  Task <-> JSON converters
# ============================================================


def _task_to_dict(task) -> dict:
    """Convert :class:`core.models.Task` → JSON-friendly dict."""
    return {
        "id": task.id,
        "name": task.name,
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "priority": task.priority.value if hasattr(task.priority, "value") else str(task.priority),
        "deadline": task.deadline,
        "tags": list(task.tags) if task.tags else [],
        "created": task.created,
        "updated": task.updated,
        "folder": task.folder,
        "archived": (
            task.status.value == "archived" if hasattr(task.status, "value") else False
        ),
        "reason": task.reason.value if task.reason and hasattr(task.reason, "value") else task.reason,
    }


def _parse_status(value: str) -> str:
    from core.models import TaskStatus

    try:
        return TaskStatus(value).value
    except ValueError as exc:
        raise ValueError(f"invalid status: {value!r}") from exc


def _parse_priority(value: str) -> str:
    from core.models import Priority

    try:
        return Priority(value).value
    except ValueError as exc:
        raise ValueError(f"invalid priority: {value!r}") from exc


def _parse_archive_reason(value: str | None) -> str:
    from core.models import ArchiveReason

    if value is None:
        return ArchiveReason.DONE.value
    try:
        return ArchiveReason(value).value
    except ValueError as exc:
        raise ValueError(f"invalid reason: {value!r}") from exc


def _coerce_status(value):
    """Convert str to TaskStatus enum, or pass through enum."""
    from core.models import TaskStatus

    if isinstance(value, TaskStatus):
        return value
    return TaskStatus(value)


def _coerce_priority(value):
    from core.models import Priority

    if isinstance(value, Priority):
        return value
    return Priority(value)


# ============================================================
#  /api/tasks  collection
# ============================================================


def handle_tasks_collection(handler, action: str) -> None:
    if action == "list":
        _list_tasks(handler)
    elif action == "create":
        _create_task(handler)
    else:  # pragma: no cover
        error_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", f"unknown action {action}")


def _list_tasks(handler) -> None:
    qs = _parse_query(handler.path)
    include_archived = qs.get("include_archived", ["false"])[0].lower() == "true"

    status_filter = qs.get("status", [None])[0]
    priority_filter = qs.get("priority", [None])[0]
    tag_filter = qs.get("tag", [None])[0]

    store = handler.server.store
    tasks = store.list_tasks(include_archived=include_archived)

    if status_filter:
        try:
            status_val = _parse_status(status_filter)
        except ValueError as exc:
            error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", str(exc))
            return
        tasks = [t for t in tasks if t.status.value == status_val]
    if priority_filter:
        try:
            prio_val = _parse_priority(priority_filter)
        except ValueError as exc:
            error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", str(exc))
            return
        tasks = [t for t in tasks if t.priority.value == prio_val]
    if tag_filter:
        tasks = [t for t in tasks if t.tags and tag_filter in t.tags]

    json_response(
        handler,
        HTTPStatus.OK,
        {
            "tasks": [_task_to_dict(t) for t in tasks],
            "count": len(tasks),
        },
    )


def _create_task(handler) -> None:
    from core.models import Priority, Task, TaskStatus
    from core.storage import TaskAlreadyExistsError
    from core.slug import unique_slug

    body, err = read_json_body(handler)
    if err == "empty_body":
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "request body required")
        return
    if err == "invalid_json":
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "invalid JSON body")
        return
    assert body is not None

    name = (body.get("name") or "").strip()
    if not name:
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "name is required")
        return

    priority_str = body.get("priority", "medium")
    try:
        priority_val = _parse_priority(priority_str)
    except ValueError as exc:
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", str(exc))
        return

    deadline = body.get("deadline")
    if deadline is not None and not isinstance(deadline, str):
        error_response(
            handler,
            HTTPStatus.BAD_REQUEST,
            "validation_error",
            "deadline must be a string (YYYY-MM-DD)",
        )
        return

    tags = body.get("tags") or []
    if not isinstance(tags, list):
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "tags must be a list")
        return

    today = date.today().isoformat()
    store = handler.server.store

    existing_ids = {t.id for t in store.list_tasks(include_archived=True) if t.id}
    task_id = unique_slug(name, existing_ids)

    task = Task(
        id=task_id,
        name=name,
        status=TaskStatus.PENDING,
        priority=Priority(priority_val),
        created=today,
        updated=today,
        deadline=deadline,
        folder=f"任务/{name}",
        tags=tags if tags else None,
    )

    try:
        store.add_task(task)
    except TaskAlreadyExistsError as exc:
        error_response(
            handler,
            HTTPStatus.CONFLICT,
            "duplicate",
            f"task already exists: {name}",
            name=name,
        )
        return
    except ValueError as exc:
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", str(exc))
        return

    json_response(handler, HTTPStatus.CREATED, {"task": _task_to_dict(task)})


# ============================================================
#  /api/tasks/<id>  item
# ============================================================


def handle_task_item(handler, task_id: str, action: str) -> None:
    if action == "get":
        _get_task(handler, task_id)
    elif action == "update":
        _update_task(handler, task_id)
    else:  # pragma: no cover
        error_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", f"unknown action {action}")


def _get_task(handler, task_id: str) -> None:
    store = handler.server.store
    task = store.get_task(task_id, include_archived=True)
    if task is None:
        error_response(handler, HTTPStatus.NOT_FOUND, "not_found", f"task not found: {task_id}", id=task_id)
        return
    json_response(handler, HTTPStatus.OK, {"task": _task_to_dict(task)})


def _update_task(handler, task_id: str) -> None:
    from core.storage import TaskAlreadyArchivedError, TaskNotFoundError

    body, err = read_json_body(handler)
    if err == "empty_body":
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "request body required")
        return
    if err == "invalid_json":
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "invalid JSON body")
        return
    assert body is not None
    if not body:
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "at least one field required")
        return

    kwargs: dict = {}
    if "status" in body:
        try:
            kwargs["status"] = _parse_status(body["status"])
        except ValueError as exc:
            error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", str(exc))
            return
    if "priority" in body:
        try:
            kwargs["priority"] = _parse_priority(body["priority"])
        except ValueError as exc:
            error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", str(exc))
            return
    if "deadline" in body:
        if body["deadline"] is None:
            kwargs["clear_deadline"] = True
        else:
            kwargs["deadline"] = body["deadline"]
    if "tags" in body:
        kwargs["tags"] = body["tags"]

    store = handler.server.store
    try:
        task = store.update_task(task_id, **kwargs)
    except TaskNotFoundError as exc:
        error_response(handler, HTTPStatus.NOT_FOUND, "not_found", str(exc), id=task_id)
        return
    except TaskAlreadyArchivedError as exc:
        error_response(
            handler,
            HTTPStatus.CONFLICT,
            "duplicate",
            f"task already archived: {task_id}",
            id=task_id,
        )
        return
    except ValueError as exc:
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", str(exc))
        return

    json_response(handler, HTTPStatus.OK, {"task": _task_to_dict(task)})


def handle_task_archive(handler, task_id: str) -> None:
    from core.models import ArchiveReason
    from core.storage import TaskAlreadyArchivedError, TaskNotFoundError

    body: dict = {}
    raw, err = read_json_body(handler)
    if err is None and raw is not None:
        body = raw

    reason_str = body.get("reason") if body else None
    try:
        reason_val = _parse_archive_reason(reason_str)
    except ValueError as exc:
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", str(exc))
        return

    store = handler.server.store
    try:
        task = store.archive_task(task_id, reason=ArchiveReason(reason_val))
    except TaskNotFoundError:
        error_response(handler, HTTPStatus.NOT_FOUND, "not_found", f"task not found: {task_id}", id=task_id)
        return
    except TaskAlreadyArchivedError:
        error_response(
            handler,
            HTTPStatus.CONFLICT,
            "duplicate",
            f"task already archived: {task_id}",
            id=task_id,
        )
        return
    except ValueError as exc:
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", str(exc))
        return

    json_response(handler, HTTPStatus.OK, {"task": _task_to_dict(task)})


def handle_tasks_stats(handler) -> None:
    store = handler.server.store
    stats = store.stats()
    json_response(handler, HTTPStatus.OK, stats)


# ============================================================
#  Query string parser
# ============================================================


def _parse_query(path: str) -> dict[str, list[str]]:
    if "?" not in path:
        return {}
    qs = path.split("?", 1)[1]
    out: dict[str, list[str]] = {}
    for pair in qs.split("&"):
        if not pair:
            continue
        if "=" in pair:
            k, v = pair.split("=", 1)
            out.setdefault(k, []).append(v)
        else:
            out.setdefault(pair, []).append("")
    return out