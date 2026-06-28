"""core.web.handlers — REST endpoint handlers.

Each module exports one or more ``handle_*`` functions with the signature
``(handler: BaseHTTPRequestHandler, ...) -> None``. They write the response
directly via :func:`core.web.server._json_response` / :func:`_error`.

Handlers should NOT raise on expected errors — they catch domain exceptions
and translate to HTTP errors.
"""

from __future__ import annotations