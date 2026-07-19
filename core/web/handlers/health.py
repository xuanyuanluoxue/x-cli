"""core.web.handlers.health — ``GET /api/health`` (no auth)."""

from __future__ import annotations

from http import HTTPStatus

from core.version import __version__
from core.web.response import json_response


def handle_health(handler) -> None:
    """Return service status + version + subsystems list."""
    json_response(
        handler,
        HTTPStatus.OK,
        {
            "status": "ok",
            "version": __version__,
            "subsystems": ["todo", "secret"],
            "auth_required": handler.server.token is not None,
        },
    )
