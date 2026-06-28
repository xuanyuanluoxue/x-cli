"""core.web.server — HTTP server glue + WebHandler request dispatcher.

Wraps :class:`http.server.HTTPServer` with:

* Token-based authentication for ``/api/*`` endpoints
* Static file serving from ``core/web/static/`` (for ``/`` and ``/<file>``)
* Path-traversal protection on static files
* JSON request parsing + JSON response formatting

The :class:`WebServer` class is the high-level facade — tests instantiate
it directly with a fixed port and start/stop it in a thread.
"""

from __future__ import annotations

import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from core.web.auth import is_valid_token
from core.web.handlers.health import handle_health
from core.web.handlers.secrets import handle_secrets_collection, handle_secret_item
from core.web.handlers.tasks import (
    handle_task_archive,
    handle_task_item,
    handle_tasks_collection,
    handle_tasks_stats,
)
from core.web.response import error_response, json_response, read_json_body


# Static dir is sibling to this file: core/web/static/
_STATIC_DIR = Path(__file__).parent / "static"


# ============================================================
#  Static file serving
# ============================================================


def _serve_static(handler: BaseHTTPRequestHandler, rel_path: str) -> bool:
    """Try to serve a static file from ``core/web/static/``.

    Returns True if the file was found and served; False if not found
    (caller should then return 404).

    Path-traversal protection: any resolved path that escapes ``STATIC_DIR``
    is rejected as 404.
    """
    # Strip leading slash
    rel_path = rel_path.lstrip("/")
    if not rel_path:
        rel_path = "index.html"

    # Reject path traversal attempts
    if ".." in Path(rel_path).parts:
        error_response(handler, HTTPStatus.NOT_FOUND, "not_found", "static file not found")
        return True

    full = (_STATIC_DIR / rel_path).resolve()
    try:
        full.relative_to(_STATIC_DIR.resolve())
    except ValueError:
        # Escaped STATIC_DIR — reject
        error_response(handler, HTTPStatus.NOT_FOUND, "not_found", "static file not found")
        return True

    if not full.is_file():
        return False

    # Serve the file
    content = full.read_bytes()
    handler.send_response(HTTPStatus.OK)
    # Basic content-type guess
    if full.suffix == ".html":
        ctype = "text/html; charset=utf-8"
    elif full.suffix == ".css":
        ctype = "text/css; charset=utf-8"
    elif full.suffix == ".js":
        ctype = "application/javascript; charset=utf-8"
    elif full.suffix == ".json":
        ctype = "application/json; charset=utf-8"
    elif full.suffix == ".svg":
        ctype = "image/svg+xml"
    else:
        ctype = "application/octet-stream"
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(content)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(content)
    return True


# ============================================================
#  WebHandler — request dispatcher
# ============================================================


class WebHandler(BaseHTTPRequestHandler):
    """Single-handler that routes ``/api/*`` and ``/`` requests.

    Configuration is read from class-level attributes (``server.token``,
    ``server.store``, ``server.secrets``). The :class:`WebServer` sets
    these before serving.
    """

    # Suppress default per-request log noise; we use stderr writes ourselves.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    # ---- Routing ----

    def do_GET(self) -> None:  # noqa: N802 — http.server convention
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        path = self.path.split("?", 1)[0]  # strip query string

        # Auth (except /api/health and static)
        if path.startswith("/api/") and path != "/api/health":
            token = self.headers.get("X-Web-Token")
            if token is None:
                error_response(self, HTTPStatus.UNAUTHORIZED, "missing_token", "X-Web-Token header required")
                return
            if not is_valid_token(token, self.server.token):  # type: ignore[attr-defined]
                error_response(self, HTTPStatus.UNAUTHORIZED, "invalid_token", "invalid token")
                return

        # API routes
        if path == "/api/health" and method == "GET":
            handle_health(self)
            return
        if path == "/api/tasks":
            if method == "GET":
                handle_tasks_collection(self, "list")
            elif method == "POST":
                handle_tasks_collection(self, "create")
            else:
                error_response(self, HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", f"method {method} not allowed on {path}")
            return
        if path == "/api/tasks/stats" and method == "GET":
            handle_tasks_stats(self)
            return
        if path.startswith("/api/tasks/"):
            tail = path[len("/api/tasks/"):]
            if tail.endswith("/archive"):
                task_id = tail[:-len("/archive")]
                if method == "POST":
                    handle_task_archive(self, task_id)
                else:
                    error_response(self, HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", f"method {method} not allowed")
                return
            # Single task
            if method == "GET":
                handle_task_item(self, tail, "get")
            elif method == "PATCH":
                handle_task_item(self, tail, "update")
            else:
                error_response(self, HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", f"method {method} not allowed on {path}")
            return
        if path == "/api/secrets":
            if method == "GET":
                handle_secrets_collection(self, "list")
            elif method == "POST":
                handle_secrets_collection(self, "create")
            else:
                error_response(self, HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", f"method {method} not allowed on {path}")
            return
        if path.startswith("/api/secrets/"):
            name = path[len("/api/secrets/"):]
            if method == "GET":
                handle_secret_item(self, name, "get")
            elif method == "PATCH":
                handle_secret_item(self, name, "update")
            elif method == "DELETE":
                handle_secret_item(self, name, "delete")
            else:
                error_response(self, HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", f"method {method} not allowed on {path}")
            return

        # Static files (no auth)
        if path == "/" or not path.startswith("/api/"):
            if _serve_static(self, path):
                return
            error_response(self, HTTPStatus.NOT_FOUND, "not_found", f"no route for {path}")
            return

        error_response(self, HTTPStatus.NOT_FOUND, "not_found", f"no route for {path}")


# ============================================================
#  WebServer — facade for starting/stopping the HTTP server
# ============================================================


class _Server(ThreadingHTTPServer):
    """ThreadingHTTPServer with extra attributes used by WebHandler."""

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_cls: type[BaseHTTPRequestHandler],
        token: str,
        store: Any,  # TaskStore — avoid circular import
        secrets_store: Any,  # SecretStore
    ) -> None:
        super().__init__(server_address, handler_cls)
        self.token = token
        self.store = store
        self.secrets = secrets_store


class WebServer:
    """High-level facade for the x web HTTP server.

    Usage::

        token = generate_token()
        server = WebServer(host="127.0.0.1", port=8421, token=token)
        server.start()
        # ... server is running in background thread ...
        server.stop()

    The server is thread-safe (uses ``ThreadingHTTPServer``). Multiple
    clients can hit it concurrently.
    """

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        store: Any | None = None,
        secrets_store: Any | None = None,
    ) -> None:
        from core.secrets import SecretStore  # lazy import
        from core.storage import TaskStore  # lazy import

        self.host = host
        self.port = port
        self.token = token
        self.store = store if store is not None else TaskStore()
        self.secrets = secrets_store if secrets_store is not None else SecretStore()
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        """Start the server in a background thread. Non-blocking."""
        self._server = _Server(
            (self.host, self.port),
            WebHandler,
            token=self.token,
            store=self.store,
            secrets_store=self.secrets,
        )

        def _serve_with_logging() -> None:
            import traceback
            try:
                self._server.serve_forever()
            except Exception:  # noqa: BLE001
                traceback.print_exc()

        self._thread = threading.Thread(
            target=_serve_with_logging,
            name="x-web-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the server and wait for the thread to exit."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
