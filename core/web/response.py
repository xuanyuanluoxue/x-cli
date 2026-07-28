"""core.web.response — HTTP response helpers shared by handlers + server.

Extracted to :mod:`core.web.response` to avoid circular imports between
:mod:`core.web.server` (which imports handlers) and :mod:`core.web.handlers`
(which need response helpers).
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    """Write a JSON response with the right headers and status code."""
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def error_response(
    handler: BaseHTTPRequestHandler, status: int, code: str, message: str, **extra: Any
) -> None:
    """Standard error envelope: ``{"error": ..., "code": ..., ...extra}``."""
    payload: dict[str, Any] = {"error": message, "code": code}
    payload.update(extra)
    json_response(handler, status, payload)


def read_json_body(
    handler: BaseHTTPRequestHandler,
) -> tuple[dict[str, Any] | None, str | None]:
    """Parse request body as JSON. Returns ``(body_dict, error_code)``.

    Error codes:
        ``"empty_body"`` — Content-Length is 0 or missing
        ``"invalid_json"`` — body is not a JSON object
    """
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length == 0:
        return None, "empty_body"
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, "invalid_json"
    if not isinstance(data, dict):
        return None, "invalid_json"
    return data, None