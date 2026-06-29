"""Tests for ``x web`` HTTP server + REST API.

对应 BDD：``docs/behaviors/web-api-behavior.md``

测试策略：
- 在临时端口（0 = OS 分配）启动 :class:`WebServer` 在后台线程
- 用 stdlib ``http.client`` 发请求
- 每个测试独立 fixture（端口 + token 重新生成）

覆盖 23 个 BDD 场景。
"""

from __future__ import annotations

import json
import socket
import argparse
import webbrowser
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from typing import Iterator

import pytest

from core.secrets import SecretStore
from core.storage import TaskStore
from core.web.auth import generate_token, is_valid_token
from core.web.server import WebServer


# ============================================================
#  Fixtures
# ============================================================


def _free_port() -> int:
    """Ask OS for a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[WebServer]:
    """Spin up a WebServer on a free port + isolated env. Auto-stops on teardown."""
    # Isolate storage to tmp_path
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path / "todo"))
    monkeypatch.setenv("XCLI_SECRETS_DIR", str(tmp_path / "secrets.json"))
    if hasattr(monkeypatch, "setenv"):  # Windows
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    # Use the same TaskStore / SecretStore instances the handler will use
    store = TaskStore()
    secrets_store = SecretStore(db_path=str(tmp_path / "secrets.json"))

    token = "test-token-abc123"
    port = _free_port()
    srv = WebServer(host="127.0.0.1", port=port, token=token, store=store, secrets_store=secrets_store)
    srv.start()
    # Wait for server to actually be listening (up to 2s)
    import time
    deadline = time.time() + 2.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.02)
    else:  # pragma: no cover
        raise RuntimeError(f"server didn't start within 2s on port {port}")
    srv.test_base_url = f"http://127.0.0.1:{port}"
    srv.test_token = token
    try:
        yield srv
    finally:
        srv.stop()


@contextmanager
def http_client(server: WebServer) -> Iterator[HTTPConnection]:
    """Yield an HTTPConnection to the test server."""
    conn = HTTPConnection("127.0.0.1", server.port, timeout=5)
    try:
        yield conn
    finally:
        conn.close()


def _request(
    server: WebServer,
    method: str,
    path: str,
    *,
    body: dict | None = None,
    token: str | None = "use-server-token",
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    """Send a request to the test server. Returns ``(status_code, json_body)``.

    ``token="use-server-token"`` (default) injects ``server.test_token``.
    Pass ``token=None`` to omit the header entirely.
    """
    headers = {}
    if token == "use-server-token":
        headers["X-Web-Token"] = server.test_token
    elif token is not None:
        headers["X-Web-Token"] = token
    if body is not None:
        body_bytes = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body_bytes))
    if extra_headers:
        headers.update(extra_headers)

    conn = HTTPConnection("127.0.0.1", server.port, timeout=5)
    try:
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        try:
            return resp.status, json.loads(data.decode("utf-8")) if data else {}
        except json.JSONDecodeError:
            return resp.status, {"raw": data.decode("utf-8", errors="replace")}
    finally:
        conn.close()


def _make_task_via_cli(server: WebServer, name: str, **kwargs) -> None:
    """Helper: create a task via the store directly (bypass HTTP for setup)."""
    from datetime import date

    from core.models import Priority, Task, TaskStatus
    from core.slug import unique_slug

    today = date.today().isoformat()
    existing_ids = {t.id for t in server.store.list_tasks(include_archived=True) if t.id}
    task_id = unique_slug(name, existing_ids)
    task = Task(
        id=task_id,
        name=name,
        status=TaskStatus.PENDING,
        priority=Priority(kwargs.get("priority", "medium")),
        created=today,
        updated=today,
        deadline=kwargs.get("deadline"),
        folder=f"任务/{name}",
        tags=kwargs.get("tags") or None,
    )
    server.store.add_task(task)


def _make_secret_via_store(server: WebServer, name: str, value: str, **kwargs) -> None:
    """Helper: create a secret via the store directly."""
    server.secrets.set(name=name, value=value, **kwargs)


# ============================================================
#  Auth / health (场景 2-5)
# ============================================================


def test_health_no_auth_required(server: WebServer):
    """GET /api/health works without token. 场景 2."""
    status, body = _request(server, "GET", "/api/health", token=None)
    assert status == 200
    assert body["status"] == "ok"
    assert "version" in body
    assert "todo" in body["subsystems"]
    assert "secret" in body["subsystems"]


def test_api_missing_token_returns_401(server: WebServer):
    """GET /api/tasks without X-Web-Token → 401. 场景 3."""
    status, body = _request(server, "GET", "/api/tasks", token=None)
    assert status == 401
    assert body["code"] == "missing_token"


def test_api_wrong_token_returns_401(server: WebServer):
    """Wrong X-Web-Token → 401. 场景 4."""
    status, body = _request(server, "GET", "/api/tasks", token="wrong-token")
    assert status == 401
    assert body["code"] == "invalid_token"


def test_api_correct_token_returns_200(server: WebServer):
    """Correct X-Web-Token → 200 with empty list. 场景 5."""
    status, body = _request(server, "GET", "/api/tasks")
    assert status == 200
    assert body["tasks"] == []
    assert body["count"] == 0


# ============================================================
#  Tasks (场景 6-15)
# ============================================================


def test_list_tasks_with_status_filter(server: WebServer):
    """GET /api/tasks?status=pending filters by status. 场景 6."""
    _make_task_via_cli(server, "kemu1", priority="high")
    _make_task_via_cli(server, "zizhushixi", priority="medium")
    # Mark one as in_progress via update
    server.store.update_task("zizhushixi", status="in_progress")

    status, body = _request(server, "GET", "/api/tasks?status=pending")
    assert status == 200
    assert body["count"] == 1
    assert body["tasks"][0]["id"] == "kemu1"


def test_get_single_task(server: WebServer):
    """GET /api/tasks/<id> returns one task. 场景 7."""
    _make_task_via_cli(server, "kemu1", priority="high")
    status, body = _request(server, "GET", "/api/tasks/kemu1")
    assert status == 200
    assert body["task"]["id"] == "kemu1"
    assert body["task"]["priority"] == "high"


def test_get_nonexistent_task_returns_404(server: WebServer):
    """GET /api/tasks/nonexistent → 404. 场景 8."""
    status, body = _request(server, "GET", "/api/tasks/nonexistent")
    assert status == 404
    assert body["code"] == "not_found"
    assert body["id"] == "nonexistent"


def test_create_task_success(server: WebServer):
    """POST /api/tasks creates a task. 场景 9."""
    status, body = _request(
        server, "POST", "/api/tasks",
        body={"name": "新任务", "priority": "high"},
    )
    assert status == 201
    assert body["task"]["name"] == "新任务"
    assert body["task"]["priority"] == "high"
    # Verify on disk
    task = server.store.get_task(body["task"]["id"], include_archived=True)
    assert task is not None


def test_create_task_missing_name_returns_400(server: WebServer):
    """POST /api/tasks without name → 400. 场景 10."""
    status, body = _request(
        server, "POST", "/api/tasks",
        body={"priority": "high"},
    )
    assert status == 400
    assert body["code"] == "validation_error"


def test_create_task_duplicate_returns_409(server: WebServer):
    """POST /api/tasks with existing name → 409. 场景 11."""
    _make_task_via_cli(server, "kemu1")
    status, body = _request(
        server, "POST", "/api/tasks",
        body={"name": "kemu1"},
    )
    assert status == 409
    assert body["code"] == "duplicate"
    assert body["name"] == "kemu1"


def test_update_task_changes_status(server: WebServer):
    """PATCH /api/tasks/<id> updates fields. 场景 12."""
    _make_task_via_cli(server, "kemu1")
    status, body = _request(
        server, "PATCH", "/api/tasks/kemu1",
        body={"status": "in_progress"},
    )
    assert status == 200
    assert body["task"]["status"] == "in_progress"


def test_archive_task(server: WebServer):
    """POST /api/tasks/<id>/archive archives. 场景 13."""
    _make_task_via_cli(server, "kemu1")
    status, body = _request(
        server, "POST", "/api/tasks/kemu1/archive",
        body={"reason": "done"},
    )
    assert status == 200
    assert body["task"]["status"] == "archived"
    assert body["task"]["reason"] == "done"


def test_archive_already_archived_returns_409(server: WebServer):
    """POST archive on already-archived task → 409. 场景 14."""
    _make_task_via_cli(server, "kemu1")
    _request(server, "POST", "/api/tasks/kemu1/archive", body={"reason": "done"})
    status, body = _request(server, "POST", "/api/tasks/kemu1/archive")
    assert status == 409
    assert body["code"] == "duplicate"


def test_stats_returns_summary(server: WebServer):
    """GET /api/tasks/stats returns counts. 场景 15."""
    _make_task_via_cli(server, "kemu1", priority="high")
    _make_task_via_cli(server, "zizhushixi", priority="medium")
    status, body = _request(server, "GET", "/api/tasks/stats")
    assert status == 200
    assert body["total"] == 2
    assert "by_status" in body
    assert "by_priority" in body


# ============================================================
#  Secrets (场景 16-19)
# ============================================================


def test_list_secrets_no_value_field(server: WebServer):
    """GET /api/secrets list NEVER returns value. 场景 16."""
    _make_secret_via_store(server, "minimax", "sk-test", category="API")
    _make_secret_via_store(server, "openai", "sk-openai")
    status, body = _request(server, "GET", "/api/secrets")
    assert status == 200
    assert body["count"] == 2
    for s in body["secrets"]:
        assert "value" not in s
        assert "name" in s
        assert "category" in s


def test_get_secret_includes_value_and_warns(server: WebServer, capsys):
    """GET /api/secrets/<name> returns value + stderr warning. 场景 17."""
    _make_secret_via_store(server, "minimax", "sk-test", category="API")
    status, body = _request(server, "GET", "/api/secrets/minimax")
    assert status == 200
    assert body["secret"]["value"] == "sk-test"
    assert body["secret"]["category"] == "API"
    captured = capsys.readouterr()
    assert "密钥已通过 Web API 输出" in captured.err


def test_create_secret(server: WebServer):
    """POST /api/secrets creates a secret. 场景 18."""
    status, body = _request(
        server, "POST", "/api/secrets",
        body={"name": "minimax", "value": "sk-test", "category": "API"},
    )
    assert status == 201
    assert body["secret"]["name"] == "minimax"
    assert body["secret"]["value"] == "sk-test"
    # Verify on disk
    entry = server.secrets.get("minimax")
    assert entry is not None
    assert entry.value == "sk-test"


def test_delete_secret_returns_204(server: WebServer):
    """DELETE /api/secrets/<name> → 204. 场景 19."""
    _make_secret_via_store(server, "minimax", "sk-test")
    status, body = _request(server, "DELETE", "/api/secrets/minimax")
    assert status == 204
    assert server.secrets.get("minimax") is None


# ============================================================
#  Security / edge cases (场景 20-22)
# ============================================================


def test_path_traversal_blocked(server: WebServer):
    """GET /../etc/passwd → 404 (no file content leaked). 场景 20."""
    status, body = _request(server, "GET", "/../etc/passwd", token=None)
    assert status in (403, 404)
    # Must NOT contain "root:" or passwd-like content
    body_text = json.dumps(body)
    assert "root:" not in body_text
    assert "/bin/" not in body_text


def test_method_not_allowed_returns_405(server: WebServer):
    """DELETE /api/tasks → 405. 场景 21."""
    status, body = _request(server, "DELETE", "/api/tasks")
    assert status == 405
    assert body["code"] == "method_not_allowed"


def test_invalid_json_body_returns_400(server: WebServer):
    """POST /api/tasks with non-JSON body → 400. 场景 22."""
    # Send raw non-JSON via extra headers + body bytes
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    try:
        conn.request(
            "POST", "/api/tasks",
            body=b"this is not json",
            headers={"X-Web-Token": server.test_token, "Content-Type": "text/plain"},
        )
        resp = conn.getresponse()
        data = resp.read()
        assert resp.status == 400
        body = json.loads(data.decode("utf-8"))
        assert body["code"] in ("validation_error", "invalid_json")
    finally:
        conn.close()


# ============================================================
#  Auth unit tests (no server needed)
# ============================================================


def test_generate_token_length():
    """generate_token() returns ~43 chars for 32 bytes."""
    t = generate_token()
    assert isinstance(t, str)
    assert len(t) >= 40  # base64 of 32 bytes is 44 chars without padding


def test_generate_token_unique():
    """Two calls return different tokens."""
    assert generate_token() != generate_token()


def test_is_valid_token_correct():
    """Correct token returns True."""
    assert is_valid_token("abc", "abc") is True


def test_is_valid_token_wrong():
    """Wrong token returns False."""
    assert is_valid_token("wrong", "abc") is False


def test_is_valid_token_none():
    """None provided returns False (no exception)."""
    assert is_valid_token(None, "abc") is False


# ============================================================
#  x web --auto-token-url  (v0.6.0+ opt-in UX improvement)
# ============================================================
#
# 设计（docs/superpowers/specs/2026-06-28-web-auto-token-url-design.md）：
# - 默认 False（不传 flag = 现状，手动复制粘贴 token）
# - 加 --auto-token-url / -A → webbrowser.open(url + "?token=xxx")
# - 前端（login.js）解析 ?token= → setToken → history.replaceState 清 URL
# - 测试 register 暴露了 flag + 默认 False 行为

from plugins import web as _web_plugin  # noqa: E402


def _build_web_parser() -> argparse.ArgumentParser:
    """Build a fresh ``x web`` parser (don't reuse module-level state)."""
    parser = argparse.ArgumentParser(prog="x web")
    _web_plugin.register(parser)
    return parser


def test_auto_token_url_flag_in_register() -> None:
    """``register()`` must expose --auto-token-url / -A as a store_true flag."""
    parser = _build_web_parser()
    # 用 namespace 反向检查（-A / --auto-token-url 都应映射到 auto_token_url）
    ns = parser.parse_args([])
    assert hasattr(ns, "auto_token_url")
    assert ns.auto_token_url is False, "default must be False (opt-in)"

    ns_on = parser.parse_args(["--auto-token-url"])
    assert ns_on.auto_token_url is True

    ns_short = parser.parse_args(["-A"])
    assert ns_short.auto_token_url is True


def test_auto_token_url_help_text_mentions_optin() -> None:
    """Help 文本必须明确 'opt-in' / '默认关闭'，避免用户误启用。"""
    parser = _build_web_parser()
    # 通过 parser._actions 找 --auto-token-url 的 help 字符串
    for action in parser._actions:
        if "--auto-token-url" in (action.option_strings or []):
            assert "opt-in" in action.help
            assert "默认" in action.help
            return
    pytest.fail("--auto-token-url flag not found in parser actions")


def test_auto_token_url_default_is_false() -> None:
    """不传 flag 时 auto_token_url 必须为 False（防止默认开启泄露 URL）。"""
    parser = _build_web_parser()
    ns = parser.parse_args([])
    assert ns.auto_token_url is False
    # 同时确认 no_browser 也是默认 False（与现有行为一致）
    assert ns.no_browser is False


# --- _open_browser helper (v0.6.0 抽出来测真实行为) -----------------------


def test_open_browser_default_url() -> None:
    """_open_browser 默认 (auto_token_url=False) → webbrowser.open(url 原样)。"""
    captured: list[str] = []
    _original_open = webbrowser.open
    webbrowser.open = lambda u: captured.append(u)  # type: ignore[assignment]
    try:
        _web_plugin._open_browser("http://127.0.0.1:8421", "abc", False)
    finally:
        webbrowser.open = _original_open  # type: ignore[assignment]
    assert captured == ["http://127.0.0.1:8421"], (
        f"expected plain URL, got {captured!r}"
    )


def test_open_browser_with_auto_token_url() -> None:
    """_open_browser + auto_token_url=True → webbrowser.open(url?token=xxx)。"""
    captured: list[str] = []
    _original_open = webbrowser.open
    webbrowser.open = lambda u: captured.append(u)  # type: ignore[assignment]
    try:
        _web_plugin._open_browser("http://127.0.0.1:8421", "tok-XYZ", True)
    finally:
        webbrowser.open = _original_open  # type: ignore[assignment]
    assert captured == ["http://127.0.0.1:8421?token=tok-XYZ"], (
        f"expected URL with ?token=, got {captured!r}"
    )


def test_open_browser_swallows_exceptions() -> None:
    """_open_browser 失败时静默（不致命；用户可手动访问 URL）。"""
    _original_open = webbrowser.open

    def _raise(_url: str) -> None:
        raise OSError("no default browser")

    webbrowser.open = _raise  # type: ignore[assignment]
    try:
        # 不应抛异常
        _web_plugin._open_browser("http://127.0.0.1:8421", "tok", True)
    finally:
        webbrowser.open = _original_open  # type: ignore[assignment]