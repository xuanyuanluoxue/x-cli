"""Pure validation and presentation helpers for the ``x todo`` plugin.

This module deliberately performs no filesystem access and writes nothing to
stdout/stderr. Command handlers in :mod:`plugins.todo` own side effects.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.formatting import colorize
from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.slug import compute_end_time


_STATUS_ICONS: dict[str, str] = {
    TaskStatus.PENDING.value: "⏳",
    TaskStatus.IN_PROGRESS.value: "▶",
    TaskStatus.BLOCKED.value: "⏸",
    TaskStatus.WAITING.value: "⌛",
    TaskStatus.ARCHIVED.value: "✅",
    f"{TaskStatus.ARCHIVED.value} (done)": "✅",
    f"{TaskStatus.ARCHIVED.value} (cancelled)": "🚫",
    f"{TaskStatus.ARCHIVED.value} (expired)": "⏰",
    f"{TaskStatus.ARCHIVED.value} (failed)": "❌",
}

_PRIORITY_ICONS: dict[str, str] = {
    Priority.URGENT.value: "🔥🔥",
    Priority.HIGH.value: "🔥",
    Priority.MEDIUM.value: "⚡",
    Priority.LOW.value: "🐢",
}

_PRIORITY_SORT_WEIGHT: dict[str, int] = {
    Priority.URGENT.value: 0,
    Priority.HIGH.value: 1,
    Priority.MEDIUM.value: 2,
    Priority.LOW.value: 3,
}

_VALID_STATUS_HINT = " / ".join(status.value for status in TaskStatus)
_VALID_PRIORITY_HINT = " / ".join(priority.value for priority in Priority)


def _coerce_status(raw: str) -> TaskStatus:
    """Convert a CLI status value or raise the canonical user-facing error."""
    try:
        return TaskStatus(raw)
    except ValueError:
        raise ValueError(
            f"❌ 无效的 status 值：{raw}（合法值：{_VALID_STATUS_HINT}）"
        )


def _coerce_priority(raw: str) -> Priority:
    """Convert a CLI priority value or raise the canonical user-facing error."""
    try:
        return Priority(raw)
    except ValueError:
        raise ValueError(
            f"❌ 无效的 priority 值：{raw}（合法值：{_VALID_PRIORITY_HINT}）"
        )


def _list_status_cell(task: Task) -> str:
    """Return the status table cell, including archive reason and icon."""
    status_value = (
        task.status.value
        if isinstance(task.status, TaskStatus)
        else str(task.status)
    )
    if status_value == TaskStatus.ARCHIVED.value and task.reason is not None:
        reason_value = (
            task.reason.value
            if isinstance(task.reason, ArchiveReason)
            else str(task.reason)
        )
        cell = f"{status_value} ({reason_value})"
    else:
        cell = status_value
    icon = _STATUS_ICONS.get(cell, "")
    return f"{icon} {cell}" if icon else cell


def _list_priority_cell(
    task: Task,
    *,
    color_enabled: bool | None = None,
) -> str:
    """Return the priority table cell, optionally coloring urgent tasks."""
    cell = (
        task.priority.value
        if isinstance(task.priority, Priority)
        else str(task.priority)
    )
    icon = _PRIORITY_ICONS.get(cell, "")
    text = f"{icon} {cell}" if icon else cell
    if cell == Priority.URGENT.value:
        return colorize(text, "red", enabled=color_enabled)
    return text


def _list_time_cell(task: Task) -> str:
    """Return the canonical list time cell."""
    start = task.time or ""
    end = getattr(task, "end_time", None)
    duration_min = getattr(task, "duration_min", None)
    if not start:
        return "-"
    if end:
        return f"{start}-{end}"
    if duration_min is not None:
        return f"{start}-{compute_end_time(start, duration_min)}"
    return start


def _list_name_cell(task: Task, *, has_unfulfilled_dep: bool) -> str:
    """Return the task name, adding a lock for unfulfilled dependencies."""
    name = task.name or ""
    return f"🔒 {name}" if has_unfulfilled_dep else name


def _make_priority_cell(color_enabled: bool | None) -> Callable[[Task], str]:
    return lambda task: _list_priority_cell(task, color_enabled=color_enabled)


_LIST_COLUMNS_TEMPLATE: Callable[
    [bool | None],
    tuple[tuple[str, Callable[[Task], str]], ...],
] = lambda color_enabled: (
    ("ID", lambda task: task.id or task.name),
    ("Name", lambda task: task.name),
    ("Status", _list_status_cell),
    ("Priority", _make_priority_cell(color_enabled)),
    ("Deadline", lambda task: task.deadline or "-"),
    ("Time", _list_time_cell),
)

_LIST_COLUMNS = _LIST_COLUMNS_TEMPLATE(None)


def _matches_list_filters(
    task: Task,
    *,
    status: TaskStatus | None,
    priority: Priority | None,
    tag: str | None,
) -> bool:
    """Return whether a task satisfies all active list filters."""
    if status is not None and task.status != status:
        return False
    if priority is not None and task.priority != priority:
        return False
    if tag is not None and tag not in (task.tags or []):
        return False
    return True


def _render_auto_archive_summary(archived: list[Task]) -> str:
    """Render the optional one-line automatic archive summary."""
    if not archived:
        return ""
    ids = " / ".join(task.id for task in archived)
    return f"⏰ 自动归档 {len(archived)} 个逾期任务：{ids}\n"


def _compute_tree_indent(tasks: list[Task]) -> dict[str, str]:
    """Return a task-id to indentation-prefix mapping for tree display."""
    by_id = {task.id: task for task in tasks if task.id}
    depth: dict[str, int] = {}

    def get_depth(task_id: str | None, seen: set[str] | None = None) -> int:
        if not task_id or task_id not in by_id:
            return 0
        if seen is None:
            seen = set()
        if task_id in seen:
            return 0
        seen.add(task_id)
        if task_id in depth:
            return depth[task_id]
        parent = by_id[task_id].parent
        if not parent or parent not in by_id:
            depth[task_id] = 0
        else:
            depth[task_id] = get_depth(parent, seen) + 1
        return depth[task_id]

    result: dict[str, str] = {}
    for task in tasks:
        task_depth = get_depth(task.id)
        if task_depth == 0:
            result[task.id or ""] = ""
        elif task_depth == 1:
            result[task.id or ""] = "  └ "
        else:
            result[task.id or ""] = "    └ "
    return result


def _render_stats(stats: dict[str, Any]) -> str:
    """Format a ``TaskStore.stats()`` result into canonical CLI output."""
    lines = ["📊 TODO 统计信息", "", f"总任务数：{stats['total']}"]

    if stats["total"] > 0:
        by_status = stats["by_status"]
        for key in ("pending", "in_progress", "blocked", "waiting", "archived"):
            icon = _STATUS_ICONS.get(key, "")
            prefix = f"{icon} " if icon else "- "
            lines.append(f"{prefix}{key}：{by_status.get(key, 0)}")

    lines.extend(["", "优先级分布："])
    by_priority = stats["by_priority"]
    for key in ("high", "medium", "low"):
        icon = _PRIORITY_ICONS.get(key, "")
        prefix = f"{icon} " if icon else "- "
        lines.append(f"{prefix}{key}：{by_priority.get(key, 0)}")

    lines.extend(["", f"即将到期（7 天内）：{stats['due_within_7_days']}"])

    if stats["high_priority_active"] > 0:
        breakdown = stats["high_priority_breakdown"]
        lines.append(
            f"🔥 高优先级任务：{stats['high_priority_active']}"
            f"（⏳ pending: {breakdown.get('pending', 0)} / "
            f"▶ in_progress: {breakdown.get('in_progress', 0)}）"
        )

    remind_active = stats.get("remind_active", 0)
    if remind_active > 0:
        lines.append(f"⏰ 有提醒任务数：{remind_active}")

    return "\n".join(lines) + "\n"
