"""Read-only and reporting actions for the x todo plugin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from core.config import is_auto_archive_enabled
from core.formatting import display_width, pad
from core.models import Priority, Task, TaskStatus
from core.parser import parse_frontmatter
from core.storage import (
    TaskAlreadyArchivedError,
    TaskNotFoundError,
    TaskStore,
)
from core.task_service import TaskService
from plugins.todo_presenters import (
    _LIST_COLUMNS,
    _LIST_COLUMNS_TEMPLATE,
    _PRIORITY_SORT_WEIGHT,
    _coerce_priority,
    _coerce_status,
    _compute_tree_indent,
    _list_name_cell,
    _render_auto_archive_summary,
    _render_stats,
)

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

    service = TaskService()
    store = service.store

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

    matches = service.search(
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
        # Maintain inventory without hiding consistency failures.
        try:
            store.update_inventory_on_archive(old_status)
        except Exception as exc:  # noqa: BLE001 — defensive
            print(
                "⚠️ 自动归档已完成，但 TODO.md 索引更新失败："
                f"{task.id or task.name}（{exc}）",
                file=sys.stderr,
            )

    return archived


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
    service = TaskService()
    store = service.store
    archived = _auto_archive_overdue(store)
    sys.stdout.write(_render_auto_archive_summary(archived))

    # 2. 取任务列表（默认不含归档；--all 包含）
    tasks = service.list(
        include_archived=include_archived,
        status=status,
        priority=priority,
        tag=tag,
    )

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
    # A task has unfulfilled dep when any of its `depends` matches a
    # non-archived task by EITHER id OR name (since `task.depends` is
    # whatever the user passed to --depends, typically a name like
    # "复习" not the auto-generated slug id).
    active_keys: set[str] = set()
    for t in tasks:
        if t.status != TaskStatus.ARCHIVED and t.id:
            active_keys.add(t.id)
            active_keys.add(t.name)

    def _has_unfulfilled_dep(t) -> bool:
        return any(
            dep_id in active_keys
            for dep_id in (t.depends or [])
        )

    has_unfulfilled = {
        t.id: _has_unfulfilled_dep(t)
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

    service = TaskService()
    store = service.store

    # Auto-archive hook (opt-in). Summary goes to stdout BEFORE the
    # stats block so the user sees "you archived 3, here's the
    # updated stats" in one screen.
    archived = _auto_archive_overdue(store)
    sys.stdout.write(_render_auto_archive_summary(archived))

    broken = _find_broken_tasks(store.todo_dir)

    stats = service.stats()
    sys.stdout.write(_render_stats(stats))

    if broken:
        for rel_path, err in broken:
            sys.stderr.write(
                f"❌ 解析任务失败：{rel_path}（YAML 格式错误：{err}）\n"
            )
        return 5

    return 0


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
                _quote(tags),
                _quote(
                    (task.extra or {}).get("note", "")
                    if task.extra
                    else ""
                ),
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
            "duration_min,parent,remind,repeat,depends,folder,tags,note"
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

    service = TaskService()
    tasks = service.list(include_archived=include_archived)

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
