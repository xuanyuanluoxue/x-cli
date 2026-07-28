"""Lifecycle actions for the x todo plugin."""

from __future__ import annotations

import argparse
import sys

from core.formatting import display_width, pad
from core.models import ArchiveReason, Task, TaskStatus
from core.storage import (
    TaskAlreadyActiveError,
    TaskAlreadyArchivedError,
    TaskAlreadyExistsError,
    TaskNotArchivedError,
    TaskNotFoundError,
    TaskStore,
)
from plugins.todo_presenters import _list_time_cell

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
    for t in archived_set:
        old_status_str = (
            (t.extra or {}).get("_orig_status_before_archive", "pending")
        )
        try:
            old_status = TaskStatus(old_status_str)
        except ValueError:
            old_status = TaskStatus.PENDING
        try:
            store.update_inventory_on_archive(old_status)
        except Exception as exc:  # noqa: BLE001
            print(
                "⚠️ 任务已归档，但 TODO.md 索引更新失败："
                f"{t.id or t.name}（{exc}）",
                file=sys.stderr,
            )

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
