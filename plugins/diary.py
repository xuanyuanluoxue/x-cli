"""``x diary`` plugin: append local entries and list recent diary dates."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from core.diary import DiaryStore


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是正整数") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def register(parser: argparse.ArgumentParser) -> None:
    """Register the P0 diary arguments on ``parser``."""
    parser.add_argument(
        "content",
        nargs="?",
        help='要写入的日记内容；传 "list" 列出最近日期',
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=None,
        metavar="N",
        help="list 最多显示的日期数（默认 7）",
    )


def run(args: Sequence[str]) -> int:
    """Parse and execute ``x diary`` arguments."""
    parser = argparse.ArgumentParser(
        prog="x diary",
        description='本地日记（写入：x diary "内容"；列表：x diary list）',
    )
    register(parser)

    if list(args) == ["help"]:
        parser.print_help()
        return 0

    parsed = parser.parse_args(list(args))
    if parsed.content is None:
        parser.print_help()
        return 0

    store = DiaryStore()
    if parsed.content == "list":
        limit = parsed.limit if parsed.limit is not None else 7
        dates = store.list_dates(limit=limit)
        if not dates:
            print("📭 暂无日记")
            return 0
        print(f"最近 {limit} 个日记日期：")
        for day in dates:
            print(day.isoformat())
        return 0

    if parsed.limit is not None:
        print("❌ --limit 只能与 x diary list 一起使用", file=sys.stderr)
        return 2

    try:
        path = store.append(parsed.content)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    print(f"✅ 日记已写入：{path.stem}")
    return 0
