"""x - Xavier 个人工具集的统一 CLI 入口

Phase 1 (MVP): 单文件实现，主入口 + x todo 子命令（待实现）。
Phase 4: 拆出 plugins/ 目录，每个子命令独立文件。
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path
from typing import Any, Callable, Sequence

from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.parser import parse_frontmatter
from core.slug import parse_tags, slugify, unique_slug, validate_deadline
from core.storage import (
    TaskAlreadyArchivedError,
    TaskAlreadyExistsError,
    TaskNotFoundError,
    TaskStore,
)

__version__ = "0.2.0"


# ============================================================
#  Visualization helpers (CJK-aware table rendering + icons)
# ============================================================


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
    Priority.HIGH.value: "🔥",
    Priority.MEDIUM.value: "⚡",
    Priority.LOW.value: "🐢",
}


def _display_width(s: str) -> int:
    """Monospace display width of ``s`` (CJK / emoji = 2, ASCII = 1).

    Uses :func:`unicodedata.east_asian_width` to decide width:
    * ``W`` (Wide) / ``F`` (Fullwidth) -> 2 cells
    * ``H`` (Halfwidth) / ``Na`` (Narrow) / ``A`` (Ambiguous) -> 1 cell

    Tab / newline are treated as 0 so they don't break padding.
    """
    width = 0
    for ch in s:
        if ch in ("\t", "\n", "\r"):
            continue
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def _pad(s: str, width: int) -> str:
    """Right-pad ``s`` so its display width is at least ``width``.

    Adds the minimum number of spaces to reach the requested display
    width. Useful for monospace table alignment with mixed ASCII + CJK.
    """
    pad_count = max(0, width - _display_width(s))
    return s + " " * pad_count


# ============================================================
#  x todo 命令实现（MVP 阶段 inline 在主入口）
# ============================================================

TODO_ACTIONS: tuple[str, ...] = ("list", "add", "update", "archive", "stats")


def _todo_register(parser: argparse.ArgumentParser) -> None:
    """注册 x todo 的子命令参数

    ``add`` / ``archive`` / ``update`` / ``list`` 子命令带自己的参数；
    其它子命令仍是占位（Phase 1 MVP 阶段后续实现）。
    """
    sub = parser.add_subparsers(dest="todo_action", required=False, metavar="ACTION")
    for name in TODO_ACTIONS:
        if name == "archive":
            sp = sub.add_parser(name, help="归档任务")
            sp.add_argument("id", help="任务 ID 或活动名称")
            sp.add_argument(
                "--reason",
                default="done",
                help="归档原因（done / cancelled / expired / failed），默认 done",
            )
        elif name == "update":
            # BDD: docs/behaviors/todo-update-behavior.md §场景 1-8
            sp = sub.add_parser(name, help="更新任务")
            sp.add_argument("id", help="任务 ID（或 active 状态下的任务名）")
            sp.add_argument(
                "--status",
                help="新状态（pending / in_progress / blocked / waiting / archived）",
            )
            sp.add_argument(
                "--priority",
                help="新优先级（high / medium / low）",
            )
            sp.add_argument(
                "--deadline",
                help='新截止日期（YYYY-MM-DD；传 "" 显式清除）',
            )
            sp.add_argument(
                "--tags",
                help="新标签（逗号分隔；完全替换而非合并）",
            )
        elif name == "list":
            # BDD: docs/behaviors/todo-list-behavior.md §场景 1-8
            sp = sub.add_parser(name, help="列出任务")
            sp.add_argument(
                "--status",
                help="按状态过滤（pending / in_progress / blocked / waiting / archived）",
            )
            sp.add_argument(
                "--priority",
                help="按优先级过滤（high / medium / low）",
            )
            sp.add_argument(
                "--tag",
                help="按标签过滤（精确匹配 tags 列表中的任一元素）",
            )
            sp.add_argument(
                "--all",
                action="store_true",
                dest="include_archived",
                help="显示所有任务（含已归档）",
            )
        elif name == "add":
            # BDD: docs/behaviors/todo-add-behavior.md §场景 1-8
            sp = sub.add_parser(name, help="添加任务")
            sp.add_argument(
                "name",
                metavar="名称",
                help="任务名称（必填）",
            )
            sp.add_argument(
                "--priority",
                default=Priority.MEDIUM.value,
                help="优先级（high / medium / low），默认 medium",
            )
            sp.add_argument(
                "--deadline",
                help="截止日期（YYYY-MM-DD）；不传则不写入 deadline 字段",
            )
            sp.add_argument(
                "--tags",
                help="标签（逗号分隔，如 驾照,暑假）；不传则不写入 tags 字段",
            )
        elif name == "stats":
            sp = sub.add_parser(name, help="📊 统计信息")
        else:
            sp = sub.add_parser(name, help=f"{name} 命令")


def _todo_not_implemented(action: str) -> int:
    """x todo 各子命令的占位实现（Phase 1 MVP 阶段）"""
    print(f"🚧 x todo {action} 还未实现", file=sys.stderr)
    return 1


def _todo_archive(args: argparse.Namespace) -> int:
    """处理 x todo archive 命令（已被 _todo_run 解析过）

    对应 BDD: docs/behaviors/todo-archive-behavior.md §场景 1-8

    退出码约定：
    - 0：成功
    - 2：非法 reason
    - 3：任务不存在
    - 4：任务已归档（重复归档）
    - 5：归档目标已存在（碰撞）
    """
    name_or_id: str = args.id
    reason_str: str = args.reason or "done"

    # 1. Validate reason (BDD §场景 6)
    valid_reasons = sorted(r.value for r in ArchiveReason)
    if reason_str not in valid_reasons:
        print(
            f"❌ 无效的 reason 值：{reason_str}"
            f"（合法值：{' / '.join(valid_reasons)}）",
            file=sys.stderr,
        )
        return 2

    # 2. Pre-flight lookup so we can give precise error messages and
    #    capture the OLD status for the inventory update (the archive
    #    itself moves the task out of "active", so we need to remember
    #    what bucket to decrement).
    store = TaskStore()
    existing = store.get_task(name_or_id, include_archived=True)
    if existing is None:
        # BDD §场景 4
        print(f"❌ 任务不存在：{name_or_id}", file=sys.stderr)
        return 3
    if existing.status is TaskStatus.ARCHIVED:
        # BDD §场景 5
        folder_display = existing.folder or ""
        print(
            f"❌ 任务已归档：{name_or_id}（位于 {folder_display}）",
            file=sys.stderr,
        )
        return 4

    old_status = existing.status

    # 3. Perform the actual archive (folder move + frontmatter update)
    try:
        archived = store.archive_task(name_or_id, reason=reason_str)
    except TaskNotFoundError:
        # Race: someone else moved/deleted the file between our lookup
        # and the archive call. Treat the same as "not found".
        print(f"❌ 任务不存在：{name_or_id}", file=sys.stderr)
        return 3
    except TaskAlreadyArchivedError as exc:
        print(
            f"❌ 任务已归档：{name_or_id}（位于 {exc.folder}）",
            file=sys.stderr,
        )
        return 4
    except FileExistsError as exc:
        # Storage layer raises when a folder with the target
        # ``YYYYMMDD-<name>`` already exists. Surface a clear error.
        print(f"❌ {exc}", file=sys.stderr)
        return 5

    # 4. Update the top-level TODO.md inventory (BDD §场景 8).
    #    Best-effort: a missing or broken index is not an error —
    #    the user can regenerate it later with regen-index.ps1.
    try:
        store.update_inventory_on_archive(old_status)
    except Exception:  # noqa: BLE001 — defensive, see comment above
        pass

    # 5. Success (BDD §场景 1-3)
    print(
        f"✅ 任务已归档：{archived.name}"
        f"（ID: {archived.id}，reason={archived.reason.value}）"
    )
    return 0


def _todo_run(args: Sequence[str]) -> int:
    """x todo 入口：解析参数并分发到子命令"""
    parser = argparse.ArgumentParser(prog="x todo", description="TODO 管理")
    _todo_register(parser)
    parsed = parser.parse_args(list(args))

    if not parsed.todo_action:
        parser.print_help()
        return 0

    # x todo stats — Phase 1 已实现（action-stats task）
    if parsed.todo_action == "stats":
        # 传给 handler 的 args 需要剔除 action 名（"stats"），否则
        # handler 自己的 ArgumentParser 会把 "stats" 解释成未知位置参数。
        return _todo_stats(list(args)[1:])

    # x todo archive — Phase 1 已实现（action-archive task）
    if parsed.todo_action == "archive":
        return _todo_archive(parsed)

    # x todo update — Phase 1 已实现（action-update task）
    if parsed.todo_action == "update":
        return _todo_update(parsed)

    # x todo list — Phase 1 已实现（action-list task）
    if parsed.todo_action == "list":
        return _todo_list(parsed)

    # x todo add — Phase 1 已实现（action-add task）
    if parsed.todo_action == "add":
        return _todo_add(parsed)

    return _todo_not_implemented(parsed.todo_action)


# ============================================================
#  x todo update — 更新任务（对应 docs/behaviors/todo-update-behavior.md）
# ============================================================


def _todo_update(args: argparse.Namespace) -> int:
    """处理 ``x todo update <id> [选项]`` 命令（已被 _todo_run 解析过）。

    对应 BDD：`docs/behaviors/todo-update-behavior.md`（8 个场景）。

    退出码约定：
    - 0：成功
    - 2：非法 status / priority 值，或无任何 --xxx 选项（argparse 标准错误）
    - 3：任务不存在
    - 4：任务已归档（不可更新，需先 restore）

    未知字段保留由 TaskStore.update_task 走 Task.to_frontmatter_body()
    整 round-trip 保证（dump_frontmatter + parse_frontmatter），所以
    ``description`` / ``paused_at`` / ``pause_reason`` 等用户字段不会丢。
    """
    from datetime import date  # local import to keep module load cheap

    # BDD 场景 8：至少要有一个 --xxx 选项；用 argparse 标准错误格式
    if (
        args.status is None
        and args.priority is None
        and args.deadline is None
        and args.tags is None
    ):
        # Rebuild a parser so we can use parser.error() for consistent
        # argparse-style output ("usage: ..." + "prog: error: ...").
        parser = argparse.ArgumentParser(prog="x todo update", description="更新 TODO 任务")
        parser.add_argument("id", help="任务 ID")
        parser.add_argument("--status", help="新状态")
        parser.add_argument("--priority", help="新优先级")
        parser.add_argument("--deadline", help='新截止日期（"" 清除）')
        parser.add_argument("--tags", help="新标签")
        parser.error(
            "at least one of --status / --priority / --deadline / --tags is required"
        )
        return 2  # unreachable; parser.error() raises SystemExit(2)

    # BDD 场景 4：非法 status / priority → 退出码 2 + 列出合法值
    valid_statuses = {s.value for s in TaskStatus}
    if args.status is not None and args.status not in valid_statuses:
        hint = " / ".join(sorted(valid_statuses))
        print(
            f"❌ 无效的 status 值：{args.status}（合法值：{hint}）",
            file=sys.stderr,
        )
        return 2

    valid_priorities = {p.value for p in Priority}
    if args.priority is not None and args.priority not in valid_priorities:
        hint = " / ".join(sorted(valid_priorities))
        print(
            f"❌ 无效的 priority 值：{args.priority}（合法值：{hint}）",
            file=sys.stderr,
        )
        return 2

    # BDD 场景 5：--deadline "" 显式清除（不是设为空字符串）
    clear_deadline = args.deadline is not None and args.deadline == ""
    if args.deadline is None or clear_deadline:
        new_deadline: str | None = None
    else:
        new_deadline = args.deadline

    # tags：逗号分隔、完全替换
    if args.tags is None:
        new_tags: list[str] | None = None
    else:
        new_tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    # 写盘
    store = TaskStore()
    try:
        task = store.update_task(
            args.id,
            status=TaskStatus(args.status) if args.status else None,
            priority=Priority(args.priority) if args.priority else None,
            deadline=new_deadline,
            tags=new_tags,
            clear_deadline=clear_deadline,
            today=date.today().isoformat(),
        )
    except TaskNotFoundError:
        # BDD 场景 3
        print(f"❌ 任务不存在：{args.id}", file=sys.stderr)
        print("💡 提示：运行 'x todo list' 查看现有任务 ID", file=sys.stderr)
        return 3
    except TaskAlreadyArchivedError:
        # BDD 场景 7
        print(f"❌ 已归档任务不可更新：{args.id}", file=sys.stderr)
        print(
            "💡 如需重新激活，请先用 'x todo restore' 还原（如该命令存在）",
            file=sys.stderr,
        )
        return 4

    # BDD 场景 1/2：成功
    print(f"✅ 任务已更新：{task.name}（ID: {task.id}）")
    return 0


# ============================================================
#  x todo list — 列出任务（对应 docs/behaviors/todo-list-behavior.md）
# ============================================================

# 合法值提示（用于 BDD §场景 8 的错误信息）
_VALID_STATUS_HINT = " / ".join(s.value for s in TaskStatus)
_VALID_PRIORITY_HINT = " / ".join(p.value for p in Priority)


def _coerce_status(raw: str) -> TaskStatus:
    """把 --status 的字符串值转成 TaskStatus；非法时抛 ValueError（错误信息匹配 BDD §场景 8）。"""
    try:
        return TaskStatus(raw)
    except ValueError:
        raise ValueError(
            f"❌ 无效的 status 值：{raw}（合法值：{_VALID_STATUS_HINT}）"
        )


def _coerce_priority(raw: str) -> Priority:
    """把 --priority 的字符串值转成 Priority；非法时抛 ValueError。"""
    try:
        return Priority(raw)
    except ValueError:
        raise ValueError(
            f"❌ 无效的 priority 值：{raw}（合法值：{_VALID_PRIORITY_HINT}）"
        )


def _list_status_cell(task) -> str:
    """表格 Status 列的展示值；带图标 + 归档任务附 reason（BDD §场景 5）。"""
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


def _list_priority_cell(task) -> str:
    """表格 Priority 列的展示值；带图标。"""
    if isinstance(task.priority, Priority):
        cell = task.priority.value
    else:
        cell = str(task.priority)
    icon = _PRIORITY_ICONS.get(cell, "")
    return f"{icon} {cell}" if icon else cell


# 列表命令的列定义（表头 + 取值函数），集中维护表格 schema
_LIST_COLUMNS: tuple[tuple[str, Callable[[object], str]], ...] = (
    ("ID", lambda t: t.id or t.name),
    ("Name", lambda t: t.name),
    ("Status", _list_status_cell),
    ("Priority", _list_priority_cell),
    ("Deadline", lambda t: t.deadline or "-"),
)


def _matches_list_filters(task, *, status, priority, tag) -> bool:
    """判断 task 是否同时满足所有过滤条件（AND 关系，BDD §场景 7）。"""
    if status is not None and task.status != status:
        return False
    if priority is not None and task.priority != priority:
        return False
    if tag is not None:
        if tag not in (task.tags or []):
            return False
    return True


def _todo_list(args: argparse.Namespace) -> int:
    """``x todo list [选项]`` — 列出任务表格（已被 _todo_run 解析过）。

    对应 BDD：`docs/behaviors/todo-list-behavior.md`（8 个场景）。

    退出码：
    - 0：成功（包括空仓库/无匹配）
    - 2：非法 status / priority 值（BDD §场景 8）
    """
    # 1. 校验 --status / --priority（非法值 → 退出码 2，不打印表格）
    try:
        status = _coerce_status(args.status) if args.status else None
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        priority = _coerce_priority(args.priority) if args.priority else None
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    tag: str | None = args.tag
    include_archived: bool = bool(getattr(args, "include_archived", False))

    # 2. 取任务列表（默认不含归档；--all 包含）
    store = TaskStore()
    tasks = store.list_tasks(include_archived=include_archived)

    # 3. 应用过滤（AND 关系，BDD §场景 7）
    if status is not None or priority is not None or tag is not None:
        tasks = [
            t for t in tasks
            if _matches_list_filters(t, status=status, priority=priority, tag=tag)
        ]

    # 4. 输出
    if not tasks:
        # BDD §场景 6：空仓库 / 无匹配 → 提示信息 + 退出码 0
        print("📭 没有任务（试试 x todo add \"任务名\" 创建第一个）")
        return 0

    # 计算每列的显示宽度（取表头与所有数据行的最大值），
    # 用 display-width 而非字符数，CJK 字符按 2 宽算，确保对齐
    header_cells = [h for h, _ in _LIST_COLUMNS]
    rows: list[list[str]] = [
        [col(t) for _, col in _LIST_COLUMNS] for t in tasks
    ]
    col_widths = [
        max(
            [_display_width(header_cells[i])]
            + [_display_width(row[i]) for row in rows]
        )
        for i in range(len(_LIST_COLUMNS))
    ]

    # 表头
    print("  ".join(_pad(c, col_widths[i]) for i, c in enumerate(header_cells)))
    # 分隔线（用 ─ 增强可视化）
    print("  ".join("─" * col_widths[i] for i in range(len(_LIST_COLUMNS))))
    # 数据行
    for row in rows:
        print("  ".join(_pad(c, col_widths[i]) for i, c in enumerate(row)))
    return 0


# ============================================================
#  x todo add — 添加任务（对应 docs/behaviors/todo-add-behavior.md）
# ============================================================


def _todo_add(args: argparse.Namespace) -> int:
    """处理 ``x todo add <名称> [选项]`` 命令（已被 _todo_run 解析过）。

    对应 BDD：`docs/behaviors/todo-add-behavior.md`（8 个场景）。

    退出码约定：
    - 0：成功
    - 2：非法 deadline 格式 / 任务名为空（argparse 也会产出 2）
    - 3：任务名已存在（BDD §场景 3）

    必填字段（per TODO-SPEC §3.4）由本函数集中写入；存储层 ``add_task``
    负责落盘。未知 frontmatter 字段对新增任务天然不会写入（Task.extra
    默认空）—— 这同时满足 BDD §场景 8「不得写入未在前缀参数中出现的字段」。
    """
    from datetime import date  # local import — keep module load cheap

    name: str = (args.name or "").strip()
    if not name:
        # 理论上 argparse 必填校验会先捕获；这里作 defense-in-depth。
        print("❌ 任务名称不能为空", file=sys.stderr)
        return 2

    # BDD §场景 5：priority 必须是 high / medium / low 之一
    valid_priorities = {p.value for p in Priority}
    if args.priority not in valid_priorities:
        hint = " / ".join(sorted(valid_priorities))
        print(
            f"❌ 无效的 priority 值：{args.priority}（合法值：{hint}）",
            file=sys.stderr,
        )
        return 2

    # BDD §场景 6：deadline 必须为 YYYY-MM-DD
    deadline_str: str | None = args.deadline
    if deadline_str is not None:
        try:
            validate_deadline(deadline_str)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    # BDD §场景 2：tags 逗号分隔
    tags: list[str] | None = None
    if args.tags is not None:
        tags = parse_tags(args.tags)
        if not tags:
            # 用户传了 ``--tags ""`` 或 ``--tags ,``：视为「不写入 tags」，
            # 与「不传 --tags」保持一致（BDD §场景 7 的精神）。
            tags = None

    # 写入日期：created/updated 同为今天（YYYY-MM-DD 本地日期）。
    today = date.today().isoformat()

    # 生成 id：slugify 候选 → 检查碰撞 → 必要时追加 -2 / -3 / …
    store = TaskStore()
    existing_ids = {t.id for t in store.list_tasks(include_archived=True) if t.id}
    task_id = unique_slug(name, existing_ids)

    task = Task(
        id=task_id,
        name=name,
        status=TaskStatus.PENDING,
        priority=Priority(args.priority),
        created=today,
        updated=today,
        deadline=deadline_str,
        folder=f"任务/{name}",
        tags=tags,
    )

    # BDD §场景 3：任务名重复 → 退出码 3
    try:
        store.add_task(task)
    except TaskAlreadyExistsError as exc:
        print(
            f"❌ 任务已存在：{exc.name}"
            f"（ID: {exc.existing_id}，位于 {exc.folder}）",
            file=sys.stderr,
        )
        return 3

    # BDD §场景 1/2：成功
    print(f"✅ 任务已创建：{task.name}（ID: {task.id}）")
    return 0


# ============================================================
#  x todo stats — 仓库统计（对应 docs/behaviors/todo-stats-behavior.md）
# ============================================================


def _render_stats(stats: dict[str, Any]) -> str:
    """Format a TaskStore.stats() dict into the canonical output.

    Output format is defined by ``docs/commands.md §2.6`` and the BDD
    spec ``docs/behaviors/todo-stats-behavior.md``:

    * Status breakdown (5 lines) is omitted when ``total == 0``.
    * Priority breakdown is always printed.
    * The 🔥 high-priority breakdown is appended only when at least
      one high-priority active task exists.
    """
    lines: list[str] = []
    lines.append("📊 TODO 统计信息")
    lines.append("")
    lines.append(f"总任务数：{stats['total']}")

    if stats["total"] > 0:
        by_status = stats["by_status"]
        # 状态分布：用 list 表里同款的图标，保持视觉一致
        for key, label in (
            ("pending", "pending"),
            ("in_progress", "in_progress"),
            ("blocked", "blocked"),
            ("waiting", "waiting"),
            ("archived", "archived"),
        ):
            count = by_status.get(key, 0)
            icon = _STATUS_ICONS.get(key, "")
            prefix = f"{icon} " if icon else "- "
            lines.append(f"{prefix}{label}：{count}")

    lines.append("")
    lines.append("优先级分布：")
    by_priority = stats["by_priority"]
    for key, label in (
        ("high", "high"),
        ("medium", "medium"),
        ("low", "low"),
    ):
        count = by_priority.get(key, 0)
        icon = _PRIORITY_ICONS.get(key, "")
        prefix = f"{icon} " if icon else "- "
        lines.append(f"{prefix}{label}：{count}")

    lines.append("")
    lines.append(f"即将到期（7 天内）：{stats['due_within_7_days']}")

    if stats["high_priority_active"] > 0:
        hb = stats["high_priority_breakdown"]
        lines.append(
            f"🔥 高优先级任务：{stats['high_priority_active']}"
            f"（⏳ pending: {hb.get('pending', 0)} / "
            f"▶ in_progress: {hb.get('in_progress', 0)}）"
        )

    return "\n".join(lines) + "\n"


def _find_broken_tasks(todo_dir: Path) -> list[tuple[str, str]]:
    """Walk ``任务/`` and ``归档/`` and return ``(relative_path, error)`` for
    files whose frontmatter fails to parse.

    Returned paths are POSIX-style (forward slashes) and relative to
    ``todo_dir`` so they match the BDD example output format:

        "任务/科目一/TODO.md"

    Empty / missing directories return an empty list — they are not
    "broken", they just have no tasks yet.
    """
    broken: list[tuple[str, str]] = []
    for area_name in ("任务", "归档"):
        area = todo_dir / area_name
        if not area.is_dir():
            continue
        for child in sorted(area.iterdir()):
            if not child.is_dir():
                continue
            todo_md = child / "TODO.md"
            if not todo_md.is_file():
                continue
            try:
                parse_frontmatter(todo_md.read_text(encoding="utf-8"))
            except ValueError as exc:
                rel = todo_md.relative_to(todo_dir)
                # Normalise Windows backslashes to forward slashes
                broken.append((str(rel).replace("\\", "/"), str(exc)))
    return broken


def _todo_stats(args: Sequence[str]) -> int:
    """``x todo stats`` — print repository statistics.

    Workflow (per BDD §stats 7):

    1. Detect broken YAML files first (don't crash; just report).
    2. Compute stats from parseable tasks (best-effort).
    3. Print the formatted stats to stdout.
    4. If any broken files were found, print error lines to stderr and
       return exit code ``5`` (custom error code for "data integrity
       issues"); otherwise return ``0``.
    """
    parser = argparse.ArgumentParser(
        prog="x todo stats",
        description="统计信息（状态分布 / 优先级分布 / 即将到期）",
    )
    parser.parse_args(list(args))  # 当前不接受额外参数

    store = TaskStore()
    broken = _find_broken_tasks(store.todo_dir)

    stats = store.stats()
    sys.stdout.write(_render_stats(stats))

    if broken:
        for rel_path, err in broken:
            sys.stderr.write(
                f"❌ 解析任务失败：{rel_path}（YAML 格式错误：{err}）\n"
            )
        return 5

    return 0


# ============================================================
#  x secret 命令实现（MVP 阶段 inline 在主入口）
# ============================================================

SECRET_ACTIONS: tuple[str, ...] = (
    "list",
    "get",
    "set",
    "update",
    "rm",
    "search",
    "import",
    "export",
)


def _secret_register(parser: argparse.ArgumentParser) -> None:
    """注册 x secret 的子命令参数。

    对应 BDD：``docs/behaviors/secret-behavior.md``（17 个场景）。

    子命令：list / get / set / update / rm / search / import / export。
    所有 core.secrets / core.paths 调用都在 handler 内做 lazy import，
    保证 x.py 顶层 import 始终成功（core.secrets 正在并行实现）。
    """
    sub = parser.add_subparsers(
        dest="secret_action", required=False, metavar="ACTION"
    )

    # list — 无参数
    sub.add_parser("list", help="列出所有密钥（不显示 value）")

    # get <name> [--full]
    sp = sub.add_parser("get", help="取一个 value（支持模糊匹配）")
    sp.add_argument("name", help="密钥名（精确 / 模糊匹配）")
    sp.add_argument(
        "--full",
        action="store_true",
        help="显示完整元数据（name / category / value / note / created_at / updated_at）",
    )

    # set <name> --value <v> [--category <c>] [--note <n>]
    sp = sub.add_parser("set", help="新增条目")
    sp.add_argument("name", help="密钥名（唯一）")
    sp.add_argument("--value", required=True, help="密钥值")
    sp.add_argument(
        "--category", default="default", help="分类（默认 default）"
    )
    sp.add_argument("--note", default="", help="备注")

    # update <name> [--value <v>] [--note <n>]
    sp = sub.add_parser("update", help="修改 value / note")
    sp.add_argument("name", help="密钥名")
    sp.add_argument("--value", help="新 value（不传则不改）")
    sp.add_argument(
        "--note",
        help="新 note（不传则不改；传空字符串会清空）",
    )

    # rm <name>
    sp = sub.add_parser("rm", help="删除条目")
    sp.add_argument("name", help="密钥名")

    # search <keyword>
    sp = sub.add_parser("search", help="按 name/note 模糊搜（不搜 value）")
    sp.add_argument("keyword", help="关键词")

    # import --from <dir>
    sp = sub.add_parser("import", help="从 .md 批量迁移")
    sp.add_argument(
        "--from",
        dest="src_dir",
        required=True,
        help="源目录（含 .md 文件）",
    )

    # export [--to <path>]
    sp = sub.add_parser("export", help="JSON 备份")
    sp.add_argument(
        "--to",
        dest="dest",
        help=(
            "备份文件路径（默认 <db_dir>/secrets-backup-YYYYMMDD-HHMMSS.json）"
        ),
    )


# list / search 共用的表格列定义（表头 + 取值函数），集中维护 schema
_SECRET_LIST_COLUMNS: tuple[tuple[str, Callable[[object], str]], ...] = (
    ("Name", lambda e: f"🔐 {e.name}"),
    ("Category", lambda e: f"📂 {e.category}"),
    ("Updated", lambda e: f"🕐 {e.updated_at}"),
)


def _render_secret_table(entries: list) -> str:
    """Render a list of SecretEntry as a CJK-aligned table (BDD §场景 1, 12).

    空列表走友好提示行，不打表头。列宽按表头与所有数据行的最大
    display-width 计算（CJK 按 2 宽算），保证中英混排对齐。
    """
    if not entries:
        return "📭 暂无密钥（试试 x secret set <name> --value <v> 创建）\n"

    header_cells = [h for h, _ in _SECRET_LIST_COLUMNS]
    rows: list[list[str]] = [
        [col(e) for _, col in _SECRET_LIST_COLUMNS] for e in entries
    ]
    col_widths = [
        max(
            [_display_width(header_cells[i])]
            + [_display_width(row[i]) for row in rows]
        )
        for i in range(len(_SECRET_LIST_COLUMNS))
    ]

    lines: list[str] = [
        "  ".join(_pad(c, col_widths[i]) for i, c in enumerate(header_cells)),
        "  ".join("─" * col_widths[i] for i in range(len(_SECRET_LIST_COLUMNS))),
    ]
    for row in rows:
        lines.append(
            "  ".join(_pad(c, col_widths[i]) for i, c in enumerate(row))
        )
    return "\n".join(lines) + "\n"


def _secret_list(args: argparse.Namespace) -> int:
    """``x secret list`` — 列出所有密钥（不显示 value）。

    对应 BDD：§场景 1。按 name 字典序升序，永不显示 value（硬性约束）。
    退出码 0（包含空仓库）。
    """
    from core.secrets import SecretStore  # lazy import

    store = SecretStore()
    entries = sorted(store.list(), key=lambda e: e.name)
    sys.stdout.write(_render_secret_table(entries))
    return 0


def _secret_get(args: argparse.Namespace) -> int:
    """``x secret get <name> [--full]`` — 取一个 value。

    对应 BDD：§场景 2-4。
    - 默认：stdout 第一行 = value（仅 value，无前缀）；stderr 永远打警告
    - ``--full``：stdout = Field/Value 表格（含完整元数据）
    - 找不到 → 退出码 3，stderr 报错，stdout 空
    """
    from core.secrets import SecretStore  # lazy import

    store = SecretStore()
    entry = store.find(args.name)
    if entry is None:
        print(f"❌ 密钥不存在：{args.name}", file=sys.stderr)
        return 3

    if args.full:
        # 完整元数据表格（BDD §场景 3）
        rows: list[tuple[str, str]] = [
            ("name", entry.name),
            ("category", entry.category),
            ("value", entry.value),
            ("note", entry.note or ""),
            ("created_at", entry.created_at),
            ("updated_at", entry.updated_at),
        ]
        col0_w = max(
            _display_width("Field"),
            max(_display_width(r[0]) for r in rows),
        )
        col1_w = max(
            _display_width("Value"),
            max(_display_width(r[1]) for r in rows),
        )
        out: list[str] = [
            "  ".join([_pad("Field", col0_w), _pad("Value", col1_w)]),
            "  ".join(["─" * col0_w, "─" * col1_w]),
        ]
        for k, v in rows:
            out.append("  ".join([_pad(k, col0_w), _pad(v, col1_w)]))
        sys.stdout.write("\n".join(out) + "\n")
    else:
        # BDD §场景 2：仅 value，无前缀；第一行就是 value
        print(entry.value)

    # BDD 硬性约束：get 永远 stderr 警告（不管是否 tty / 是否有 --full）
    print(
        "🔐 警告：密钥已输出到 stdout（可能被 shell 历史 / 日志捕获）",
        file=sys.stderr,
    )
    return 0


def _secret_set(args: argparse.Namespace) -> int:
    """``x secret set <name> --value <v> [--category <c>] [--note <n>]`` — 新增条目。

    对应 BDD：§场景 5-7。已存在 → 退出码 4（用 update 改）。
    """
    from core.secrets import SecretAlreadyExistsError, SecretStore  # lazy import

    store = SecretStore()
    try:
        entry = store.set(
            args.name,
            args.value,
            category=args.category,
            note=args.note,
        )
    except SecretAlreadyExistsError:
        print(
            f"❌ 密钥已存在：{args.name}（用 x secret update 修改）",
            file=sys.stderr,
        )
        return 4

    print(f"✅ 密钥已创建：{entry.name}")
    return 0


def _secret_update(args: argparse.Namespace) -> int:
    """``x secret update <name> [--value <v>] [--note <n>]`` — 修改 value / note。

    对应 BDD：§场景 8-9。
    - 至少要指定 ``--value`` 或 ``--note`` 之一（否则退码 2）
    - ``--note ""`` 显式传空串表示清空 note
    - 找不到 → 退出码 3
    """
    if args.value is None and args.note is None:
        print(
            "❌ 至少要指定 --value 或 --note 之一",
            file=sys.stderr,
        )
        return 2

    from core.secrets import SecretNotFoundError, SecretStore  # lazy import

    store = SecretStore()
    try:
        entry = store.update(args.name, value=args.value, note=args.note)
    except SecretNotFoundError:
        print(f"❌ 密钥不存在：{args.name}", file=sys.stderr)
        return 3

    print(f"✅ 密钥已更新：{entry.name}")
    return 0


def _secret_rm(args: argparse.Namespace) -> int:
    """``x secret rm <name>`` — 删除条目。

    对应 BDD：§场景 10-11。找不到 → 退出码 3。
    """
    from core.secrets import SecretNotFoundError, SecretStore  # lazy import

    store = SecretStore()
    try:
        entry = store.rm(args.name)
    except SecretNotFoundError:
        print(f"❌ 密钥不存在：{args.name}", file=sys.stderr)
        return 3

    print(f"✅ 密钥已删除：{entry.name}")
    return 0


def _secret_search(args: argparse.Namespace) -> int:
    """``x secret search <keyword>`` — 按 name/note 模糊搜（不搜 value）。

    对应 BDD：§场景 12。搜索范围 = name + note，硬性**不**搜 value
    （避免 grep 撞到密钥）。输出格式与 list 一致。
    """
    from core.secrets import SecretStore  # lazy import

    store = SecretStore()
    entries = sorted(store.search(args.keyword), key=lambda e: e.name)
    sys.stdout.write(_render_secret_table(entries))
    return 0


def _secret_import(args: argparse.Namespace) -> int:
    """``x secret import --from <dir>`` — 从 .md 批量迁移。

    对应 BDD：§场景 13-14。源目录不存在 → 退出码 5。
    旧 .md 文件**保留**（单向导入，不删源文件）。
    """
    from core.secrets import SecretStore  # lazy import

    src = Path(args.src_dir)
    if not src.is_dir():
        print(f"❌ 源目录不存在：{src}", file=sys.stderr)
        return 5

    store = SecretStore()
    imported, skipped = store.import_from_dir(src)
    print(f"📥 迁移完成：导入 {imported} 条，跳过 {skipped} 条（重复）")
    return 0


def _secret_export(args: argparse.Namespace) -> int:
    """``x secret export [--to <path>]`` — JSON 备份。

    对应 BDD：§场景 15。默认路径 = ``<db_dir>/secrets-backup-YYYYMMDD-HHMMSS.json``。
    """
    from core.secrets import SecretStore  # lazy import

    dest = Path(args.dest) if args.dest else None
    store = SecretStore()
    path = store.export(dest)
    n = len(store.list())
    print(f"✅ 已备份 {n} 条到 {path}")
    return 0


def _secret_run(args: Sequence[str]) -> int:
    """x secret 入口：解析参数并分发到子命令 handler。

    对应 BDD：``docs/behaviors/secret-behavior.md``（17 场景）。

    无 action → 打印 usage + 退出码 0（BDD §场景 16）。
    action 解析后通过 ``globals().get("_secret_<action>")`` 派发到对应 handler。
    """
    parser = argparse.ArgumentParser(
        prog="x secret", description="密钥管理（独立 JSON DB）"
    )
    _secret_register(parser)
    parsed = parser.parse_args(list(args))

    if not parsed.secret_action:
        parser.print_help()
        return 0

    handler_name = f"_secret_{parsed.secret_action.replace('-', '_')}"
    handler = globals().get(handler_name)
    if handler is None:
        print(
            f"🚧 x secret {parsed.secret_action} 还未实现",
            file=sys.stderr,
        )
        return 1
    return handler(parsed)


# ============================================================
#  主入口
# ============================================================

# 子命令注册表：name -> handler(args) -> exit_code
# Phase 1 只注册 todo；Phase 4 拆插件后改用 importlib.import_module
SUBCOMMAND_HANDLERS: dict[str, Callable[[Sequence[str]], int]] = {
    "todo": _todo_run,
    "secret": _secret_run,
}


def build_parser() -> argparse.ArgumentParser:
    """构造主解析器：--version / <subcommand> [args...]"""
    parser = argparse.ArgumentParser(
        prog="x",
        description="Xavier 个人工具集的统一 CLI 入口",
    )
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="显示版本号并退出",
    )
    parser.add_argument(
        "subcommand",
        nargs="?",
        metavar="SUBCOMMAND",
        help=f"子命令（{', '.join(SUBCOMMAND_HANDLERS)}）",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """主入口：解析 → 分发到子命令 handler"""
    parser = build_parser()
    parsed, remaining = parser.parse_known_args(argv if argv is not None else None)

    if parsed.version:
        print(f"x {__version__}")
        return 0

    if not parsed.subcommand:
        parser.print_help()
        return 0

    handler = SUBCOMMAND_HANDLERS.get(parsed.subcommand)
    if handler is None:
        print(f"❌ 错误：未知子命令：{parsed.subcommand}", file=sys.stderr)
        print(f"提示：支持 {', '.join(SUBCOMMAND_HANDLERS)}", file=sys.stderr)
        return 1

    return handler(remaining)


if __name__ == "__main__":
    sys.exit(main())