"""plugins/web.py — ``x web`` subcommand plugin.

Starts an HTTP server (stdlib-only) exposing ``x todo`` + ``x secret``
as a REST API + a static-file frontend (replaced by feature/web-frontend
branch).

Usage::

    x web                              # default 127.0.0.1:8421
    x web --port 9000                  # custom port
    x web --host 0.0.0.0               # expose to LAN (use with care)
    x web --token my-secret-token      # explicitly enable auth

Token authentication is disabled by default. Set ``web_auth: true`` in
``config.yaml`` or pass ``--token`` to enable it.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Sequence

from core.paths import xcli_config_path
from core.web import DEFAULT_HOST, DEFAULT_PORT
from core.web.auth import generate_token
from core.web.server import WebServer


_WEB_AUTH_ENV = "XCLI_WEB_AUTH"
_WEB_SECRET_CONFIRMATION_ENV = "XCLI_WEB_SECRET_CONFIRMATION"
_CONFIG_PATH_ENV = "XCLI_CONFIG_PATH"


def _resolve_token(
    custom_token: str | None,
    *,
    config_auth_enabled: bool,
) -> str | None:
    """Return the effective token, or ``None`` for direct-access mode."""
    if custom_token is not None:
        return custom_token or generate_token()
    if config_auth_enabled:
        return generate_token()
    return None


def register(parser: argparse.ArgumentParser) -> None:
    """Register ``x web`` subcommand args."""
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"绑定 host（默认 {DEFAULT_HOST}；改 0.0.0.0 暴露给局域网）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"绑定端口（默认 {DEFAULT_PORT}）",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="自定义认证 token（传入即开启认证；否则由 web_auth 配置决定）",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="不自动打开浏览器",
    )
    parser.add_argument(
        "--auto-token-url",
        "-A",
        action="store_true",
        help=(
            "自动把 token 注入到浏览器 URL（?token=xxx），"
            "前端自动填 + 立即清 URL。"
            "⚠️ opt-in：默认关闭（防 URL 泄露到浏览器历史/同步）。"
            "需要 --browser（默认）才生效；--no-browser 模式下无效。"
        ),
    )


def _open_browser(url: str, token: str | None, auto_token_url: bool) -> None:
    """Open the browser with the right URL (with or without ?token=).

    v0.6.0 抽出来以便 unit test（plugins/web.py:run 阻塞 Ctrl+C 死循环，
    难直接测；抽成纯函数后用 mock webbrowser.open 直接测）。

    Args:
        url: server base URL (e.g. ``http://127.0.0.1:8421``)
        token: 当前会话 token；``None`` 表示无需认证
        auto_token_url: opt-in flag。True → URL 拼 ?token=xxx

    Side effects:
        - 调 ``webbrowser.open(open_url)``（失败静默）
        - 当 ``auto_token_url=True`` 时额外打印一行 ⚡ 提示
    """
    try:
        inject_token = auto_token_url and token is not None
        open_url = f"{url}?token={token}" if inject_token else url
        if inject_token:
            print(
                f"   ⚡ auto-token-url：URL 含 ?token=...（浏览器自动填后清 URL）",
                file=sys.stderr,
            )
        webbrowser.open(open_url)
    except Exception:  # noqa: BLE001
        # 静默：开浏览器失败不致命（用户可手动访问 URL）
        pass


def run(args: Sequence[str]) -> int:
    """Dispatch through a stable public plugin entry point."""
    return _run(args)


def _run(args: Sequence[str]) -> int:
    """Start the web server and block until Ctrl+C."""
    # v0.6.1: positional ``help`` alias (--help/-h 由 argparse 原生处理)
    if list(args) == ["help"]:
        parser = argparse.ArgumentParser(
            prog="x web", description="x-cli Web UI (REST API + frontend)"
        )
        register(parser)
        parser.print_help()
        return 0

    parser = argparse.ArgumentParser(prog="x web", description="x-cli Web UI (REST API + frontend)")
    register(parser)
    parsed = parser.parse_args(list(args))

    config_auth_enabled = os.environ.get(_WEB_AUTH_ENV, "0") == "1"
    secret_confirmation_required = (
        os.environ.get(_WEB_SECRET_CONFIRMATION_ENV, "1") != "0"
    )
    config_path = Path(os.environ.get(_CONFIG_PATH_ENV) or xcli_config_path())
    token = _resolve_token(
        parsed.token,
        config_auth_enabled=config_auth_enabled,
    )

    try:
        server = WebServer(
            host=parsed.host,
            port=parsed.port,
            token=token,
            config_path=config_path,
            secret_confirmation_required=secret_confirmation_required,
        )
        server.start()
    except OSError as exc:
        print(f"❌ 启动失败：{exc}", file=sys.stderr)
        print(f"提示：端口 {parsed.port} 可能被占用", file=sys.stderr)
        return 1

    url = server.base_url
    print(f"🌐 x web 服务已启动", file=sys.stderr)
    print(f"   地址: {url}", file=sys.stderr)
    if token is None:
        print("   认证: 关闭（浏览器可直接访问）", file=sys.stderr)
    else:
        print(f"   Token: {token}", file=sys.stderr)
    print(f"   停止: Ctrl+C", file=sys.stderr)
    print(f"", file=sys.stderr)
    if token is None:
        print("🌐 已关闭 Token 验证；任务和密钥可由本机浏览器直接访问", file=sys.stderr)
        if parsed.host not in {"127.0.0.1", "localhost", "::1"}:
            print(
                "⚠️  当前绑定地址不是本机回环；其他设备可能直接访问任务和密钥",
                file=sys.stderr,
            )
    else:
        print(f"🔐 请在浏览器输入上面的 Token（首次访问会提示）", file=sys.stderr)

    # opt-in：检测 --no-browser + --auto-token-url 冲突，给友好警告
    # （不动用户意图，只教育）
    if parsed.auto_token_url and token is None:
        print(
            "⚠️  --auto-token-url 在认证关闭时无效（无需 Token）",
            file=sys.stderr,
        )
    elif parsed.no_browser and parsed.auto_token_url:
        print(
            f"⚠️  --auto-token-url 在 --no-browser 模式下静默无效",
            file=sys.stderr,
        )
        print(
            f"   （不开浏览器 = URL 注入无意义；要生效请去掉 --no-browser）",
            file=sys.stderr,
        )

    if not parsed.no_browser:
        _open_browser(url, token, parsed.auto_token_url)

    try:
        # Block until Ctrl+C
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n👋 停止服务...", file=sys.stderr)
    finally:
        server.stop()

    return 0
