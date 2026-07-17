"""``x note`` plugin for topic-oriented local Markdown notes."""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Sequence

from core.formatting import display_width, pad
from core.note import Note, NoteDataError, NoteNotFoundError, NoteStore


NOTE_ACTIONS: tuple[str, ...] = ("add", "list", "show", "search")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是正整数") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def register(parser: argparse.ArgumentParser) -> None:
    """Register ``x note`` P0 actions and arguments."""
    sub = parser.add_subparsers(dest="note_action", required=False, metavar="ACTION")

    add = sub.add_parser("add", help="创建主题笔记")
    add.add_argument("title", help="笔记标题")
    add.add_argument("--body", default="", help="笔记正文（默认空）")
    add.add_argument("--tags", default="", help="标签，英文逗号分隔")

    listing = sub.add_parser("list", help="列出最近笔记")
    listing.add_argument("--tag", help="按单个标签精确过滤（不区分大小写）")
    listing.add_argument("--limit", type=_positive_int, default=20, metavar="N", help="最多显示数量（默认 20）")

    show = sub.add_parser("show", help="显示一篇笔记")
    show.add_argument("id", help="完整笔记 ID")

    search = sub.add_parser("search", help="搜索标题、标签和正文")
    search.add_argument("keyword", help="搜索关键词")
    search.add_argument("--limit", type=_positive_int, default=20, metavar="N", help="最多显示数量（默认 20）")


def run(args: Sequence[str]) -> int:
    """Parse and execute ``x note`` arguments."""
    parser = argparse.ArgumentParser(
        prog="x note",
        description="本地主题笔记（Markdown + frontmatter）",
    )
    register(parser)

    if list(args) == ["help"]:
        parser.print_help()
        return 0

    parsed = parser.parse_args(list(args))
    if not parsed.note_action:
        parser.print_help()
        return 0

    handler = globals()[f"_note_{parsed.note_action}"]
    return handler(parsed)


def _note_add(args: argparse.Namespace) -> int:
    store = NoteStore()
    try:
        note = store.add(
            args.title,
            body=args.body,
            tags=args.tags.split(","),
        )
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except NoteDataError as exc:
        _print_data_error(exc)
        return 5
    print(f"✅ 笔记已创建：{note.title}（ID: {note.id}）")
    return 0


def _note_list(args: argparse.Namespace) -> int:
    try:
        notes = NoteStore().list_notes(tag=args.tag, limit=args.limit)
    except NoteDataError as exc:
        _print_data_error(exc)
        return 5
    sys.stdout.write(_render_note_table(notes))
    return 0


def _note_show(args: argparse.Namespace) -> int:
    try:
        note = NoteStore().get(args.id)
    except NoteNotFoundError:
        print(f"❌ 笔记不存在：{args.id}", file=sys.stderr)
        return 3
    except NoteDataError as exc:
        _print_data_error(exc)
        return 5
    sys.stdout.write(_render_note(note))
    return 0


def _note_search(args: argparse.Namespace) -> int:
    if not args.keyword.strip():
        print("❌ 搜索关键词不能为空", file=sys.stderr)
        return 2
    try:
        notes = NoteStore().search(args.keyword, limit=args.limit)
    except NoteDataError as exc:
        _print_data_error(exc)
        return 5
    sys.stdout.write(_render_note_table(notes))
    return 0


_NOTE_COLUMNS: tuple[tuple[str, Callable[[Note], str]], ...] = (
    ("ID", lambda note: note.id),
    ("Title", lambda note: note.title),
    ("Tags", lambda note: ", ".join(note.tags) if note.tags else "-"),
    ("Updated", lambda note: note.updated_at),
)


def _render_note_table(notes: list[Note]) -> str:
    if not notes:
        return "📭 暂无笔记\n"
    headers = [header for header, _ in _NOTE_COLUMNS]
    rows = [[getter(note) for _, getter in _NOTE_COLUMNS] for note in notes]
    widths = [
        max([display_width(headers[index])] + [display_width(row[index]) for row in rows])
        for index in range(len(headers))
    ]
    lines = [
        "  ".join(pad(header, widths[index]) for index, header in enumerate(headers)),
        "  ".join("─" * width for width in widths),
    ]
    for row in rows:
        lines.append("  ".join(pad(cell, widths[index]) for index, cell in enumerate(row)))
    return "\n".join(lines) + "\n"


def _render_note(note: Note) -> str:
    lines = [
        f"# {note.title}",
        "",
        f"ID: {note.id}",
        f"Tags: {', '.join(note.tags) if note.tags else '-'}",
        f"Created: {note.created_at}",
        f"Updated: {note.updated_at}",
    ]
    if note.body.strip():
        lines.extend(["", note.body.rstrip("\n")])
    return "\n".join(lines) + "\n"


def _print_data_error(exc: NoteDataError) -> None:
    print(f"❌ 笔记数据损坏：{exc}", file=sys.stderr)
