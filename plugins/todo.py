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

from core.formatting import display_width, pad
from core.config import is_auto_archive_enabled
from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.parser import parse_frontmatter
from core.slug import parse_tags, unique_slug, validate_deadline, validate_time, parse_duration, compute_end_time
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
    Priority.HIGH.value: "🔥",
    Priority.MEDIUM.value: "⚡",
    Priority.LOW.value: "🐢",
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
                help='持续时间（如 90 / 90m / 1.5h；与 --end-time 互斥）',
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
            # BDD: docs/behaviors/todo-done-behavior.md（6 场景）
            sp = sub.add_parser(name, help="archive --reason done 的快捷方式")
            sp.add_argument("id", help="任务 ID")
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
    """``x todo done <id>`` — ``x todo archive <id> --reason done`` 的快捷方式。

    对应 BDD：``docs/behaviors/todo-done-behavior.md``（6 场景）。

    语义上**完全等价**于 ``archive --reason done``（80% 的归档场景）：
    复用 ``_todo_archive`` 的全部逻辑与退出码，不重复实现。
    """
    if not args.id or not args.id.strip():
        print("❌ 任务 ID 不能为空", file=sys.stderr)
        return 3

    # Build a fake Namespace to delegate to _todo_archive — DRY:
    # the archive handler is the single source of truth for
    # folder move + frontmatter update + inventory maintenance.
    archive_args = argparse.Namespace(
        id=args.id.strip(),
        reason="done",
    )
    return _todo_archive(archive_args)


# ============================================================
#  x todo update
# ============================================================


def _todo_update(args: argparse.Namespace) -> int:
    """处理 ``x todo update <id> [选项]`` 命令（已被 run 解析过）。

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
        and args.time is None
        and args.end_time is None
        and args.duration is None
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
        parser.error(
            "at least one of --status / --priority / --deadline / --tags "
            "/ --time / --end-time / --duration is required"
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
            time=new_time,
            end_time=new_end_time,
            duration_min=new_duration_min,
            clear_time=clear_time,
            clear_end_time=clear_end_time,
            clear_duration_min=clear_duration,
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


def _list_priority_cell(task) -> str:
    """表格 Priority 列的展示值；带图标。"""
    if isinstance(task.priority, Priority):
        cell = task.priority.value
    else:
        cell = str(task.priority)
    icon = _PRIORITY_ICONS.get(cell, "")
    return f"{icon} {cell}" if icon else cell


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


# 列表命令的列定义（表头 + 取值函数），集中维护表格 schema
_LIST_COLUMNS: tuple[tuple[str, Callable[[object], str]], ...] = (
    ("ID", lambda t: t.id or t.name),
    ("Name", lambda t: t.name),
    ("Status", _list_status_cell),
    ("Priority", _list_priority_cell),
    ("Deadline", lambda t: t.deadline or "-"),
    ("Time", _list_time_cell),  # v0.5 Phase A
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


def _todo_list(args: argparse.Namespace) -> int:
    """``x todo list [选项]`` — 列出任务表格（已被 run 解析过）。

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

    # 0. Auto-archive hook (opt-in, default disabled).
    #    Per BDD §场景 1 — first step on entry. We do this AFTER
    #    validation because a user-supplied --status invalid shouldn't
    #    silently trigger an archive; but the archive itself runs once
    #    per list invocation so a follow-up --all or --status filter
    #    call sees the cleaned store. Note: archive errors are already
    #    swallowed inside _auto_archive_overdue.
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
            [display_width(header_cells[i])]
            + [display_width(row[i]) for row in rows]
        )
        for i in range(len(_LIST_COLUMNS))
    ]

    # 表头
    print("  ".join(pad(c, col_widths[i]) for i, c in enumerate(header_cells)))
    # 分隔线（用 ─ 增强可视化）
    print("  ".join("─" * col_widths[i] for i in range(len(_LIST_COLUMNS))))
    # 数据行
    for row in rows:
        print("  ".join(pad(c, col_widths[i]) for i, c in enumerate(row)))
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