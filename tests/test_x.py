"""x 主入口测试（Phase 1 骨架）"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

import pytest

from x import __version__, build_parser, main


# ============================================================
#  x --version
# ============================================================

def test_version_flag_prints_version_and_exits_zero():
    """对应场景：x --version 显示版本号，退出码 0"""
    out = io.StringIO()
    with redirect_stdout(out):
        exit_code = main(["--version"])
    assert exit_code == 0
    assert out.getvalue().strip() == f"x {__version__}"


def test_short_version_flag_works():
    """对应场景：x -v（短选项）等价于 --version"""
    out = io.StringIO()
    with redirect_stdout(out):
        exit_code = main(["-v"])
    assert exit_code == 0
    assert __version__ in out.getvalue()


# ============================================================
#  x 无参数 / --help（argparse 触发 SystemExit(0)）
# ============================================================

def test_no_args_shows_help_and_exits_zero():
    """对应场景：x（无参数）显示帮助，退出码 0"""
    out = io.StringIO()
    with redirect_stdout(out):
        exit_code = main([])
    assert exit_code == 0
    output = out.getvalue()
    assert "x" in output
    assert "SUBCOMMAND" in output
    assert "todo" in output  # 帮助里列出已注册的子命令


def test_help_flag_exits_zero_and_prints_help(capsys):
    """对应场景：x --help 显示帮助，退出码 0（argparse 会触发 SystemExit）"""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "SUBCOMMAND" in captured.out
    assert "todo" in captured.out


# ============================================================
#  未知子命令
# ============================================================

def test_unknown_subcommand_errors_with_exit_code_1():
    """对应场景：x unknown → 错误提示 + 退出码 1"""
    err = io.StringIO()
    with redirect_stderr(err):
        exit_code = main(["unknown"])
    assert exit_code == 1
    assert "未知子命令" in err.getvalue()
    assert "unknown" in err.getvalue()


# ============================================================
#  x todo 子命令（Phase 1 占位）
# ============================================================

def test_todo_no_action_shows_help_and_exits_zero():
    """对应场景：x todo（无子动作）显示 x todo 帮助"""
    out = io.StringIO()
    with redirect_stdout(out):
        exit_code = main(["todo"])
    assert exit_code == 0
    output = out.getvalue()
    for action in ("list", "add", "update", "archive", "stats"):
        assert action in output


def test_todo_help_flag_shows_main_help(capsys):
    """对应场景：x todo --help 由主入口 argparse 拦截，显示 x 主入口帮助

    查看 x todo 子动作帮助：用 `x todo`（无参数）。这是 argparse 标准行为。
    """
    with pytest.raises(SystemExit) as exc_info:
        main(["todo", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    # argparse 主入口帮助里会提到 todo
    assert "todo" in captured.out


@pytest.mark.parametrize("action", [])
def test_todo_action_not_yet_implemented(action):
    """对应场景：x todo <action> 全部占位（Phase 1 未实现）

    所有 todo 子命令均已实现并覆盖在独立测试文件：
    - ``add``    → ``tests/test_todo_add.py``
    - ``list``   → ``tests/test_todo_list.py``
    - ``stats``  → ``tests/test_todo_stats.py``
    - ``update`` → ``tests/test_todo_update.py``
    - ``archive`` → ``tests/test_todo_archive.py``

    本测试保留 parametrize 框架，但当前没有未实现的子命令；如果以后
    新增了占位子命令，往参数列表里加即可。
    """
    err = io.StringIO()
    with redirect_stderr(err):
        exit_code = main(["todo", action])
    assert exit_code == 1
    assert "🚧" in err.getvalue()
    assert action in err.getvalue()


# ============================================================
#  build_parser 单元测试
# ============================================================

def test_build_parser_does_not_crash():
    parser = build_parser()
    assert parser.prog == "x"
    arg_dests = {a.dest for a in parser._actions}
    assert "version" in arg_dests
    assert "subcommand" in arg_dests


# ============================================================
#  argv 透传：子命令的 argparse 自己处理剩余参数
# ============================================================
# 注：原 ``test_unknown_flag_after_subcommand_is_argparse_error`` 测试
# ``x todo list --status pending`` 在占位阶段触发 argparse 的 SystemExit(2)；
# 但 ``list`` 已被 action-list task 实现并接受 ``--status``，该用例不再适用。
# 真正的未知-flag 用法错误测试由各 action 的子命令测试覆盖（见
# ``tests/test_todo_*.py``）。