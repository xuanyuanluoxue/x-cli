"""core.web.handlers.secrets — secret CRUD REST handlers.

Routes handled here:
    GET    /api/secrets         — list (NO value)
    POST   /api/secrets         — create
    GET    /api/secrets/<name>  — get one (WITH value + stderr warning)
    PATCH  /api/secrets/<name>  — update
    DELETE /api/secrets/<name>  — delete

**Security**: ``GET /api/secrets`` NEVER returns ``value``. Only ``GET /api/secrets/<name>``
returns the value, AND it prints a warning to stderr (same as CLI ``x secret get``).
"""

from __future__ import annotations

import sys
from http import HTTPStatus

from core.web.response import error_response, json_response, read_json_body


# ============================================================
#  Secret <-> JSON converters
# ============================================================


def _secret_summary(entry) -> dict:
    """List-view: NO value, NO note. Safe for any consumer."""
    return {
        "name": entry.name,
        "category": entry.category,
        "updated_at": entry.updated_at,
    }


def _secret_full(entry) -> dict:
    """Detail-view: includes value + note. Sensitive — logs warning."""
    print(
        f"🔐 警告：密钥已通过 Web API 输出到客户端（name={entry.name}）",
        file=sys.stderr,
    )
    return {
        "name": entry.name,
        "category": entry.category,
        "value": entry.value,
        "note": entry.note or "",
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


# ============================================================
#  /api/secrets collection
# ============================================================


def handle_secrets_collection(handler, action: str) -> None:
    if action == "list":
        _list_secrets(handler)
    elif action == "create":
        _create_secret(handler)
    else:  # pragma: no cover
        error_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", f"unknown action {action}")


def _list_secrets(handler) -> None:
    store = handler.server.secrets
    entries = store.list()
    json_response(
        handler,
        HTTPStatus.OK,
        {
            "secrets": [_secret_summary(e) for e in entries],
            "count": len(entries),
        },
    )


def _create_secret(handler) -> None:
    body, err = read_json_body(handler)
    if err == "empty_body":
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "request body required")
        return
    if err == "invalid_json":
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "invalid JSON body")
        return
    assert body is not None

    name = (body.get("name") or "").strip()
    value = body.get("value") or ""
    if not name:
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "name is required")
        return
    if not value:
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "value is required")
        return

    category = body.get("category") or "default"
    note = body.get("note") or ""

    store = handler.server.secrets
    try:
        entry = store.set(name=name, value=value, category=category, note=note)
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" in msg:
            error_response(handler, HTTPStatus.CONFLICT, "duplicate", f"secret already exists: {name}", name=name)
            return
        error_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))
        return

    json_response(handler, HTTPStatus.CREATED, {"secret": _secret_full(entry)})


# ============================================================
#  /api/secrets/<name> item
# ============================================================


def handle_secret_item(handler, name: str, action: str) -> None:
    if action == "get":
        _get_secret(handler, name)
    elif action == "update":
        _update_secret(handler, name)
    elif action == "delete":
        _delete_secret(handler, name)
    else:  # pragma: no cover
        error_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", f"unknown action {action}")


def _get_secret(handler, name: str) -> None:
    store = handler.server.secrets
    entry = store.find(name)
    if entry is None:
        error_response(handler, HTTPStatus.NOT_FOUND, "not_found", f"secret not found: {name}", name=name)
        return
    json_response(handler, HTTPStatus.OK, {"secret": _secret_full(entry)})


def _update_secret(handler, name: str) -> None:
    body, err = read_json_body(handler)
    if err == "empty_body":
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "request body required")
        return
    if err == "invalid_json":
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "invalid JSON body")
        return
    assert body is not None
    if not body:
        error_response(handler, HTTPStatus.BAD_REQUEST, "validation_error", "at least one field required")
        return

    kwargs: dict = {}
    if "value" in body:
        kwargs["value"] = body["value"]
    if "category" in body:
        kwargs["category"] = body["category"]
    if "note" in body:
        kwargs["note"] = body["note"]

    store = handler.server.secrets
    try:
        entry = store.update(name, **kwargs)
    except LookupError as exc:
        error_response(handler, HTTPStatus.NOT_FOUND, "not_found", f"secret not found: {name}", name=name)
        return

    json_response(handler, HTTPStatus.OK, {"secret": _secret_full(entry)})


def _delete_secret(handler, name: str) -> None:
    store = handler.server.secrets
    try:
        store.rm(name)
    except LookupError as exc:
        error_response(handler, HTTPStatus.NOT_FOUND, "not_found", f"secret not found: {name}", name=name)
        return
    handler.send_response(HTTPStatus.NO_CONTENT)
    handler.send_header("Content-Length", "0")
    handler.end_headers()
