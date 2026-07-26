"""Parser and dispatcher facade for the ``x todo`` command family.

Business actions live in ``todo_lifecycle``, ``todo_mutations`` and
``todo_queries``; pure rendering helpers live in ``todo_presenters``.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from core.models import Priority, TaskStatus
from plugins.todo_lifecycle import (
    _todo_archive,
    _todo_done,
    _todo_reminder,
    _todo_remove,
    _todo_repeat_fire,
    _todo_restore,
)
from plugins.todo_mutations import (
    _todo_add,
    _todo_import,
    _todo_init,
    _todo_template,
    _todo_update,
)
from plugins.todo_queries import (
    _todo_export,
    _todo_list,
    _todo_search,
    _todo_stats,
)


# ============================================================
#  Plugin contract: register() + run()
# ============================================================


# v0.5: flags whose value may legitimately start with '-' (so argparse's
# "expected one argument" check on the bare form must be bypassed).
# We rewrite `--flag -X` to `--flag=-X` before argparse sees it; the
# `=` form is accepted by argparse regardless of the value's leading
# character.  See ``todo-remind-behavior.md §场景 5`` and
# ``todo-time-precision-behavior.md §场景 10`` for the BDD contract
# ("❌ must be positive: -5m").
_DASH_VALUE_FLAGS: frozenset[str] = frozenset({"--remind", "--duration"})


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
            # v0.5 Phase D — repeat rule (also updateable, "" 清除)
            sp.add_argument(
                "--repeat",
                help='重复规则（"" 清除 repeat 字段）',
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
    # v0.6.1: ``x todo help``（位置别名）→ 打印 todo help 并退出。必须放在
    # dash-value 重写 + parse_args 之前；--help/-h 由 argparse 原生处理。
    if list(args) == ["help"]:
        parser = argparse.ArgumentParser(prog="x todo", description="TODO 管理")
        register(parser)
        parser.print_help()
        return 0

    # v0.5: argparse 默认拒单值参数的 '-X' 形式（"expected one argument"）。
    # 我们用 `--flag=-X` 让 argparse 接受（`=` 形式赋值绕过 looks_like_option
    # 检查），但 `parse_remind` / `parse_duration` 期望原始 `-X`——把前缀 `=`
    # 在 parse_args 后再剥掉。 见 ``_DASH_VALUE_FLAGS`` 上方注释。
    argv = list(args)
    for i, token in enumerate(argv):
        if token in _DASH_VALUE_FLAGS and i + 1 < len(argv):
            nxt = argv[i + 1]
            if nxt.startswith("-") and len(nxt) > 1:
                argv[i + 1] = f"={nxt}"
    parser = argparse.ArgumentParser(prog="x todo", description="TODO 管理")
    register(parser)
    parsed = parser.parse_args(argv)
    # 还原 `=` 前缀：让下游 parse_* 看到干净的 `-X`。
    for flag in _DASH_VALUE_FLAGS:
        value = getattr(parsed, flag.lstrip("-"), None)
        if isinstance(value, str) and value.startswith("="):
            setattr(parsed, flag.lstrip("-"), value[1:])

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
