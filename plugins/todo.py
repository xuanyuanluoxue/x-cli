"""plugins/todo.py — ``x todo`` subcommand plugin (Phase 4 split).

10 subcommands: list / add / update / archive / restore / search / done /
stats / init / import. See :mod:`x` for the dispatch glue.

Plugin contract (required by ``x.py``):

* :func:`register` — bind subparsers + flags for all actions
* :func:`run` — parse ``sys.argv[1:]`` for this subcommand and dispatch
  to the right handler

The handlers themselves (``_todo_list``, ``_todo_add``, etc.) are kept
as module-private functions and re-exported from :mod:`x` for backward
compat with existing tests.

Per-subcommand BDD specs live in :mod:`docs.behaviors`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from core.formatting import colorize, display_width, pad, supports_color
from core.config import is_auto_archive_enabled
from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.parser import parse_frontmatter
from core.slug import parse_tags, parse_remind, parse_repeat, unique_slug, validate_deadline, validate_time, parse_duration, compute_end_time
from core.storage import (
    TaskAlreadyArchivedError,
    TaskAlreadyExistsError,
    TaskNotFoundError,
    TaskStore,
)

# v0.4.x restore-task exception classes. Try/except the import so the
# plugin module can be imported even if storage hasn't been updated yet
# (during parallel dev). Falls back to ``ValueError`` for the pre-rename
# contract.
try:
    from core.storage import TaskAlreadyActiveError  # type: ignore
    from core.storage import TaskNotArchivedError  # type: ignore
except ImportError:  # pragma: no cover — pre-Subagent-A 阶段
    TaskAlreadyActiveError = ValueError  # type: ignore[misc,assignment]
    TaskNotArchivedError = ValueError  # type: ignore[misc,assignment]


# ============================================================
#  Status / Priority icons (shared by list / search / stats)
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
    Priority.URGENT.value: "🔥🔥",  # v0.5 Phase D — 双火焰
    Priority.HIGH.value: "🔥",
    Priority.MEDIUM.value: "⚡",
    Priority.LOW.value: "🐢",
}


# Priority 排序权重（v0.5 Phase D — urgent > high > medium > low）
_PRIORITY_SORT_WEIGHT: dict[str, int] = {
    Priority.URGENT.value: 0,
    Priority.HIGH.value: 1,
    Priority.MEDIUM.value: 2,
    Priority.LOW.value: 3,
}


# ============================================================
#  Plugin contract: register() + run()
# ============================================================


TODO_ACTIONS: tuple[str, ...] = (
    "list",
    "add",
    "update",
    "archive",
    "stats",
    "init",     # v0.4.0 — bootstrap x-cli's independent TODO dir
    "import",   # v0.4.0 — one-way migration from xavier system
    "restore",  # v0.4.x — archive → active
    "search",   # v0.4.x — cross-field search (name + note + tags)
    "done",     # v0.4.x — `archive --reason done` shortcut
    "reminder", # v0.5 Phase C — read-only remind surface (no notifications)
    "repeat-fire", # v0.5 Phase D — explicit repeat trigger
    "remove",   # v0.5 Phase D — recycle-bin delete
    "template", # v0.5 Phase E — task template create/list/remove
    "export",   # v0.5 Phase E — data export json/csv/md
)


def _todo_register(parser: argparse.ArgumentParser) -> None:
    """注册 x todo 的子命令参数

    ``add`` / ``archive`` / ``update`` / ``list`` 子命令带自己的参数；
    其它子命令仍是占位（Phase 1 MVP 阶段后续实现）。
    """
    sub = parser.add_subparsers(dest="todo_action", required=False, metavar="ACTION")
    for name in TODO_ACTIONS:
        if name == "archive":
            sp = sub.add_parser(name, help="归档任务")
            sp.add_argument(
                "ids",
                nargs="*",
                help="任务 ID（空格分隔；与 --filter 互斥）",
            )
            sp.add_argument(
                "--filter",
                help="模糊匹配 name/tags/note（替代 ids 参数）",
            )
            sp.add_argument(
                "--reason",
                default="done",
                help="归档原因（done / cancelled / expired / failed），默认 done",
            )
        elif name == "update":
            # BDD: docs/behaviors/todo-update-behavior.md §场景 1-8
            # v0.5 Phase D: id 改为可选（--filter 模式不需要）
            sp = sub.add_parser(name, help="更新任务")
            sp.add_argument(
                "id",
                nargs="?",
                help="任务 ID（或 active 状态下的任务名；与 --filter 互斥）",
            )
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
            # v0.5 Phase A — time precision flags
            sp.add_argument(
                "--time",
                help='开始时间（HH:MM 24h 制；传 "" 显式清除）',
            )
            sp.add_argument(
                "--end-time",
                help='结束时间（HH:MM；与 --duration 互斥；传 "" 清除）',
            )
            sp.add_argument(
                "--duration",
                help='新持续时间（"" 清除）',
            )
            # v0.5 Phase B — subtask parent
            sp.add_argument(
                "--parent",
                help='父任务 ID（"" 清除 parent 字段）',
            )
            # v0.5 Phase E — 任务依赖（"" 清除 depends 字段）
            sp.add_argument(
                "--depends",
                help='依赖任务 ID 列表（逗号分隔；"" 清除 depends 字段）',
            )
            # v0.5 Phase C — remind offsets
            sp.add_argument(
                "--remind",
                help='提醒偏移（"" 清除 remind 字段）',
            )
            # v0.5 Phase D — batch ops: --filter / --all (update only)
            sp.add_argument(
                "--filter",
                help='模糊匹配 name/tags/note（替代 id 参数；与 id 互斥）',
            )
            sp.add_argument(
                "--all",
                action="store_true",
                help="--filter 时扩到 archived 范围（默认 active only）",
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
            # v0.5 Phase B — explicit tree view (auto-enabled when any task has parent)
            sp.add_argument(
                "--tree",
                action="store_true",
                help="强制树形展示子任务",
            )
            # v0.5 Phase C — filter by remind field
            sp.add_argument(
                "--reminding",
                action="store_true",
                help="仅显示带提醒字段的任务",
            )
            # v0.5 Phase D — sort modes（无 argparse choices，留给 _todo_list 给中文友好错误）
            sp.add_argument(
                "--sort",
                default="priority",
                help="排序方式（priority / deadline / created / time，默认 priority）",
            )
            # v0.5 Phase D — disable ANSI colors explicitly
            sp.add_argument(
                "--no-color",
                action="store_true",
                help="禁用 ANSI 颜色（即便终端支持）",
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
            # v0.5 Phase A — time precision
            sp.add_argument(
                "--time",
                help="开始时间（HH:MM 24h 制，如 08:20）",
            )
            sp.add_argument(
                "--end-time",
                help="结束时间（HH:MM；与 --duration 互斥）",
            )
            sp.add_argument(
                "--duration",
                help="持续时间（90 / 90m / 1.5h；与 --end-time 互斥）",
            )
            # v0.5 Phase B — subtask parent
            sp.add_argument(
                "--parent",
                help="父任务 ID（创建子任务；最多 2 层）",
            )
            # v0.5 Phase C — remind offsets (read-only mode, no notifications)
            sp.add_argument(
                "--remind",
                help='提醒偏移（逗号分隔，如 1d,2h,30m；传 "" 不写入）',
            )
            # v0.5 Phase D — repeat rule (显式触发 via repeat-fire 子命令)
            sp.add_argument(
                "--repeat",
                help="重复规则（daily/weekly/weekdays/monthly 或标准 5 字段 cron）",
            )
            # v0.5 Phase E — 任务模板（展开为父任务 + N 个子任务）
            sp.add_argument(
                "--template",
                help="任务模板名（用 x todo template create 先创建）",
            )
            # v0.5 Phase E — 任务依赖（多个用逗号分隔）
            sp.add_argument(
                "--depends",
                help="依赖任务 ID（多个用逗号分隔）",
            )
        elif name == "stats":
            sp = sub.add_parser(name, help="📊 统计信息")
        elif name == "init":
            # v0.4.0 — 一键创建 x-cli's 独立 TODO 目录（任务/ + 归档/ + README.md）
            sp = sub.add_parser(
                name,
                help="创建 x-cli's 独立 TODO 目录（幂等）",
            )
            sp.add_argument(
                "--dir",
                dest="init_dir",
                help="自定义目标路径（默认走 xcli_todo_dir 解析）",
            )
        elif name == "import":
            # v0.4.0 — 单向迁移 xavier 系统的 TODO 到 x-cli's 独立库
            sp = sub.add_parser(
                name,
                help="单向迁移（不写回源；重复跳过）",
            )
            sp.add_argument(
                "--from",
                dest="src_dir",
                required=True,
                help="源目录（xavier 系统的 TODO 根，含 任务/ + 归档/）",
            )
            sp.add_argument(
                "--to",
                dest="dst_dir",
                help="目标目录（默认 xcli_todo_dir()）",
            )
            sp.add_argument(
                "--dry-run",
                action="store_true",
                help="只读源 + 只报告，不实际写入",
            )
        elif name == "restore":
            # v0.4.x — 把归档任务还原到 active（不删源，留作审计）
            # BDD: docs/behaviors/todo-restore-behavior.md（10 场景）
            sp = sub.add_parser(name, help="从归档还原到 active")
            sp.add_argument("id", help="任务 ID 或归档名（如 20260621-kemu1）")
            sp.add_argument(
                "--status",
                choices=[s.value for s in TaskStatus],
                help="强制覆盖还原后的 status（默认保留归档前的值）",
            )
            sp.add_argument(
                "--dry-run",
                action="store_true",
                help="只读源 + 只报告，不实际还原",
            )
        elif name == "search":
            # v0.4.x — 跨字段模糊搜索（name + note + tags）
            # BDD: docs/behaviors/todo-search-behavior.md（12 场景）
            sp = sub.add_parser(name, help="跨字段模糊搜索（name + note + tags）")
            sp.add_argument("keyword", help="关键词（非空）")
            sp.add_argument("--active-only", action="store_true", help="只看 active")
            sp.add_argument("--archived-only", action="store_true", help="只看归档")
            sp.add_argument(
                "--status",
                help="按 status 过滤（与搜索结果 AND 关系）",
            )
        elif name == "done":
            # v0.4.x — `archive --reason done` 的语义化快捷方式
            # v0.5 Phase D — 批量多 id + --filter 支持
            sp = sub.add_parser(name, help="archive --reason done 的快捷方式")
            sp.add_argument(
                "ids",
                nargs="*",
                help="任务 ID（空格分隔；与 --filter 互斥）",
            )
            sp.add_argument(
                "--filter",
                help="模糊匹配 name/tags/note",
            )
        elif name == "reminder":
            # v0.5 Phase C — reminder read-only surface
            # BDD: docs/behaviors/todo-remind-behavior.md（12 场景）
            # v0.5 does NOT trigger notifications — only storage / display / clear.
            sub_reminder = sub.add_parser(name, help="提醒管理（v0.5 只读，不触发通知）")
            sub_sub = sub_reminder.add_subparsers(
                dest="reminder_action", required=True
            )
            # x todo reminder list
            list_sp = sub_sub.add_parser("list", help="列出所有带提醒字段的任务")
            list_sp.set_defaults(_reminder_action="list")
            # x todo reminder clear <id...>
            clear_sp = sub_sub.add_parser(
                "clear", help="清除一个或多个任务的提醒字段"
            )
            clear_sp.add_argument(
                "ids", nargs="+", help="任务 ID（空格分隔）"
            )
            clear_sp.set_defaults(_reminder_action="clear")
        elif name == "repeat-fire":
            # v0.5 Phase D — 显式触发重复任务的下一次实例
            # BDD: docs/behaviors/todo-repeat-behavior.md §场景 8-13
            sp = sub.add_parser(name, help="显式触发重复任务的下一次实例（自动编号 -001/-002...）")
            sp.add_argument("id", help="原任务 ID")
        elif name == "remove":
            # v0.5 Phase D — 物理删除（走系统回收站 + --force 跳过）
            # BDD: docs/behaviors/todo-batch-behavior.md §场景 6-12
            sp = sub.add_parser(name, help="删除任务（默认走回收站；--force 物理删除）")
            sp.add_argument(
                "ids",
                nargs="*",
                help="任务 ID（空格分隔；与 --filter 互斥）",
            )
            sp.add_argument(
                "--filter",
                help="模糊匹配 name/tags/note",
            )
            sp.add_argument(
                "--force",
                action="store_true",
                help="跳过回收站，物理删除（不可恢复）",
            )
        elif name == "template":
            # v0.5 Phase E — 任务模板
            # BDD: docs/behaviors/todo-template-behavior.md §场景 1-9
            sub_tmpl = sub.add_parser(name, help="任务模板管理（用于 add --template 展开）")
            sub_tmpl_sub = sub_tmpl.add_subparsers(
                dest="template_action", required=True
            )
            # x todo template create <name> --steps "A,B,C"
            create_sp = sub_tmpl_sub.add_parser(
                "create", help="创建任务模板（--steps 逗号分隔）"
            )
            create_sp.add_argument("name", help="模板名（中文 / 英文均可）")
            create_sp.add_argument(
                "--steps", required=True, help="步骤名（逗号分隔）"
            )
            create_sp.set_defaults(_template_action="create")
            # x todo template list
            list_sp = sub_tmpl_sub.add_parser("list", help="列出所有模板")
            list_sp.set_defaults(_template_action="list")
            # x todo template remove <name>
            remove_sp = sub_tmpl_sub.add_parser("remove", help="删除模板")
            remove_sp.add_argument("name", help="模板名")
            remove_sp.set_defaults(_template_action="remove")
        elif name == "export":
            # v0.5 Phase E — 数据导出
            # BDD: docs/behaviors/todo-export-behavior.md §场景 1-8
            sp = sub.add_parser(name, help="导出任务数据（json / csv / md）")
            sp.add_argument(
                "--format",
                required=True,
                choices=["json", "csv", "md"],
                help="导出格式",
            )
            sp.add_argument(
                "--output",
                help="输出文件路径（默认 stdout）",
            )
            sp.add_argument(
                "--all",
                action="store_true",
                help="包含已归档任务",
            )
        else:
            sp = sub.add_parser(name, help=f"{name} 命令")


# Plugin contract alias. The x.py dispatcher calls ``register(parser)``
# to wire up subparsers. ``_todo_register`` is the historical name kept
# for backward compat with tests / external imports.
register = _todo_register


def run(args: Sequence[str]) -> int:
    """x todo 入口：解析参数并分发到子命令"""
    parser = argparse.ArgumentParser(prog="x todo", description="TODO 管理")
    register(parser)
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

    # x todo init — v0.4.0 新增（独立目录引导）
    if parsed.todo_action == "init":
        return _todo_init(parsed)

    # x todo import — v0.4.0 新增（从 xavier 系统单向迁移）
    if parsed.todo_action == "import":
        return _todo_import(parsed)

    # x todo restore — v0.4.x 新增（archive → active）
    if parsed.todo_action == "restore":
        return _todo_restore(parsed)

    # x todo search — v0.4.x 新增（跨字段模糊搜索）
    if parsed.todo_action == "search":
        return _todo_search(parsed)

    # x todo done — v0.4.x 新增（archive --reason done 快捷方式）
    if parsed.todo_action == "done":
        return _todo_done(parsed)

    # x todo reminder — v0.5 Phase C（只读 / clear，**不触发通知**）
    if parsed.todo_action == "reminder":
        return _todo_reminder(parsed)

    # x todo repeat-fire — v0.5 Phase D（显式触发重复任务下一次实例）
    if parsed.todo_action == "repeat-fire":
        return _todo_repeat_fire(parsed)

    # x todo remove — v0.5 Phase D（走系统回收站 + --force）
    if parsed.todo_action == "remove":
        return _todo_remove(parsed)

    # x todo template — v0.5 Phase E（模板 create/list/remove + add --template）
    if parsed.todo_action == "template":
        return _todo_template(parsed)

    # x todo export — v0.5 Phase E（json/csv/md 数据导出）
    if parsed.todo_action == "export":
        return _todo_export(parsed)

    return _todo_not_implemented(parsed.todo_action)


def _todo_not_implemented(action: str) -> int:
    """x todo 各子命令的占位实现（Phase 1 MVP 阶段）"""
    print(f"🚧 x todo {action} 还未实现", file=sys.stderr)
    return 1


# ============================================================
#  x todo archive
# ============================================================


def _todo_archive(args: argparse.Namespace) -> int:
    """处理 x todo archive 命令（已被 run 解析过）

    对应 BDD: docs/behaviors/todo-archive-behavior.md §场景 1-8

    v0.5 Phase B: 当 archive 的任务有 parent 引用（子任务），
    或有任务以本任务为 parent（父任务场景），永远级联。

    v0.5 Phase D: 批量多 id + ``--filter`` 模糊匹配。
    单 id 旧调用方式（args.id 仍兼容）也保留。

    退出码约定：
    - 0：全部成功
    - 2：非法 reason / 必须指定 id 或 --filter
    - 3：任务不存在（部分成功也算 3）
    - 4：任务已归档（重复归档）
    - 5：归档目标已存在（碰撞）
    """
    from core.storage import find_descendants, find_by_filter

    # v0.5 Phase D — batch: ids (list) 或 --filter 模糊匹配
    ids: list[str] = list(getattr(args, "ids", None) or [])
    keyword: str | None = getattr(args, "filter", None)
    single_id_legacy: str | None = getattr(args, "id", None)  # 兼容旧 done 路径

    if not ids and not keyword and not single_id_legacy:
        print(
            "❌ 必须指定任务 ID 或 --filter",
            file=sys.stderr,
        )
        return 2
    if single_id_legacy and not ids:
        ids = [single_id_legacy]

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

    # 2. Resolve targets
    store = TaskStore()
    targets: list[Task] = []
    not_found: list[str] = []
    if ids:
        for raw in ids:
            tid = raw.strip()
            if not tid:
                continue
            t = store.get_task(tid, include_archived=True)
            if t is None:
                not_found.append(tid)
            else:
                if t not in targets:
                    targets.append(t)
    if keyword:
        for t in find_by_filter(keyword, include_archived=False):
            if t not in targets:
                targets.append(t)

    if not targets:
        if not_found:
            print(
                f"❌ 任务不存在：{', '.join(not_found)}",
                file=sys.stderr,
            )
        else:
            print(
                f"❌ --filter '{keyword}' 没有匹配的任务",
                file=sys.stderr,
            )
        return 3

    # Cascade to descendants
    all_active = store.list_tasks(include_archived=False)
    full_targets: list[Task] = []
    for t in targets:
        if t not in full_targets:
            full_targets.append(t)
        for d in find_descendants(t.id or "", all_active):
            if d not in full_targets:
                full_targets.append(d)

    # Archive each
    archived_set: list[Task] = []
    any_already_archived = False
    for t in full_targets:
        try:
            archived = store.archive_task(t.id or "", reason=reason_str)
            archived_set.append(archived)
        except TaskNotFoundError:
            continue
        except TaskAlreadyArchivedError:
            any_already_archived = True
            # v0.5 Phase D — 批量场景：仅当 ALL targets 都已归档才算 4；
            # 部分已归档视为 partial success（rc=3）
            if len(full_targets) == 1:
                folder_display = t.folder or ""
                print(
                    f"❌ 任务已归档：{t.id or t.name}（位于 {folder_display}）",
                    file=sys.stderr,
                )
                return 4
            continue
        except FileExistsError:
            continue

    # Update inventory（从 task.extra._orig_status_before_archive 取旧状态）
    try:
        for t in archived_set:
            old_status_str = (
                (t.extra or {}).get("_orig_status_before_archive", "pending")
            )
            # Convert back to enum
            try:
                old_status = TaskStatus(old_status_str)
            except ValueError:
                old_status = TaskStatus.PENDING
            store.update_inventory_on_archive(old_status)
    except Exception:  # noqa: BLE001
        pass

    # Success message
    if len(archived_set) == 1:
        print(
            f"✅ 任务已归档：{archived_set[0].name}"
            f"（ID: {archived_set[0].id}，reason={reason_str}）"
        )
    else:
        ids_str = ", ".join(t.id or t.name for t in archived_set)
        print(
            f"✅ 已级联归档 {len(archived_set)} 个任务：{ids_str}"
            f"（reason={reason_str}）"
        )

    if not_found:
        print(
            f"⚠️ 部分 ID 未找到：{', '.join(not_found)}",
            file=sys.stderr,
        )
        return 3
    if any_already_archived and len(archived_set) == 0:
        # All targets were already archived → rc=4
        return 4
    return 0


# ============================================================
#  x todo restore
# ============================================================


def _todo_restore(args: argparse.Namespace) -> int:
    """``x todo restore <id> [--status X] [--dry-run]`` — archive → active.

    对应 BDD：``docs/behaviors/todo-restore-behavior.md``（10 场景）。

    退出码约定：
    - 0：成功（含 ``--dry-run``）
    - 3：任务不存在 / active 已有同名（冲突）
    - 4：任务未归档（不是 archived 状态）
    - 5：归档 YAML 解析失败

    归档源**不**删除（审计保留）；仅在 active 区创建新文件并把
    ``status`` 恢复为归档前的值（默认行为，``--status`` 可覆盖）。
    """
    if not args.id or not args.id.strip():
        print("❌ 任务 ID 不能为空", file=sys.stderr)
        return 3

    target_status = TaskStatus(args.status) if args.status else None

    store = TaskStore()
    try:
        restored = store.restore_task(
            args.id,
            target_status=target_status,
            dry_run=args.dry_run,
        )
    except TaskNotFoundError:
        # BDD §场景 3
        print(f"❌ 任务不存在：{args.id}", file=sys.stderr)
        return 3
    except TaskAlreadyActiveError as exc:
        # BDD §场景 2C / §场景 8
        active_name = getattr(exc, "name", args.id)
        print(
            f"❌ 任务已存在（active）：{active_name}"
            f"（先 archive 或用归档名）",
            file=sys.stderr,
        )
        return 3
    except TaskNotArchivedError:
        # BDD §场景 4
        print(
            f"❌ 任务未归档：{args.id}"
            f"（请用 x todo update 改状态）",
            file=sys.stderr,
        )
        return 4
    except ValueError as exc:
        # BDD §场景 6：归档 YAML 解析失败
        print(
            f"❌ 归档任务解析失败：{args.id}"
            f"（YAML 格式错误：{exc}）",
            file=sys.stderr,
        )
        return 5

    status_str = (
        restored.status.value
        if isinstance(restored.status, TaskStatus)
        else str(restored.status)
    )
    if args.dry_run:
        # BDD §场景 10
        print(
            f"🔍 [dry-run] 将还原：{restored.name}（ID: {restored.id}）"
        )
        print(f"   status: archived → {status_str}")
        return 0

    # BDD §场景 1/5/9
    print(f"✅ 任务已还原：{restored.name}（ID: {restored.id}）")
    print(f"   状态：archived → {status_str}")
    return 0


# ============================================================
#  x todo search
# ============================================================


def _todo_search(args: argparse.Namespace) -> int:
    """``x todo search <keyword> [--active-only] [--archived-only] [--status X]``.

    对应 BDD：``docs/behaviors/todo-search-behavior.md``（12 场景）。

    退出码约定：
    - 0：成功（0 个匹配也算 0）
    - 2：关键词为空（argparse 必填 + 显式校验）

    输出格式与 ``x todo list`` 完全一致（5 列：ID / Name / Status /
    Priority / Deadline），方便用户认知切换。
    """
    if not args.keyword or not args.keyword.strip():
        print("❌ 关键词不能为空", file=sys.stderr)
        return 2

    keyword = args.keyword.strip()
    active_only = bool(args.active_only)
    archived_only = bool(args.archived_only)

    if active_only and archived_only:
        # 互斥 — 既只要 active 又只要 archived 永远为空，提前报个错
        print(
            "❌ --active-only 和 --archived-only 互斥，不能同时使用",
            file=sys.stderr,
        )
        return 2

    store = TaskStore()

    # Auto-archive hook (opt-in). Per BDD §场景 5 the search result
    # table must NOT contain the just-archived overdue tasks. The
    # default ``search_tasks`` includes both active + archived, so
    # without intervention the freshly-archived tasks would leak into
    # the result. Fix: when auto-archive just fired, force
    # ``include_archived=False`` UNLESS the user explicitly asked for
    # ``--archived-only`` (in which case the summary line is still
    # useful as a hint, and the user clearly wants to see archived).
    archived = _auto_archive_overdue(store)
    sys.stdout.write(_render_auto_archive_summary(archived))

    auto_archived = bool(archived)
    include_archived_effective = archived_only or (
        not active_only and not auto_archived
    )
    include_active_effective = not archived_only

    matches = store.search_tasks(
        keyword,
        include_archived=include_archived_effective,
        include_active=include_active_effective,
    )

    # Optional status filter (BDD §场景 10)
    if args.status:
        try:
            status_filter = TaskStatus(args.status)
        except ValueError:
            hint = " / ".join(s.value for s in TaskStatus)
            print(
                f"❌ 无效的 status 值：{args.status}（合法值：{hint}）",
                file=sys.stderr,
            )
            return 2
        matches = [t for t in matches if t.status == status_filter]

    if not matches:
        # BDD §场景 6 / §场景 9
        print(f'📭 没有匹配 "{keyword}" 的任务（搜索 name + note + tags）')
        print("💡 试试：x todo list")
        return 0

    # BDD §场景 1/3/4/7：表格格式与 ``x todo list`` 一致（5 列）
    header_cells = [h for h, _ in _LIST_COLUMNS]
    rows: list[list[str]] = [
        [col(t) for _, col in _LIST_COLUMNS] for t in matches
    ]
    col_widths = [
        max(
            [display_width(header_cells[i])]
            + [display_width(row[i]) for row in rows]
        )
        for i in range(len(_LIST_COLUMNS))
    ]
    print("  ".join(pad(c, col_widths[i]) for i, c in enumerate(header_cells)))
    print("  ".join("─" * col_widths[i] for i in range(len(_LIST_COLUMNS))))
    for row in rows:
        print("  ".join(pad(c, col_widths[i]) for i, c in enumerate(row)))
    return 0


# ============================================================
#  x todo done
# ============================================================


def _todo_done(args: argparse.Namespace) -> int:
    """``x todo done <id...> [--filter]`` — ``x todo archive <id...> --reason done`` 的快捷方式。

    v0.5 Phase D：批量多 id + ``--filter`` 模糊匹配。
    复用 ``_todo_archive`` 的全部逻辑与退出码。
    """
    # Reuse _todo_archive logic — translate multi-id/filter to a Namespace it expects
    archive_args = argparse.Namespace(
        ids=getattr(args, "ids", None) or ([args.id] if getattr(args, "id", None) else []),
        reason="done",
        filter=getattr(args, "filter", None),
    )
    return _todo_archive(archive_args)


# ============================================================
#  x todo reminder list / clear (v0.5 Phase C)
# ============================================================


def _todo_reminder(args: argparse.Namespace) -> int:
    """``x todo reminder list / clear`` — 提醒只读 + 清除。

    对应 BDD：``docs/behaviors/todo-remind-behavior.md``（12 场景）。

    v0.5 范围（明确）：
    - ✅ 字段可写、可显示、可清除、可筛选、可统计
    - ❌ **不触发任何通知**（daemon / scheduler 推到 v0.6+ 打包 exe 后）

    退出码：
    - 0：成功（包括「无提醒」空表）
    - 3：clear 时任务不存在
    """
    action = getattr(args, "_reminder_action", None)
    if action == "list":
        return _todo_reminder_list()
    if action == "clear":
        return _todo_reminder_clear(args.ids)
    # Should never reach here (subparser required=True)
    print(f"❌ 未知的 reminder 子命令：{action}", file=sys.stderr)
    return 2


def _todo_reminder_list() -> int:
    """``x todo reminder list`` — 列出所有带 remind 字段的 active 任务。

    输出表格列：ID / Name / Deadline / Time / Reminders。
    表格为空时输出提示文案（而非错误）。
    """
    store = TaskStore()
    tasks = store.list_tasks(include_archived=False)
    reminded = [t for t in tasks if t.remind]

    if not reminded:
        print("📭 没有带提醒的任务")
        return 0

    # Column widths (CJK-aware via display_width)
    header = ["ID", "Name", "Deadline", "Time", "Reminders"]
    rows = []
    for t in reminded:
        rows.append([
            t.id or t.name,
            t.name,
            t.deadline or "-",
            _list_time_cell(t),
            ", ".join(t.remind or []),
        ])
    col_widths = [
        max([display_width(header[i])] + [display_width(r[i]) for r in rows])
        for i in range(len(header))
    ]
    print("  ".join(pad(c, col_widths[i]) for i, c in enumerate(header)))
    print("  ".join("─" * col_widths[i] for i in range(len(header))))
    for row in rows:
        print("  ".join(pad(c, col_widths[i]) for i, c in enumerate(row)))
    return 0


def _todo_reminder_clear(ids: list[str]) -> int:
    """``x todo reminder clear <id...>`` — 清除一个或多个任务的 remind 字段。

    每个 id 独立校验：不存在则退出码 3（与 update / archive 一致）。
    """
    from datetime import date

    store = TaskStore()
    today = date.today().isoformat()
    cleared: list[str] = []
    not_found: list[str] = []
    for raw in ids:
        tid = raw.strip()
        if not tid:
            continue
        try:
            task = store.update_task(
                tid,
                clear_remind=True,
                today=today,
            )
            cleared.append(task.id or task.name)
        except TaskNotFoundError:
            not_found.append(tid)

    if not_found:
        print(
            f"❌ 任务不存在：{', '.join(not_found)}",
            file=sys.stderr,
        )
        return 3

    if len(cleared) == 1:
        print(f"✅ 已清除提醒：{cleared[0]}")
    else:
        print(f"✅ 已清除提醒：{', '.join(cleared)}（共 {len(cleared)} 个）")
    return 0


# ============================================================
#  x todo repeat-fire (v0.5 Phase D)
# ============================================================


def _todo_repeat_fire(args: argparse.Namespace) -> int:
    """``x todo repeat-fire <id>`` — 显式触发重复任务的下一次实例。

    对应 BDD：``docs/behaviors/todo-repeat-behavior.md`` §场景 8-13。

    v0.5 范围：
    - ✅ 创建 seq+1 实例（自动编号 -001/-002...）
    - ✅ 复制原任务的 repeat 字段
    - ❌ 不自动 archive 原任务（原任务保留作为锚点）
    - ❌ 不自动触发（archive done 时**不**调用此函数）
    """
    from datetime import date

    tid = (args.id or "").strip()
    if not tid:
        print("❌ 任务 ID 不能为空", file=sys.stderr)
        return 2

    store = TaskStore()
    task = store.get_task(tid, include_archived=False)
    if task is None:
        print(f"❌ 任务不存在：{tid}", file=sys.stderr)
        return 3

    if not task.repeat:
        print(f"❌ 任务没有 repeat 字段：{tid}", file=sys.stderr)
        return 2

    # Compute next seq by scanning active tasks with same name prefix
    task_id = task.id or ""
    base_name = task.name
    seq = 1
    existing_ids = {t.id for t in store.list_tasks(include_archived=True) if t.id}
    while f"{task_id}-{seq:03d}" in existing_ids:
        seq += 1
    new_id = f"{task_id}-{seq:03d}"

    # New task: same as parent but new id, new folder name suffix
    today = date.today().isoformat()
    # Avoid name collision: original "周会" → "周会-001", "周会-002", ...
    new_name = f"{base_name}-{seq:03d}"
    new_folder_name = new_name  # The folder name
    new_folder = store.active_dir / new_folder_name
    if new_folder.exists():
        # Extremely unlikely (seq collision) — bump further
        while new_folder.exists():
            seq += 1
            new_id = f"{task_id}-{seq:03d}"
            new_name = f"{base_name}-{seq:03d}"
            new_folder = store.active_dir / new_name
            if seq > 999:
                print("❌ seq 超过 999（异常），中止", file=sys.stderr)
                return 5

    # Build new Task (copy relevant fields, new id/name/folder/dates)
    new_task = Task(
        id=new_id,
        name=new_name,
        status=TaskStatus.PENDING,
        priority=task.priority,
        created=today,
        updated=today,
        deadline=task.deadline,
        time=task.time,
        end_time=task.end_time,
        duration_min=task.duration_min,
        parent=task.parent,
        remind=task.remind,
        repeat=dict(task.repeat),  # copy repeat rule
        folder=f"任务/{new_folder_name}",
        tags=list(task.tags) if task.tags else None,
    )
    try:
        store.add_task(new_task)
    except TaskAlreadyExistsError as exc:
        print(f"❌ 任务已存在：{exc.name}", file=sys.stderr)
        return 3
    print(f"✅ 已创建下一次实例：{new_id}")
    return 0


# ============================================================
#  x todo remove (v0.5 Phase D — recycle bin)
# ============================================================


def _todo_remove(args: argparse.Namespace) -> int:
    """``x todo remove <id...> [--filter] [--force]`` — 物理删除任务。

    对应 BDD：``docs/behaviors/todo-batch-behavior.md`` §场景 6-12。

    v0.5 范围：
    - 默认走系统回收站（Windows: ctypes SHFileOperation; macOS: mv ~/.Trash; Linux: gio trash）
    - ``--force`` 跳过回收站（不可恢复）
    - 多 id 支持 + ``--filter`` 模糊匹配
    - 父任务级联（永远级联，子 + 孙一起）
    - 退出码：0 全部成功 / 3 部分不存在（部分成功）
    """
    from core.storage import find_descendants, find_by_filter

    ids: list[str] = list(args.ids or [])
    keyword: str | None = getattr(args, "filter", None)
    force: bool = bool(getattr(args, "force", False))

    if not ids and not keyword:
        print(
            "❌ 必须指定任务 ID 或 --filter",
            file=sys.stderr,
        )
        return 2

    # Resolve targets: ids explicit OR --filter matching
    store = TaskStore()
    targets: list[Task] = []
    not_found: list[str] = []
    if ids:
        for raw in ids:
            tid = raw.strip()
            if not tid:
                continue
            t = store.get_task(tid, include_archived=False)
            if t is None:
                not_found.append(tid)
            else:
                targets.append(t)
    if keyword:
        matched = find_by_filter(keyword, include_archived=False)
        # Avoid duplicates with explicit ids
        explicit_ids = {t.id for t in targets}
        for t in matched:
            if t.id not in explicit_ids:
                targets.append(t)

    if not targets:
        if not_found:
            print(
                f"❌ 任务不存在：{', '.join(not_found)}",
                file=sys.stderr,
            )
        else:
            print(
                f"❌ --filter '{keyword}' 没有匹配的任务",
                file=sys.stderr,
            )
        return 3

    # Cascade to descendants
    all_active = store.list_tasks(include_archived=False)
    cascade_targets: list[Task] = []
    for t in targets:
        cascade_targets.append(t)
        for d in find_descendants(t.id or "", all_active):
            if d not in cascade_targets:
                cascade_targets.append(d)

    # Remove each (with cascade)
    removed_ids: list[str] = []
    recycled_count = 0
    for t in cascade_targets:
        try:
            _, recycled = store.remove_task(t.id or t.name, force=force)
            removed_ids.append(t.id or t.name)
            if recycled:
                recycled_count += 1
        except TaskNotFoundError:
            # Race or already-removed; skip silently
            pass

    if not removed_ids:
        print("❌ 没有任务被删除", file=sys.stderr)
        return 3

    # Compose summary
    if force:
        action = "已物理删除（绕过回收站）"
    elif recycled_count == len(removed_ids):
        action = "已移入回收站"
    elif recycled_count == 0:
        action = "已物理删除（回收站不可用）"
    else:
        action = f"已处理（{recycled_count} 个进回收站，{len(removed_ids) - recycled_count} 个物理删除）"

    if len(removed_ids) == 1:
        print(f"✅ {action}：{removed_ids[0]}")
    else:
        print(f"✅ {action}：{', '.join(removed_ids)}（共 {len(removed_ids)} 个）")

    # Partial fail: if explicit ids had not_found, report 3
    if not_found:
        print(
            f"⚠️ 部分 ID 未找到：{', '.join(not_found)}",
            file=sys.stderr,
        )
        return 3
    return 0


# ============================================================
#  x todo update
# ============================================================


def _todo_update(args: argparse.Namespace) -> int:
    """处理 ``x todo update <id> [选项]`` 命令（已被 run 解析过）。

    对应 BDD：`docs/behaviors/todo-update-behavior.md`（8 个场景）。
    v0.5 Phase D: 支持 ``--filter`` 模糊匹配 + ``--all`` 扩到 archived。

    退出码约定：
    - 0：成功
    - 2：非法 status / priority 值，或无任何 --xxx 选项（argparse 标准错误）
    - 3：任务不存在（部分成功也算 3）
    - 4：任务已归档（不可更新，需先 restore；--all 时允许）
    """
    # v0.5 Phase D — batch via --filter (or --all for global)
    keyword = getattr(args, "filter", None)
    include_archived = bool(getattr(args, "all", False))
    target_id: str | None = getattr(args, "id", None)

    if keyword or include_archived:
        from core.storage import find_by_filter
        if keyword:
            matched = find_by_filter(keyword, include_archived=include_archived)
            if not matched:
                print(f"❌ --filter '{keyword}' 没有匹配的任务", file=sys.stderr)
                return 3
        else:
            # --all without --filter = update every task (active + archived)
            from core.storage import TaskStore as _TS
            matched = _TS().list_tasks(include_archived=True)

        # Loop over each target
        any_fail = False
        any_archived_blocked = False
        for t in matched:
            single = argparse.Namespace(
                id=t.id or t.name,
                status=args.status,
                priority=args.priority,
                deadline=args.deadline,
                tags=args.tags,
                time=args.time,
                end_time=args.end_time,
                duration=args.duration,
                parent=args.parent,
                remind=args.remind,
                filter=None,
                all=False,
            )
            rc = _todo_update_single(single)
            if rc == 3:
                any_fail = True
            elif rc == 4:
                any_archived_blocked = True
        if any_archived_blocked and not include_archived:
            return 4
        if any_archived_blocked and include_archived:
            # --all + filter matched both active+archived, the archived
            # ones are still blocked. Return 4 to surface the failure.
            return 4
        if any_fail:
            return 3
        return 0
    return _todo_update_single(args)


def _todo_update_single(args: argparse.Namespace) -> int:
    """Single-id ``x todo update`` helper (Phase A/B/C original logic).

    Refactored out of :func:`_todo_update` so the v0.5 Phase D batch path
    can call it once per matched target without duplicating validation.
    """
    from datetime import date  # local import to keep module load cheap

    # BDD 场景 8：至少要有一个 --xxx 选项；用 argparse 标准错误格式
    if (
        args.status is None
        and args.priority is None
        and args.deadline is None
        and args.tags is None
        and args.time is None
        and args.end_time is None
        and args.duration is None
        and args.parent is None
        and args.remind is None
        and args.depends is None
    ):
        # Rebuild a parser so we can use parser.error() for consistent
        # argparse-style output ("usage: ..." + "prog: error: ...").
        parser = argparse.ArgumentParser(prog="x todo update", description="更新 TODO 任务")
        parser.add_argument("id", help="任务 ID")
        parser.add_argument("--status", help="新状态")
        parser.add_argument("--priority", help="新优先级")
        parser.add_argument("--deadline", help='新截止日期（"" 清除）')
        parser.add_argument("--tags", help="新标签")
        parser.add_argument("--time", help="新开始时间（HH:MM）")
        parser.add_argument("--end-time", help='新结束时间（"" 清除）')
        parser.add_argument("--duration", help='新持续时间（"" 清除）')
        parser.add_argument("--parent", help='父任务 ID（"" 清除）')
        parser.add_argument("--remind", help='提醒偏移（"" 清除）')
        parser.add_argument("--depends", help='依赖任务 ID（"" 清除）')
        parser.error(
            "at least one of --status / --priority / --deadline / --tags "
            "/ --time / --end-time / --duration / --parent / --remind / --depends is required"
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

    # v0.5 Phase A — time precision (BDD §场景 7-8, 9-10)
    new_time: str | None = None
    clear_time = args.time is not None and args.time == ""
    if args.time is not None and not clear_time:
        try:
            validate_time(args.time)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        new_time = args.time

    new_end_time: str | None = None
    clear_end_time = args.end_time is not None and args.end_time == ""
    if args.end_time is not None and not clear_end_time:
        try:
            validate_time(args.end_time)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        new_end_time = args.end_time

    new_duration_min: int | None = None
    clear_duration = args.duration is not None and args.duration == ""
    if args.duration is not None and not clear_duration:
        try:
            new_duration_min = parse_duration(args.duration)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    # v0.5 Phase C — --remind 校验（BDD §场景 3, 4, 5）
    new_remind: list[str] | None | type(...) = None  # sentinel
    clear_remind = args.remind is not None and args.remind == ""
    if args.remind is not None and not clear_remind:
        try:
            new_remind = parse_remind(args.remind)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    # v0.5 Phase E — --depends 校验（覆盖 / 清空）
    new_depends: list[str] | None | type(...) = None  # sentinel
    clear_depends = args.depends is not None and args.depends == ""
    if args.depends is not None and not clear_depends:
        deps = [d.strip() for d in args.depends.split(",") if d.strip()]
        if deps:
            from core.storage import TaskStore as _TS
            for d in deps:
                if _TS().get_task(d, include_archived=False) is None:
                    print(f"❌ 依赖任务不存在：{d}", file=sys.stderr)
                    return 3
            new_depends = deps

    # v0.5 Phase B — --parent 校验（BDD §场景 3, 4, 14）
    new_parent: str | None | type(...) = None  # sentinel
    clear_parent = args.parent is not None and args.parent == ""
    if args.parent is not None and not clear_parent:
        new_parent_value = args.parent
        store_for_check = TaskStore()
        # Cannot set parent to self
        if new_parent_value == args.id:
            print(
                f"❌ 不能把 parent 设为自己的后代：{new_parent_value}",
                file=sys.stderr,
            )
            return 2
        parent_task = store_for_check.get_task(new_parent_value, include_archived=False)
        if parent_task is None:
            print(
                f"❌ 父任务不存在：{new_parent_value}",
                file=sys.stderr,
            )
            return 3
        # Depth check: parent must be at depth ≤ 1
        depth = 0
        current = parent_task
        visited: set[str] = set()
        while current and current.parent:
            if current.id in visited:
                break
            visited.add(current.id)
            depth += 1
            current = store_for_check.get_task(current.parent, include_archived=False)
        if depth >= 2:
            print(
                f"❌ 子任务最多 2 层：{new_parent_value} 已经是孙任务",
                file=sys.stderr,
            )
            return 2
        # Cycle check: cannot set parent to one of our own descendants
        from core.storage import find_descendants
        all_active = store_for_check.list_tasks(include_archived=False)
        descendants = find_descendants(args.id, all_active)
        if any(d.id == new_parent_value for d in descendants):
            print(
                f"❌ 不能把 parent 设为自己的后代：{new_parent_value}",
                file=sys.stderr,
            )
            return 2
        new_parent = new_parent_value
    elif clear_parent:
        new_parent = None  # explicit None = clear
    # If args.parent is None (not passed), leave new_parent as sentinel → no change

    # 写盘
    store = TaskStore()
    update_kwargs: dict = dict(
        status=TaskStatus(args.status) if args.status else None,
        priority=Priority(args.priority) if args.priority else None,
        deadline=new_deadline,
        tags=new_tags,
        clear_deadline=clear_deadline,
        time=new_time,
        end_time=new_end_time,
        duration_min=new_duration_min,
        clear_time=clear_time,
        clear_end_time=clear_end_time,
        clear_duration_min=clear_duration,
        depends=new_depends,
        clear_depends=clear_depends,
        today=date.today().isoformat(),
    )
    if new_parent is not None or clear_parent:
        update_kwargs["parent"] = new_parent if not clear_parent else None
        update_kwargs["clear_parent"] = clear_parent
    if new_remind is not None or clear_remind:
        update_kwargs["remind"] = new_remind if not clear_remind else None
        update_kwargs["clear_remind"] = clear_remind
    if new_depends is not None or clear_depends:
        update_kwargs["depends"] = new_depends if not clear_depends else None
        update_kwargs["clear_depends"] = clear_depends
    try:
        task = store.update_task(args.id, **update_kwargs)
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
#  x todo list + helpers
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


def _list_priority_cell(task, *, color_enabled: bool | None = None) -> str:
    """表格 Priority 列的展示值；带图标，urgent 在 ANSI 终端标红。

    v0.5 Phase D：``color_enabled=None`` 自动检测终端（调用 ``supports_color()``），
    也可显式传 True/False 覆盖（如测试时强制开/关）。
    """
    if isinstance(task.priority, Priority):
        cell = task.priority.value
    else:
        cell = str(task.priority)
    icon = _PRIORITY_ICONS.get(cell, "")
    text = f"{icon} {cell}" if icon else cell
    # v0.5 Phase D — urgent 红色高亮
    if cell == Priority.URGENT.value:
        return colorize(text, "red", enabled=color_enabled)
    return text


def _list_time_cell(task: object) -> str:
    """v0.5 Phase A — 列表 Time 列展示（BDD §场景 11, 14）。

    优先级：time + end_time → ``HH:MM-HH:MM``
            time + duration_min → ``HH:MM-<derived>``
            time alone → ``HH:MM``
            否则 → ``-``
    """
    t = task.time or ""
    e = getattr(task, "end_time", None)
    d = getattr(task, "duration_min", None)
    if not t:
        return "-"
    if e:
        return f"{t}-{e}"
    if d is not None:
        derived = compute_end_time(t, d)
        return f"{t}-{derived}"
    return t


def _list_name_cell(task: object, *, has_unfulfilled_dep: bool) -> str:
    """v0.5 Phase E — 列表 Name 列展示（BDD §场景 6, 7）。

    任务有未完成的依赖时，Name 前加 🔒 提示。
    """
    name = task.name or ""
    return f"🔒 {name}" if has_unfulfilled_dep else name


# 列表命令的列定义（表头 + 取值函数），集中维护表格 schema
def _make_priority_cell(color_enabled: bool | None) -> Callable[[object], str]:
    return lambda t: _list_priority_cell(t, color_enabled=color_enabled)


_LIST_COLUMNS_TEMPLATE: Callable[[bool | None], tuple[tuple[str, Callable[[object], str]], ...]] = (
    lambda color_enabled: (
        ("ID", lambda t: t.id or t.name),
        ("Name", lambda t: t.name),
        ("Status", _list_status_cell),
        ("Priority", _make_priority_cell(color_enabled)),
        ("Deadline", lambda t: t.deadline or "-"),
        ("Time", _list_time_cell),  # v0.5 Phase A
    )
)

# Backward-compat alias for existing call sites; uses auto color detection.
_LIST_COLUMNS = _LIST_COLUMNS_TEMPLATE(None)


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


# ============================================================
#  Auto-archive hook (opt-in, shared by list / stats / search)
# ============================================================


def _auto_archive_overdue(store: TaskStore) -> list[Task]:
    """If auto-archive is enabled, archive overdue tasks and return them.

    对应 BDD: ``docs/behaviors/todo-auto-archive-behavior.md``.

    Behaviour:

    * **Default disabled** — when :func:`core.config.is_auto_archive_enabled`
      returns ``False`` (no env var, no config flag), this is a no-op
      and returns ``[]``. BDD §场景 3 (the "must not break existing users"
      invariant) depends on this branch.
    * **Archive + inventory update** — for each overdue task, call
      :meth:`TaskStore.archive_task` with ``reason="expired"`` and
      refresh the top-level ``TODO.md`` inventory via
      :meth:`TaskStore.update_inventory_on_archive`. Identical to the
      manual ``x todo archive <id> --reason expired`` path.
    * **Defensive** — a single broken file / race condition does not
      poison the whole list/stats/search call. Failures are logged to
      ``stderr`` and the loop continues with the next overdue task.
    * **Deterministic ordering** — the returned list is sorted by
      ``(deadline, name)`` ascending, matching the order in
      :meth:`TaskStore.find_overdue_tasks` so the summary line the
      caller renders is stable.

    The caller is responsible for rendering the summary line on
    ``stdout`` (use :func:`_render_auto_archive_summary`). This
    function only does side-effects.
    """
    if not is_auto_archive_enabled():
        return []

    overdue = store.find_overdue_tasks()
    if not overdue:
        return []

    archived: list[Task] = []
    for task in overdue:
        old_status = task.status
        try:
            moved = store.archive_task(task.id, reason="expired")
        except (
            TaskNotFoundError,
            TaskAlreadyArchivedError,
            FileExistsError,
        ) as exc:
            # Race / collision / already archived — log and move on so a
            # single bad task doesn't kill the user's list/stats/search
            # call. Mirror the manual archive handler's error suppression
            # for consistency.
            print(
                f"⚠️ 自动归档失败：{task.name}（{exc}）",
                file=sys.stderr,
            )
            continue
        except Exception as exc:  # noqa: BLE001 — defensive, see above
            print(
                f"⚠️ 自动归档失败：{task.name}（{exc}）",
                file=sys.stderr,
            )
            continue
        archived.append(moved)
        # Maintain inventory (same best-effort pattern as _todo_archive).
        try:
            store.update_inventory_on_archive(old_status)
        except Exception:  # noqa: BLE001 — defensive
            pass

    return archived


def _render_auto_archive_summary(archived: list[Task]) -> str:
    """Render the one-line summary printed at the top of stdout.

    Returns an empty string when ``archived`` is empty (BDD §场景 2: 0
    tasks → no summary line, don't pollute the user's output).
    """
    if not archived:
        return ""
    ids = " / ".join(t.id for t in archived)
    return f"⏰ 自动归档 {len(archived)} 个逾期任务：{ids}\n"


def _compute_tree_indent(tasks: list) -> dict[str, str]:
    """Return a mapping ``task_id → indent_prefix`` for tree display.

    Children get ``"  └ "`` (2 spaces + └ + space); grandchildren get
    ``"    └ "``. Tasks without a parent (or whose parent is not in the
    list) get an empty string. Indent is per-depth only — we don't try
    to draw ascii branches between siblings.
    """
    by_id = {t.id: t for t in tasks if t.id}
    depth: dict[str, int] = {}

    def get_depth(tid: str | None, _seen: set | None = None) -> int:
        if not tid or tid not in by_id:
            return 0
        if _seen is None:
            _seen = set()
        if tid in _seen:
            return 0  # avoid cycle; treat as root
        _seen.add(tid)
        if tid in depth:
            return depth[tid]
        parent = by_id[tid].parent
        if not parent or parent not in by_id:
            depth[tid] = 0
        else:
            depth[tid] = get_depth(parent, _seen) + 1
        return depth[tid]

    out: dict[str, str] = {}
    for t in tasks:
        d = get_depth(t.id)
        if d == 0:
            out[t.id or ""] = ""
        elif d == 1:
            out[t.id or ""] = "  └ "
        else:
            out[t.id or ""] = "    └ "
    return out


def _todo_list(args: argparse.Namespace) -> int:
    """``x todo list [选项]`` — 列出任务表格（已被 run 解析过）。

    对应 BDD：`docs/behaviors/todo-list-behavior.md`（8 个场景）。
    v0.5 Phase B: 增加 `--tree` 显式树形展示（自动启用 if 存在 parent）。

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

    # v0.5 Phase D — 显式 --sort 校验（argparse choices 给英文错误，加中文友好提示）
    sort_mode: str = getattr(args, "sort", "priority") or "priority"
    if sort_mode not in ("priority", "deadline", "created", "time"):
        print(
            f"❌ 无效的 sort 值：{sort_mode}（合法：priority / deadline / created / time）",
            file=sys.stderr,
        )
        return 2

    tag: str | None = args.tag
    include_archived: bool = bool(getattr(args, "include_archived", False))
    explicit_tree: bool = bool(getattr(args, "tree", False))
    only_reminding: bool = bool(getattr(args, "reminding", False))

    # 0. Auto-archive hook (opt-in, default disabled).
    store = TaskStore()
    archived = _auto_archive_overdue(store)
    sys.stdout.write(_render_auto_archive_summary(archived))

    # 2. 取任务列表（默认不含归档；--all 包含）
    tasks = store.list_tasks(include_archived=include_archived)

    # 3. 应用过滤（AND 关系，BDD §场景 7）
    if status is not None or priority is not None or tag is not None:
        tasks = [
            t for t in tasks
            if _matches_list_filters(t, status=status, priority=priority, tag=tag)
        ]

    # v0.5 Phase C — --reminding filter (BDD §场景 9)
    if only_reminding:
        tasks = [t for t in tasks if t.remind]

    # v0.5 Phase D — 排序（BDD todo-sort-behavior.md §场景 1-4）
    sort_mode = getattr(args, "sort", "priority")
    if sort_mode == "priority":
        # urgent > high > medium > low, then by created asc as tiebreaker
        tasks.sort(
            key=lambda t: (
                _PRIORITY_SORT_WEIGHT.get(
                    t.priority.value if isinstance(t.priority, Priority) else str(t.priority),
                    99,
                ),
                t.created or "",
                t.name,
            )
        )
    elif sort_mode == "deadline":
        # ascending; None deadlines go last
        tasks.sort(
            key=lambda t: (t.deadline is None, t.deadline or "9999-99-99", t.created or "")
        )
    elif sort_mode == "created":
        tasks.sort(key=lambda t: (t.created or "9999-99-99", t.name))
    elif sort_mode == "time":
        # by time ascending; no-time goes last (fallback deadline)
        tasks.sort(
            key=lambda t: (
                t.time is None,
                t.time or "99:99",
                t.deadline or "9999-99-99",
            )
        )

    # 4. 输出
    if not tasks:
        # BDD §场景 6：空仓库 / 无匹配 → 提示信息 + 退出码 0
        print("📭 没有任务（试试 x todo add \"任务名\" 创建第一个）")
        return 0

    # v0.5 Phase B — 自动树形 / 显式树形
    has_parent = any(t.parent for t in tasks)
    use_tree = explicit_tree or has_parent
    indent_map: dict[str, str] = _compute_tree_indent(tasks) if use_tree else {}

    # v0.5 Phase D — 颜色控制（BDD §场景 9-11）
    color_enabled = False if getattr(args, "no_color", False) else None  # None = auto

    # v0.5 Phase E — 依赖未完成标记（BDD §场景 6, 7）
    # A task has unfulfilled dep when any of its `depends` is in active+pending.
    active_pending_ids = {
        t.id for t in tasks
        if t.id
        and t.status != TaskStatus.ARCHIVED
    }
    has_unfulfilled = {
        t.id: any(
            dep_id in active_pending_ids
            for dep_id in (t.depends or [])
        )
        for t in tasks
    }

    # 计算每列的显示宽度（取表头与所有数据行的最大值），
    # 用 display-width 而非字符数，CJK 字符按 2 宽算，确保对齐
    list_columns = _LIST_COLUMNS_TEMPLATE(color_enabled)
    header_cells = [h for h, _ in list_columns]
    # v0.5 Phase E: name column (idx=1) gets the 🔒 prefix when unfulfilled
    rows: list[list[str]] = []
    for t in tasks:
        row: list[str] = []
        for col_idx, (_, col) in enumerate(list_columns):
            if col_idx == 1:
                # Name column
                cell = _list_name_cell(t, has_unfulfilled_dep=has_unfulfilled.get(t.id, False))
            else:
                cell = col(t)
            row.append(cell)
        rows.append(row)
    col_widths = [
        max(
            [display_width(header_cells[i])]
            + [display_width(row[i]) for row in rows]
        )
        for i in range(len(list_columns))
    ]

    # 表头
    print("  ".join(pad(c, col_widths[i]) for i, c in enumerate(header_cells)))
    # 分隔线（用 ─ 增强可视化）
    print("  ".join("─" * col_widths[i] for i in range(len(list_columns))))
    # 数据行（树形模式下前缀 indent 加在整行最前）
    for i, row in enumerate(rows):
        prefix = indent_map.get(tasks[i].id or "", "") if use_tree else ""
        print(prefix + "  ".join(pad(c, col_widths[j]) for j, c in enumerate(row)))
    return 0


# ============================================================
#  x todo add
# ============================================================


def _todo_add(args: argparse.Namespace) -> int:
    """处理 ``x todo add <名称> [选项]`` 命令（已被 run 解析过）。

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

    # v0.5 Phase A — time precision (BDD §场景 1-5, 9-10, 13)
    time_str: str | None = None
    end_time_str: str | None = None
    duration_min: int | None = None
    if args.time is not None and args.time != "":
        try:
            validate_time(args.time)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        time_str = args.time
    if args.end_time is not None and args.end_time != "":
        try:
            validate_time(args.end_time)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        end_time_str = args.end_time
    if args.duration is not None and args.duration != "":
        try:
            duration_min = parse_duration(args.duration)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    # BDD §场景 5：--end-time 与 --duration 互斥
    if end_time_str is not None and duration_min is not None:
        print(
            "❌ --end-time 与 --duration 互斥，不能同时使用",
            file=sys.stderr,
        )
        return 2

    # BDD §场景 13：end_time 必须 >= time（需要 time 已传入）
    if time_str is not None and end_time_str is not None:
        from core.slug import _time_to_minutes
        if _time_to_minutes(end_time_str) < _time_to_minutes(time_str):
            print(
                f"❌ end_time ({end_time_str}) 早于 time ({time_str})",
                file=sys.stderr,
            )
            return 2

    # v0.5 Phase B — --parent 校验（BDD §场景 3, 4）
    parent_id: str | None = None
    if args.parent is not None and args.parent != "":
        parent_id = args.parent
        # Existence + depth check
        store_for_check = TaskStore()
        parent_task = store_for_check.get_task(parent_id, include_archived=False)
        if parent_task is None:
            print(
                f"❌ 父任务不存在：{parent_id}",
                file=sys.stderr,
            )
            return 3
        # Depth check: parent must be at depth ≤ 1 (root=0 or child=1).
        # Allowed chain: root → child → grandchild (new) = depth 2.
        # Reject if parent is itself a grandchild (depth 2), which would make new task great-grandchild (depth 3).
        # Compute parent depth by walking the chain.
        depth = 0
        current = parent_task
        visited: set[str] = set()
        while current and current.parent:
            if current.id in visited:
                break  # cycle, treat as depth 0
            visited.add(current.id)
            depth += 1
            current = store_for_check.get_task(current.parent, include_archived=False)
        if depth >= 2:
            print(
                f"❌ 子任务最多 2 层：{parent_id} 已经是孙任务",
                file=sys.stderr,
            )
            return 2

    # v0.5 Phase B — --parent 校验（BDD §场景 3, 4）
    parent_id: str | None = None
    if args.parent is not None and args.parent != "":
        parent_id = args.parent
        # Existence + depth check
        store_for_check = TaskStore()
        parent_task = store_for_check.get_task(parent_id, include_archived=False)
        if parent_task is None:
            print(
                f"❌ 父任务不存在：{parent_id}",
                file=sys.stderr,
            )
            return 3
        # Depth check: parent must be at depth ≤ 1 (root=0 or child=1).
        # Allowed chain: root → child → grandchild (new) = depth 2.
        # Reject if parent is itself a grandchild (depth 2), which would make new task great-grandchild (depth 3).
        # Compute parent depth by walking the chain.
        depth = 0
        current = parent_task
        visited: set[str] = set()
        while current and current.parent:
            if current.id in visited:
                break  # cycle, treat as depth 0
            visited.add(current.id)
            depth += 1
            current = store_for_check.get_task(current.parent, include_archived=False)
        if depth >= 2:
            print(
                f"❌ 子任务最多 2 层：{parent_id} 已经是孙任务",
                file=sys.stderr,
            )
            return 2

    # v0.5 Phase C — --remind 校验（BDD §场景 5, 12）
    remind_list: list[str] | None = None
    if args.remind is not None and args.remind != "":
        try:
            remind_list = parse_remind(args.remind)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    # v0.5 Phase D — repeat rule（BDD §场景 1-7）
    repeat_rule: dict[str, str] | None = None
    if args.repeat is not None and args.repeat != "":
        try:
            repeat_rule = parse_repeat(args.repeat)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    # v0.5 Phase E — depends (validation: all must exist)
    depends_list: list[str] | None = None
    if args.depends is not None and args.depends != "":
        deps = [d.strip() for d in args.depends.split(",") if d.strip()]
        if deps:
            from core.storage import TaskStore as _TS
            for d in deps:
                if _TS().get_task(d, include_archived=False) is None:
                    print(f"❌ 依赖任务不存在：{d}", file=sys.stderr)
                    return 3
            depends_list = deps

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
        time=time_str,
        end_time=end_time_str,
        duration_min=duration_min,
        parent=parent_id,
        remind=remind_list,
        repeat=repeat_rule,
        depends=depends_list,
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
    return _maybe_expand_template(task, args.template)


def _maybe_expand_template(parent_task: Task, template_name: str | None) -> int:
    """v0.5 Phase E — expand add --template into parent + N children."""
    if not template_name:
        return 0  # nothing to do

    tmpl_dir = _todo_template_dir()
    tmpl_file = tmpl_dir / f"{template_name}.yaml"
    if not tmpl_file.exists():
        print(f"❌ 模板不存在：{template_name}", file=sys.stderr)
        # Rollback the parent (delete it) so user doesn't end up with orphan
        from core.storage import TaskStore as _TS
        try:
            _TS().remove_task(parent_task.id or parent_task.name, force=True)
        except Exception:  # noqa: BLE001
            pass
        return 3

    from core.parser import parse_frontmatter
    text = tmpl_file.read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(text)
    steps = meta.get("steps", [])

    if not steps:
        print(f"❌ 模板至少需要 1 个步骤：{template_name}", file=sys.stderr)
        return 2

    from datetime import date
    today = date.today().isoformat()
    store = TaskStore()

    # Dedup step names: same step name gets -001 / -002 suffix.
    # Note: the **folder name** is always `<parent_name>-<NNN>` where NNN is
    # the SEQUENTIAL position (1, 2, 3, …), not the dedup counter. This
    # ensures child folders are always uniquely named even when step names
    # collide (e.g. 3 "检查" steps → 检查-001/002/003 in YAML, but folder
    # names are parent-001/002/003).
    seen: dict[str, int] = {}
    created: list[Task] = []
    for seq_idx, raw_name in enumerate(steps, start=1):
        dedup_count = seen.get(raw_name, 0)
        seen[raw_name] = dedup_count + 1
        if dedup_count == 0:
            step_name = raw_name
        else:
            step_name = f"{raw_name}-{dedup_count + 1:03d}"
        child_folder_name = f"{parent_task.name}-{seq_idx:03d}"
        child = Task(
            id=None,  # auto-generate from name
            name=child_folder_name,
            status=TaskStatus.PENDING,
            priority=parent_task.priority,
            created=today,
            updated=today,
            deadline=parent_task.deadline,
            time=parent_task.time,
            end_time=parent_task.end_time,
            duration_min=parent_task.duration_min,
            parent=parent_task.id,  # parent: id (auto-cascades)
            folder=f"任务/{child_folder_name}",
        )
        try:
            store.add_task(child)
        except TaskAlreadyExistsError:
            # name collision; bump until unique
            child.name = f"{parent_task.name}-{count + 1:03d}-{step_name[:20]}"
            child.folder = f"任务/{child.name}"
            store.add_task(child)
        created.append(child)

    print(
        f"✅ 已创建 {len(created) + 1} 个任务（父 + {len(created)} 子）",
        file=sys.stderr,
    )
    return 0


# ============================================================
#  x todo stats
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

    # v0.5 Phase C — 有提醒任务数（BDD §场景 10）
    # 仅在 ≥ 1 时显示（与高优先级行风格一致）
    remind_active = stats.get("remind_active", 0)
    if remind_active > 0:
        lines.append(f"⏰ 有提醒任务数：{remind_active}")

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

    Plus (v0.5.x, opt-in): if auto-archive is enabled, run the hook
    before computing stats — the user-facing numbers then reflect the
    archived state. See
    ``docs/behaviors/todo-auto-archive-behavior.md`` §场景 4.
    """
    parser = argparse.ArgumentParser(
        prog="x todo stats",
        description="统计信息（状态分布 / 优先级分布 / 即将到期）",
    )
    parser.parse_args(list(args))  # 当前不接受额外参数

    store = TaskStore()

    # Auto-archive hook (opt-in). Summary goes to stdout BEFORE the
    # stats block so the user sees "you archived 3, here's the
    # updated stats" in one screen.
    archived = _auto_archive_overdue(store)
    sys.stdout.write(_render_auto_archive_summary(archived))

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
#  x todo init
# ============================================================


def _todo_init(args: argparse.Namespace) -> int:
    """``x todo init [--dir <path>]`` — bootstrap x-cli's independent TODO dir.

    对应 BDD：[docs/behaviors/todo-init-behavior.md](../docs/behaviors/todo-init-behavior.md)
    对应 storage：[docs/behaviors/todo-storage-behavior.md](../docs/behaviors/todo-storage-behavior.md)

    行为：
      - 默认在 :func:`core.paths.xcli_todo_dir()` 处创建 ``任务/`` + ``归档/`` + ``README.md``
      - ``--dir <path>`` 覆盖（仅本次 init）
      - ``XCLI_TODO_DIR`` 环境变量覆盖默认位置（测试 / 用户自定义）
      - 幂等：已存在则提示，**不**覆盖任何已有内容
      - 退出码：0 成功 / 1 无法创建（权限 / IO 错）/ 2 argparse 拒绝
    """
    target: Path = (
        Path(args.init_dir).expanduser()
        if args.init_dir
        else None
    )
    if target is None:
        # Honour XCLI_TODO_DIR (or legacy XAVIER_TODO_DIR via the paths helper)
        from core.paths import xcli_todo_dir

        target = xcli_todo_dir()

    active = target / "任务"
    archive = target / "归档"
    readme = target / "README.md"

    try:
        active.mkdir(parents=True, exist_ok=True)
        archive.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(
            f"❌ 无法创建目录 {target!r}：{exc}",
            file=sys.stderr,
        )
        return 1

    # Idempotent README: only write if missing so the user can edit it
    # locally and we won't clobber their notes.
    if not readme.exists():
        readme.write_text(
            "# x-cli TODO store\n\n"
            "> This is the **x-cli independent** TODO database. "
            "If you are migrating from another TODO system, point\n"
            "> ``x todo import --from <other_dir>`` at the source directory. "
            "Imports are one-way and read-only.\n",
            encoding="utf-8",
        )

    if any([args.init_dir]):
        # ``--dir`` was explicit: always show "已创建" (intent: bootstrap
        # a fresh location). Otherwise show "已存在" if it was already
        # there.
        verb = "已创建"
    else:
        verb = "已创建" if not (target / "README.md").read_text(encoding="utf-8").startswith(
            "# x-cli TODO 数据库"
        ) else "已存在"

    print(f"✅ TODO 目录{verb}：{target}")
    print("   - 任务\\")
    print("   - 归档\\")
    print("   - README.md")
    print()
    print("💡 试用：x todo add \"我的第一个任务\"")
    return 0


# ============================================================
#  x todo import
# ============================================================


def _todo_import(args: argparse.Namespace) -> int:
    """``x todo import --from <src> [--to <dst>] [--dry-run]`` — one-way migration.

    对应 BDD：[docs/behaviors/todo-import-behavior.md](../docs/behaviors/todo-import-behavior.md)

    行为：
      - 读源目录的 ``任务/`` + ``归档/`` 子目录
      - 解析每个 ``<name>/TODO.md``（含 YAML frontmatter）
      - 复制到目标目录（默认 :func:`core.paths.xcli_todo_dir()`）
      - **不**写回源；**不**删除源文件
      - 重复（同 name 已存在）跳过，不覆盖
      - 单个文件解析失败不阻塞其他
      - 退出码：0 成功 / 1 源目录不存在 / 2 argparse 拒绝
    """
    from core.paths import xcli_todo_dir

    src = Path(args.src_dir).expanduser().resolve()
    dst = (
        Path(args.dst_dir).expanduser().resolve()
        if args.dst_dir
        else xcli_todo_dir()
    )

    if not src.is_dir():
        print(f"❌ 源目录不存在：{src}", file=sys.stderr)
        return 1

    if not args.dry_run:
        # Ensure destination structure exists (mkdir 任务/ + 归档/)
        (dst / "任务").mkdir(parents=True, exist_ok=True)
        (dst / "归档").mkdir(parents=True, exist_ok=True)

    imported = 0
    skipped_dup = 0
    skipped_yaml = 0
    for area, target_area in (("任务", dst / "任务"), ("归档", dst / "归档")):
        src_area = src / area
        if not src_area.is_dir():
            continue
        for task_dir in sorted(src_area.iterdir()):
            if not task_dir.is_dir():
                continue
            todo_md = task_dir / "TODO.md"
            if not todo_md.is_file():
                continue
            name = task_dir.name
            if (target_area / name).is_dir() and not args.dry_run:
                # Already exists at destination — skip (don't overwrite)
                skipped_dup += 1
                continue
            try:
                text = todo_md.read_text(encoding="utf-8")
                metadata, body = parse_frontmatter(text)
            except (ValueError, OSError) as exc:
                print(
                    f"⚠️ 跳过 {name!r}（解析失败）：{exc}",
                    file=sys.stderr,
                )
                skipped_yaml += 1
                continue
            if args.dry_run:
                imported += 1  # would have imported
                continue
            # Materialise at destination: copy the source directory verbatim
            # (frontmatter + body preserved by round-tripping through Task model).
            try:
                task = Task.from_frontmatter(metadata, body=body)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"⚠️ 跳过 {name!r}（Task 模型构造失败）：{exc}",
                    file=sys.stderr,
                )
                skipped_yaml += 1
                continue
            task.folder = f"{target_area.name}/{name}"
            (target_area / name).mkdir(parents=True, exist_ok=True)
            (target_area / name / "TODO.md").write_text(
                task.to_markdown(), encoding="utf-8"
            )
            imported += 1

    if args.dry_run:
        print(f"🔍 [dry-run] 将导入 {imported} 个任务（{skipped_dup} 个重复，{skipped_yaml} 个解析失败）")
    else:
        print(f"📥 迁移完成：导入 {imported} 个任务")
        if skipped_dup:
            print(f"   - 跳过 {skipped_dup} 个（重复）")
        if skipped_yaml:
            print(f"   - 跳过 {skipped_yaml} 个（解析失败）")
        print()
        print(f"💡 试用：x todo list")
    return 0


# ============================================================
#  x todo template (v0.5 Phase E)
# ============================================================


def _todo_template_dir() -> Path:
    """Return the templates directory under xcli_data_dir (creates if missing)."""
    from core.paths import xcli_data_dir
    d = Path(xcli_data_dir()) / "templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _todo_template(args: argparse.Namespace) -> int:
    """``x todo template create/list/remove`` — task template management.

    对应 BDD：``docs/behaviors/todo-template-behavior.md``（9 场景）。

    v0.5 范围：
    - 模板存储在 ``<xcli_data_dir>/templates/<name>.yaml``
    - add --template 展开为父任务 + N 个子任务（步骤去重自动加 -NNN 后缀）
    - 模板名直接对应文件名（中文 / 英文均可）
    """
    action = getattr(args, "_template_action", None)
    if action == "create":
        return _todo_template_create(args.name, args.steps)
    if action == "list":
        return _todo_template_list()
    if action == "remove":
        return _todo_template_remove(args.name)
    print(f"❌ 未知的 template 子命令：{action}", file=sys.stderr)
    return 2


def _todo_template_create(name: str, steps_raw: str) -> int:
    """Create a template file under xcli_data_dir/templates/."""
    from core.parser import dump_frontmatter
    steps = [s.strip() for s in steps_raw.split(",") if s.strip()]
    if not steps:
        print("❌ 模板至少需要 1 个步骤", file=sys.stderr)
        return 2
    tmpl_dir = _todo_template_dir()
    target = tmpl_dir / f"{name}.yaml"
    if target.exists():
        print(
            f"❌ 模板已存在：{name}（请用 remove 先删，或换名字）",
            file=sys.stderr,
        )
        return 5
    metadata = {"name": name, "steps": steps}
    target.write_text(
        dump_frontmatter(metadata, body=""), encoding="utf-8"
    )
    print(f"✅ 模板已创建：{name}（{len(steps)} 步）")
    return 0


def _todo_template_list() -> int:
    """List all template names."""
    tmpl_dir = _todo_template_dir()
    templates = sorted(p.stem for p in tmpl_dir.glob("*.yaml"))
    if not templates:
        print("📭 没有已创建的模板（试试 x todo template create <name> --steps ...）")
        return 0
    print("已创建的模板：")
    for name in templates:
        print(f"  • {name}")
    return 0


def _todo_template_remove(name: str) -> int:
    """Delete a template file."""
    tmpl_dir = _todo_template_dir()
    target = tmpl_dir / f"{name}.yaml"
    if not target.exists():
        print(f"❌ 模板不存在：{name}", file=sys.stderr)
        return 3
    target.unlink()
    print(f"✅ 模板已删除：{name}")
    return 0


# ============================================================
#  x todo export (v0.5 Phase E)
# ============================================================


def _todo_export_serialize(task, fmt: str) -> str:
    """Serialize a single Task to a string line for the given format."""
    if fmt == "json":
        # Full frontmatter + body as a JSON object
        import json
        meta, body = task.to_frontmatter_body()
        meta["body"] = body
        return json.dumps(meta, ensure_ascii=False, sort_keys=False)
    if fmt == "csv":
        # Flat row: id, name, status, priority, deadline, time, end_time,
        # duration_min, parent, remind, repeat, depends, folder, archived_at, tags
        tags = ";".join(task.tags) if task.tags else ""
        remind = ";".join(task.remind) if task.remind else ""
        depends = ";".join(task.depends) if task.depends else ""
        repeat = (
            ";".join(f"{k}={v}" for k, v in (task.repeat or {}).items())
            if task.repeat
            else ""
        )
        # Quote any field containing comma or quote
        def _quote(s: str) -> str:
            if s and ("," in s or '"' in s or "\n" in s):
                return f'"{s.replace(chr(34), chr(34) * 2)}"'
            return s

        return ",".join(
            [
                _quote(task.id or ""),
                _quote(task.name or ""),
                _quote(
                    task.status.value
                    if hasattr(task.status, "value")
                    else str(task.status)
                ),
                _quote(
                    task.priority.value
                    if hasattr(task.priority, "value")
                    else str(task.priority)
                ),
                _quote(task.deadline or ""),
                _quote(task.time or ""),
                _quote(task.end_time or ""),
                _quote(str(task.duration_min) if task.duration_min is not None else ""),
                _quote(task.parent or ""),
                _quote(remind),
                _quote(repeat),
                _quote(depends),
                _quote(task.folder or ""),
            ]
        )
    if fmt == "md":
        # Human-readable row
        status = (
            task.status.value
            if hasattr(task.status, "value")
            else str(task.status)
        )
        priority = (
            task.priority.value
            if hasattr(task.priority, "value")
            else str(task.priority)
        )
        return (
            f"| {task.id or ''} | {task.name} | {status} | "
            f"{priority} | {task.deadline or '-'} | {task.time or '-'} |"
        )
    return ""


def _todo_export_header(fmt: str) -> str:
    if fmt == "csv":
        return (
            "id,name,status,priority,deadline,time,end_time,"
            "duration_min,parent,remind,repeat,depends,folder"
        )
    if fmt == "md":
        return "| id | name | status | priority | deadline | time |"
    return ""


def _todo_export_separator(fmt: str) -> str:
    if fmt == "md":
        return "|---|---|---|---|---|---|"
    return ""


def _todo_export(args: argparse.Namespace) -> int:
    """``x todo export --format json|csv|md`` — bulk export task data.

    对应 BDD：``docs/behaviors/todo-export-behavior.md``（8 场景）。
    """
    fmt = args.format
    include_archived = bool(getattr(args, "all", False))
    output_path = getattr(args, "output", None)

    store = TaskStore()
    tasks = store.list_tasks(include_archived=include_archived)

    if fmt not in ("json", "csv", "md"):
        print(
            f"❌ 无效的 format：{fmt}（支持：json / csv / md）",
            file=sys.stderr,
        )
        return 2

    if output_path:
        out_path = Path(output_path)
        if not out_path.parent.exists():
            print(
                f"❌ 父目录不存在：{out_path.parent}",
                file=sys.stderr,
            )
            return 5
    else:
        out_path = None

    if fmt == "json":
        import json
        # Array of full frontmatter dicts
        data = []
        for t in tasks:
            meta, body = t.to_frontmatter_body()
            meta["body"] = body
            data.append(meta)
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        lines = [_todo_export_header(fmt)]
        if fmt == "md":
            lines.append(_todo_export_separator(fmt))
        for t in tasks:
            lines.append(_todo_export_serialize(t, fmt))
        text = "\n".join(lines) + "\n"

    if out_path:
        out_path.write_text(text, encoding="utf-8")
        print(f"✅ 已导出 {len(tasks)} 个任务到 {out_path}")
    else:
        print(text, end="" if text.endswith("\n") else "\n")
        print(f"✅ 已导出 {len(tasks)} 个任务到 stdout", file=sys.stderr)

    return 0
