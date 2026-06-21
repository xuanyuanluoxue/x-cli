"""x - Xavier 个人工具集的统一 CLI 入口

Phase 1 (MVP): 单文件实现，主入口 + x todo 子命令（待实现）。
Phase 4: 拆出 plugins/ 目录，每个子命令独立文件。
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Sequence

__version__ = "0.1.0"


# ============================================================
#  x todo 命令实现（MVP 阶段 inline 在主入口）
# ============================================================

TODO_ACTIONS: tuple[str, ...] = ("list", "add", "update", "archive", "stats")


def _todo_register(parser: argparse.ArgumentParser) -> None:
    """注册 x todo 的子命令参数"""
    sub = parser.add_subparsers(dest="todo_action", required=False, metavar="ACTION")
    for name in TODO_ACTIONS:
        sub.add_parser(name, help=f"{name} 命令")


def _todo_not_implemented(action: str) -> int:
    """x todo 各子命令的占位实现（Phase 1 MVP 阶段）"""
    print(f"🚧 x todo {action} 还未实现", file=sys.stderr)
    return 1


def _todo_run(args: Sequence[str]) -> int:
    """x todo 入口：解析参数并分发到子命令"""
    parser = argparse.ArgumentParser(prog="x todo", description="TODO 管理")
    _todo_register(parser)
    parsed = parser.parse_args(list(args))

    if not parsed.todo_action:
        parser.print_help()
        return 0

    return _todo_not_implemented(parsed.todo_action)


# ============================================================
#  主入口
# ============================================================

# 子命令注册表：name -> handler(args) -> exit_code
# Phase 1 只注册 todo；Phase 4 拆插件后改用 importlib.import_module
SUBCOMMAND_HANDLERS: dict[str, Callable[[Sequence[str]], int]] = {
    "todo": _todo_run,
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