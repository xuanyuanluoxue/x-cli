"""core.web — HTTP server + REST API for x web subcommand.

Exposes :class:`core.storage.TaskStore` and :class:`core.secrets.SecretStore`
as JSON over HTTP. Stdlib-only (no Flask/FastAPI dependency).

Module map:

    core.web
    ├── auth          — token generation + constant-time validation
    ├── server        — ``http.server`` glue + :class:`WebHandler`
    ├── handlers/     — REST endpoint handlers (one file per subsystem)
    │   ├── health
    │   ├── tasks
    │   └── secrets
    └── static/       — frontend assets (placeholder; replaced by feature/web-frontend)

The :mod:`plugins.web` module wires :class:`core.web.server.WebServer`
into the ``x web`` CLI subcommand.
"""

from __future__ import annotations

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8421  # "x-cli web" keyboard mnemonic
STATIC_DIR = "static"