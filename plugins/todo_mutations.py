"""Mutation and bootstrap actions for the x todo plugin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.models import Priority, Task, TaskStatus
from core.parser import parse_frontmatter
from core.slug import (
    parse_duration,
    parse_remind,
    parse_repeat,
    parse_tags,
    unique_slug,
    validate_deadline,
    validate_time,
)
from core.storage import (
    TaskAlreadyArchivedError,
    TaskAlreadyExistsError,
    TaskNotFoundError,
    TaskStore,
)

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
                depends=args.depends,
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
        and args.repeat is None
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
        parser.add_argument("--repeat", help='重复规则（"" 清除）')
        parser.error(
            "at least one of --status / --priority / --deadline / --tags "
            "/ --time / --end-time / --duration / --parent / --remind / "
            "--repeat / --depends is required"
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
                # Allow depending on archived tasks (they're "satisfied"
                # by default; user may be re-referencing a known predecessor).
                if _TS().get_task(d, include_archived=True) is None:
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
                # Allow depending on archived tasks (satisfied by default)
                if _TS().get_task(d, include_archived=True) is None:
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
        return 3 if _rollback_template_tasks([parent_task]) else 1

    from core.parser import parse_frontmatter
    text = tmpl_file.read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(text)
    steps = meta.get("steps", [])

    if not steps:
        print(f"❌ 模板至少需要 1 个步骤：{template_name}", file=sys.stderr)
        return 2 if _rollback_template_tasks([parent_task]) else 1

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
        collision_suffix = 1
        while True:
            try:
                store.add_task(child)
                break
            except TaskAlreadyExistsError:
                base_name = (
                    f"{parent_task.name}-{seq_idx:03d}-{step_name[:20]}"
                )
                child.name = (
                    base_name
                    if collision_suffix == 1
                    else f"{base_name}-{collision_suffix}"
                )
                child.folder = f"任务/{child.name}"
                collision_suffix += 1
        created.append(child)

    print(
        f"✅ 已创建 {len(created) + 1} 个任务（父 + {len(created)} 子）",
        file=sys.stderr,
    )
    return 0


def _rollback_template_tasks(tasks: list[Task]) -> bool:
    """Remove template-created tasks in reverse order and report failures."""
    store = TaskStore()
    failures: list[str] = []
    for task in reversed(tasks):
        try:
            store.remove_task(task.id or task.name, force=True)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{task.id or task.name}（{exc}）")
    if failures:
        print(
            "⚠️ 父任务回滚失败，需人工处理："
            + "、".join(failures),
            file=sys.stderr,
        )
        return False
    return True


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
        print("💡 试用：x todo list")
    return 0


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
