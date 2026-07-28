"""x - Personal CLI toolset for task tracking and credential management.

A small, focused CLI built around five subsystems:
  * x todo  - personal task tracking (YAML-frontmatter folders)
  * x secret - local credential store (single JSON file, file mode 600)
  * x diary - local daily Markdown notes
  * x note - topic-oriented Markdown notes
  * x web - local authenticated web UI

Entry point only. Subcommand handlers live in :mod:`plugins.todo` and
:mod:`plugins.secret`. See README.md for usage and COMMANDS.md for the
canonical command list.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from core.config import AppConfig, ConfigError
from core.dispatch import SUBCOMMAND_MODULES, load_subcommand_handler
from core.logging import get_logger, setup_logging
from core.version import __version__


# ============================================================
#  Main entry point
# ============================================================


def _configure_utf8_standard_streams() -> None:
    """Prefer UTF-8 for localized CLI output when the host allows it.

    English Windows runners can expose redirected text streams as cp1252,
    including inside a PyInstaller executable.  Reconfigure before argparse
    prints help, while leaving StringIO and host-managed streams untouched.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, TypeError, ValueError):
            continue


def build_parser() -> argparse.ArgumentParser:
    """构造主解析器：--version / --config / --log-level / --config-init / <subcommand> [args...]

    v0.6.1: ``add_help=False`` **不**手动注册 ``-h/--help`` flag — 这样 argparse
    不会消费 ``--help``，让它落到 ``remaining`` 转给子命令 handler（每个 plugin
    自带 ArgumentParser，原生处理 ``--help``）。顶层 help 由 ``main()`` 在没有
    subcommand 时显式打印（看 ``argv`` 里有没有 ``--help`` / ``-h``）。
    """
    parser = argparse.ArgumentParser(
        prog="x",
        description="Xavier 个人工具集的统一 CLI 入口",
        add_help=False,
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
        help=f"子命令（{', '.join(SUBCOMMAND_MODULES)}）",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """主入口：解析 → 加载配置 + 日志 → 分发到子命令 handler"""
    _configure_utf8_standard_streams()
    argv = list(argv) if argv is not None else None
    parser = build_parser()
    parsed, remaining = parser.parse_known_args(argv)

    # v0.6.1: 顶层 help 只在 *没有* subcommand 时打印；有 subcommand 时
    # ``--help`` / ``-h`` 应原样传给子命令 handler（plugin 自己的 argparse
    # 打印对应 help）。``x help`` 是 ``x --help`` 的位置别名（git/npm 习惯）。
    if not parsed.subcommand and ("--help" in (argv or []) or "-h" in (argv or [])):
        parser.print_help()
        return 0
    if parsed.subcommand == "help":
        parser.print_help()
        return 0

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
            print(
                f"❌ 配置已存在：{config_path}（为避免覆盖，请先备份后移走旧文件）",
                file=sys.stderr,
            )
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
        "effective config: todo_dir=%s, log_level=%s, web_auth=%s, "
        "web_secret_confirmation=%s",
        config.todo_dir,
        config.log_level,
        config.web_auth,
        config.web_secret_confirmation,
    )

    # 把 config 派生的路径灌进环境变量，storage 层继续用 XCLI_TODO_DIR /
    # XCLI_SECRETS_DIR 读。setdefault —— 已经 set 的（用户显式 export 的）保留。
    os.environ.setdefault("XCLI_TODO_DIR", str(config.todo_dir))
    os.environ.setdefault("XCLI_SECRETS_DIR", str(config.secrets_path))
    # Web 插件保持稳定的 ``run(args)`` 契约；用进程内环境变量传递已经由
    # 顶层解析完成的配置（包括 ``--config`` 指定的非默认文件）。
    os.environ["XCLI_WEB_AUTH"] = "1" if config.web_auth else "0"
    os.environ["XCLI_WEB_SECRET_CONFIRMATION"] = (
        "1" if config.web_secret_confirmation else "0"
    )
    if parsed.config:
        effective_config_path = Path(parsed.config).resolve()
    elif os.environ.get("XCLI_CONFIG"):
        effective_config_path = Path(os.environ["XCLI_CONFIG"]).resolve()
    else:
        from core.paths import xcli_config_path

        effective_config_path = xcli_config_path().resolve()
    os.environ["XCLI_CONFIG_PATH"] = str(effective_config_path)

    if not parsed.subcommand:
        parser.print_help()
        return 0

    handler = load_subcommand_handler(parsed.subcommand)
    if handler is None:
        print(f"❌ 错误：未知子命令：{parsed.subcommand}", file=sys.stderr)
        print(f"提示：支持 {', '.join(SUBCOMMAND_MODULES)}", file=sys.stderr)
        return 1

    return handler(remaining)


if __name__ == "__main__":
    sys.exit(main())
