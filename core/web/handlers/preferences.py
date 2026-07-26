"""Restricted Web preference updates for ``PATCH /api/preferences``."""

from __future__ import annotations

from http import HTTPStatus

from core.config import ConfigError, set_web_secret_confirmation
from core.web.response import error_response, json_response, read_json_body


def handle_preferences(handler) -> None:
    """Persist the secret-confirmation switch and update the live server."""
    body, error = read_json_body(handler)
    if error is not None or body is None:
        error_response(
            handler,
            HTTPStatus.BAD_REQUEST,
            "validation_error",
            "JSON object body required",
        )
        return

    expected_keys = {"secret_confirmation_required"}
    if set(body) != expected_keys:
        error_response(
            handler,
            HTTPStatus.BAD_REQUEST,
            "validation_error",
            "only secret_confirmation_required is supported",
        )
        return

    required = body["secret_confirmation_required"]
    if not isinstance(required, bool):
        error_response(
            handler,
            HTTPStatus.BAD_REQUEST,
            "validation_error",
            "secret_confirmation_required must be a boolean",
        )
        return

    try:
        set_web_secret_confirmation(handler.server.config_path, required)
    except ConfigError:
        error_response(
            handler,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "config_error",
            "failed to save Web preference",
        )
        return

    handler.server.secret_confirmation_required = required
    json_response(
        handler,
        HTTPStatus.OK,
        {"preferences": {"secret_confirmation_required": required}},
    )
