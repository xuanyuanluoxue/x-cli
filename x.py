"""x - Personal CLI toolset for task tracking and credential management.

A small, focused CLI built around two subsystems:
  * x todo  - personal task tracking (YAML-frontmatter folders)
  * x secret - local credential store (single JSON file, file mode 600)

Entry point only. Subcommand handlers live in :mod:`plugins.todo` and
:mod:`plugins.secret`. See README.md for usage and COMMANDS.md for the
canonical command list.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Sequence

from core.config import AppConfig, ConfigError
from core.logging import get_logger, setup_logging

# Plugin handlers (Phase 4 split — see AGENTS.md "Phase 4 plugin split")
from plugins import todo as _todo_plugin
from plugins import secret as _secret_plugin

__version__ = "0.5.0"


# ============================================================
#  Subcommand dispatch (Phase 4 plugin registry)
# ============================================================

# Each plugin exposes a ``run`` callable that takes ``Sequence[str]``
# (everything after ``x <subcommand>``) and returns an exit code.
# Adding a new subcommand = drop a file in plugins/ + register here.
SUBCOMMAND_HANDLERS: dict[str, Callable[[Sequence[str]], int]] = {
    "todo": _todo_plugin.run,
    "secret": _secret_plugin.run,
}


# ============================================================
#  Backward-compat re-exports (for existing tests + scripts)
# ============================================================

# Tests import handler functions directly from ``x`` (e.g.
# ``from x import _todo_list``). Re-export them here so test code
# doesn't need to know about the plugin split.
from plugins.todo import (  # noqa: E402,F401 — re-exports
    _todo_list,
    _todo_add,
    _todo_update,
    _todo_archive,
    _todo_restore,
    _todo_search,
    _todo_done,
    _todo_stats,
    _todo_init,
    _todo_import,
    _todo_register,
    run as _todo_run,
    _render_stats,
    _find_broken_tasks,
    _LIST_COLUMNS,
    _coerce_status,
    _coerce_priority,
    _list_status_cell,
    _list_priority_cell,
    _matches_list_filters,
    _VALID_STATUS_HINT,
    _VALID_PRIORITY_HINT,
    TODO_ACTIONS,
)

from plugins.secret import (  # noqa: E402,F401 — re-exports
    _secret_list,
    _secret_get,
    _secret_set,
    _secret_update,
    _secret_rm,
    _secret_search,
    _secret_import,
    _secret_export,
    run as _secret_run,
    _copy_to_clipboard,
    _render_secret_table,
    _SECRET_LIST_COLUMNS,
    SECRET_ACTIONS,
)

# Shared display helpers — were in x.py before the split; tests + other
# modules import them as ``from x import _display_width``.
from core.formatting import display_width as _display_width  # noqa: E402,F401
from core.formatting import pad as _pad  # noqa: E402,F401

# Icon dicts — kept here for backward compat (they live in plugins/todo.py
# but were originally module-level globals in x.py).
from plugins.todo import _STATUS_ICONS, _PRIORITY_ICONS  # noqa: E402,F401


# ============================================================
#  Main entry point
# ============================================================


def build_parser() -> argparse.ArgumentParser:
    """构造主解析器：--version / --config / --log-level / --config-init / <subcommand> [args...]"""
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
        "--config",
        metavar="PATH",
        help="指定配置文件路径（覆盖默认 xcli_data_dir()/config.yaml）",
    )
    parser.add_argument(
        "--log-level",
        metavar="LEVEL",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL",
                 "debug", "info", "warning", "error", "critical"],  # case-insensitive
        help="全局日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL，大小写不敏感）",
    )
    parser.add_argument(
        "--config-init",
        action="store_true",
        help="把默认配置写入 xcli_data_dir()/config.yaml 然后退出",
    )
    parser.add_argument(
        "subcommand",
        nargs="?",
        metavar="SUBCOMMAND",
        help=f"子命令（{', '.join(SUBCOMMAND_HANDLERS)}）",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """主入口：解析 → 加载配置 + 日志 → 分发到子命令 handler"""
    parser = build_parser()
    parsed, remaining = parser.parse_known_args(argv if argv is not None else None)

    # --version 优先（最便宜的 early-exit）
    if parsed.version:
        print(f"x {__version__}")
        return 0

    # --config-init: 把默认配置写到 xcli_data_dir()/config.yaml 然后退出。
    # 在子命令分发之前 short-circuit —— 不需要 subcommand。
    if parsed.config_init:
        from core.paths import xcli_data_dir
        config_path = xcli_data_dir() / "config.yaml"
        if config_path.exists():
            print(f"❌ 配置已存在：{config_path}（用 --force 覆盖）", file=sys.stderr)
            return 2
        config_path.write_text(AppConfig.default().to_yaml(), encoding="utf-8")
        print(f"✅ 配置已写入：{config_path}")
        return 0

    # 加载配置（v0.4.x 新增）。CLI flag 优先（直接读指定文件），否则走
    # Subagent A 的 from_env_and_default（XCLI_CONFIG env > 默认文件 > 默认值）。
    try:
        if parsed.config:
            config = AppConfig.from_yaml_file(Path(parsed.config))
        else:
            config = AppConfig.from_env_and_default()
    except ConfigError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 5

    # CLI 上的 --log-level 覆盖 config 里的 log_level（最高优先级）。
    # argparse 的 choices 已经保证只接受合法值；这里再 upper 一下保证大小写一致。
    if parsed.log_level:
        from dataclasses import replace
        config = replace(config, log_level=parsed.log_level.upper())

    # 配置日志（v0.4.x 新增）。
    try:
        setup_logging(config.log_level, config.log_path)
    except Exception as exc:
        print(f"❌ 日志初始化失败：{exc}", file=sys.stderr)
        return 6
    log = get_logger("x.main")
    log.debug(
        "effective config: todo_dir=%s, log_level=%s",
        config.todo_dir,
        config.log_level,
    )

    # 把 config 派生的路径灌进环境变量，storage 层继续用 XCLI_TODO_DIR /
    # XCLI_SECRETS_DIR 读。setdefault —— 已经 set 的（用户显式 export 的）保留。
    os.environ.setdefault("XCLI_TODO_DIR", str(config.todo_dir))
    os.environ.setdefault("XCLI_SECRETS_DIR", str(config.secrets_path))

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