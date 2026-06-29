"""plugins/web.py — ``x web`` subcommand plugin.

Starts an HTTP server (stdlib-only) exposing ``x todo`` + ``x secret``
as a REST API + a static-file frontend (replaced by feature/web-frontend
branch).

Usage::

    x web                              # default 127.0.0.1:8421
    x web --port 9000                  # custom port
    x web --host 0.0.0.0               # expose to LAN (still needs token)
    x web --token my-secret-token      # custom token (default: random)

A token is generated at startup and printed to stdout. The user pastes
it into the browser's first-load prompt to authenticate.
"""

from __future__ import annotations

import argparse
import secrets
import sys
import time
import webbrowser
from typing import Sequence

from core.web import DEFAULT_HOST, DEFAULT_PORT
from core.web.auth import generate_token
from core.web.server import WebServer


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
        help="自定义认证 token（默认随机生成 32 字节 base64）",
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


def run(args: Sequence[str]) -> int:
    """Start the web server and block until Ctrl+C."""
    parser = argparse.ArgumentParser(prog="x web", description="x-cli Web UI (REST API + frontend)")
    register(parser)
    parsed = parser.parse_args(list(args))

    token = parsed.token or generate_token()

    try:
        server = WebServer(host=parsed.host, port=parsed.port, token=token)
        server.start()
    except OSError as exc:
        print(f"❌ 启动失败：{exc}", file=sys.stderr)
        print(f"提示：端口 {parsed.port} 可能被占用", file=sys.stderr)
        return 1

    url = server.base_url
    print(f"🌐 x web 服务已启动", file=sys.stderr)
    print(f"   地址: {url}", file=sys.stderr)
    print(f"   Token: {token}", file=sys.stderr)
    print(f"   停止: Ctrl+C", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"🔐 请在浏览器输入上面的 Token（首次访问会提示）", file=sys.stderr)

    if not parsed.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    try:
        # Block until Ctrl+C
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n👋 停止服务...", file=sys.stderr)
    finally:
        server.stop()

    return 0