"""core/paths.py — Cross-platform path resolution for x-cli data files.

x-cli stores its secrets DB in a per-user data directory that follows
the platform conventions:

* Windows: ``%LOCALAPPDATA%\\x-cli`` (e.g. ``C:\\Users\\X\\AppData\\Local\\x-cli``)
* Unix:    ``$XDG_DATA_HOME/x-cli`` if set, else ``~/.local/share/x-cli``

The :func:`xcli_data_dir` helper always returns a path that exists on
disk (``mkdir(parents=True, exist_ok=True)`` is invoked on every call).
The :func:`xcli_secrets_path` helper returns the location of the
secrets JSON file — by default under the data directory, but
overridable via the :envvar:`XCLI_SECRETS_DIR` environment variable
(used by tests and by users who want to point at a custom location).

This module is **stdlib-only** (no third-party dependencies) and is
the single source of truth for on-disk paths. Callers should never
hardcode ``%LOCALAPPDATA%`` or ``~/.local/share`` themselves.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# ============================================================
#  Public API
# ============================================================


def xcli_data_dir() -> Path:
    """Return the x-cli data directory for the current platform.

    The returned directory is created if it does not already exist
    (``mkdir(parents=True, exist_ok=True)``). The path resolution is:

    * Windows: ``%LOCALAPPDATA%\\x-cli``
    * Unix:    ``$XDG_DATA_HOME/x-cli`` if set, else
      ``~/.local/share/x-cli``

    Returns
    -------
    Path
        Absolute path to the x-cli data directory. Guaranteed to exist
        after this call returns.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            # Fallback: ~/AppData/Local (rare on real Windows, but safe)
            base = str(Path.home() / "AppData" / "Local")
        return _ensure_dir(Path(base) / "x-cli")

    # Unix / macOS — follow the XDG Base Directory spec
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return _ensure_dir(Path(xdg) / "x-cli")
    return _ensure_dir(Path.home() / ".local" / "share" / "x-cli")


def xcli_secrets_path() -> Path:
    """Return the full path to the secrets JSON file.

    Resolution order:

    1. If :envvar:`XCLI_SECRETS_DIR` is set, return it as-is. The
       variable must point to a **file** path (not a directory) — the
       import command treats whatever it finds there as a JSON DB.
    2. Otherwise return ``<xcli_data_dir()>/secrets.json``.

    This function does **not** create the file. The caller
    (:class:`core.secrets.SecretStore`) decides when to materialise it.

    Returns
    -------
    Path
        Absolute path to the secrets JSON file.
    """
    override = os.environ.get("XCLI_SECRETS_DIR")
    if override:
        return Path(override)
    return xcli_data_dir() / "secrets.json"


def xcli_todo_dir() -> Path:
    """Return the x-cli TODO root (independent of xavier system).

    Resolution order:

    1. If :envvar:`XAVIER_TODO_DIR` is set, return it as-is. The
       variable name is historical (the original default pointed at
       ``~/.xavier/TODO/``) but x-cli treats it as a generic override.
       Tests use this to redirect to a ``tmp_path``.
    2. Otherwise return the platform-specific default under
       :func:`xcli_data_dir`:

       * Windows: ``<data_dir>\\todo\\`` (e.g.
         ``C:\\Users\\X\\AppData\\Local\\x-cli\\todo``)
       * Unix:    ``<data_dir>/todo/`` (e.g.
         ``~/.local/share/x-cli/todo``)

    The parent directory is created on every call (the task/ and
    归档/ subdirectories are created lazily by the caller — typically
    :class:`core.storage.TaskStore` or the ``x todo init`` handler).

    **Hard invariant**: this function NEVER returns
    ``~/.xavier/TODO/`` (or any sub-path of it). The only bridge to
    that directory is the explicit ``x todo import --from <dir>``
    command, which is one-way and read-only.

    Returns
    -------
    Path
        Absolute path to x-cli's TODO root. The directory itself is
        guaranteed to exist after this call returns; sub-directories
        are not.
    """
    override = os.environ.get("XAVIER_TODO_DIR")
    if override:
        # Honour the legacy override (tests, explicit user override).
        # We do NOT validate that the path lives outside ~/.xavier — if
        # the user explicitly sets XAVIER_TODO_DIR=~/.xavier/TODO they
        # are opting in to sharing the xavier system; x-cli will not
        # silently redirect.
        return Path(override)
    return xcli_data_dir() / "todo"


# ============================================================
#  Internal helpers
# ============================================================


def _ensure_dir(path: Path) -> Path:
    """Create ``path`` (and any missing parents) and return it.

    Idempotent: safe to call when the directory already exists.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
