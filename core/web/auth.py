"""core.web.auth — token generation + validation.

Used by :mod:`core.web.server` to gate all ``/api/*`` endpoints behind
a startup-generated token. Constant-time comparison (hmac.compare_digest)
to prevent timing attacks on the token.
"""

from __future__ import annotations

import hmac
import secrets as _stdlib_secrets


def generate_token(nbytes: int = 32) -> str:
    """Generate a URL-safe random token.

    Default 32 bytes → ~43 character base64 string. Cryptographically
    secure (``secrets.token_urlsafe`` uses ``os.urandom`` under the hood).
    """
    return _stdlib_secrets.token_urlsafe(nbytes)


def is_valid_token(provided: str | None, expected: str) -> bool:
    """Constant-time string comparison.

    Returns ``False`` if ``provided`` is None. Never raises.
    """
    if provided is None:
        return False
    return hmac.compare_digest(provided, expected)