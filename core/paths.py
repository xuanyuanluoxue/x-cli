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

# Legacy alias for XCLI_TODO_DIR — used by older test fixtures and by
# users who exported this before v0.5. We read it as a fallback so
# existing setups keep working, but emit a one-time deprecation
# warning to stderr pointing at the new name. The XAVIER_ prefix
# refers to a legacy system name and will be removed in a future
# release.
_LEGACY_TODO_DIR_ENV = "XAVIER_TODO_DIR"
_TODO_DIR_ENV = "XCLI_TODO_DIR"
_LEGACY_TODO_DIR_WARNED = False


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


def xcli_config_path() -> Path:
    """Return the path to the x-cli YAML config file.

    The default lives under :func:`xcli_data_dir` so it follows the
    platform conventions (``%LOCALAPPDATA%\\x-cli\\config.yaml`` on
    Windows, ``$XDG_DATA_HOME/x-cli/config.yaml`` on Unix). The
    :envvar:`XCLI_CONFIG` environment variable overrides this — that
    resolution happens in :mod:`core.config`, not here, because the
    loader also has to decide what to do when the override points at a
    missing file.

    This function does **not** create the file. The
    :class:`core.config.AppConfig.default` factory uses this as the
    default ``log_path`` neighbour; the ``x --config init`` handler is
    responsible for materialising the file.

    Returns
    -------
    Path
        Absolute path to ``<xcli_data_dir()>/config.yaml``.
    """
    return xcli_data_dir() / "config.yaml"


def xcli_log_path() -> Path:
    """Return the default path for the x-cli log file.

    Lives next to :func:`xcli_config_path` under the data directory
    (so a single ``%LOCALAPPDATA%\\x-cli`` tree holds all per-user
    state). Setting ``log_path: null`` in the config disables file
    output entirely — handled in :mod:`core.logging`, not here.

    Returns
    -------
    Path
        Absolute path to ``<xcli_data_dir()>/x.log``.
    """
    return xcli_data_dir() / "x.log"


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
    """Return the x-cli TODO root.

    Resolution order:

    1. If :envvar:`XCLI_TODO_DIR` is set, return it as-is. Tests use
       this to redirect to a ``tmp_path``; users can also use it to
       point at a custom location.
    2. Else if :envvar:`XAVIER_TODO_DIR` is set, return it as-is and
       emit a one-time deprecation warning to stderr (the name is
       historical; it predates the v0.5 rename to :envvar:`XCLI_TODO_DIR`).
       ``XAVIER_TODO_DIR`` will be removed in a future release.
    3. Otherwise return the platform-specific default under
       :func:`xcli_data_dir`:

       * Windows: ``<data_dir>\\todo\\`` (e.g.
         ``C:\\Users\\X\\AppData\\Local\\x-cli\\todo``)
       * Unix:    ``<data_dir>/todo/`` (e.g.
         ``~/.local/share/x-cli/todo``)

    The parent directory is created on every call (the ``任务/`` and
    ``归档/`` sub-directories are created lazily by the caller —
    typically :class:`core.storage.TaskStore` or the
    ``x todo init`` handler).

    **Hard invariant**: this function NEVER assumes a specific
    on-disk location such as ``~/.xavier/TODO/`` — the only bridge
    to a different TODO layout is the explicit
    ``x todo import --from <dir>`` command, which is one-way and
    read-only.

    Returns
    -------
    Path
        Absolute path to x-cli's TODO root. The directory itself is
        guaranteed to exist after this call returns; sub-directories
        are not.
    """
    override = os.environ.get(_TODO_DIR_ENV)
    if not override:
        legacy = os.environ.get(_LEGACY_TODO_DIR_ENV)
        if legacy:
            _warn_legacy_todo_dir()
            override = legacy
    if override:
        return Path(override)
    return xcli_data_dir() / "todo"


def _warn_legacy_todo_dir() -> None:
    """Emit a one-time stderr warning about the legacy env-var name.

    The deprecation flag is module-level so a single process running
    many CLI invocations warns exactly once. Resets on process restart.
    """
    global _LEGACY_TODO_DIR_WARNED
    if _LEGACY_TODO_DIR_WARNED:
        return
    _LEGACY_TODO_DIR_WARNED = True
    print(
        f"\u26a0\ufe0f  {_LEGACY_TODO_DIR_ENV} is deprecated; use {_TODO_DIR_ENV} instead. "
        f"{_LEGACY_TODO_DIR_ENV} will be removed in a future release.",
        file=sys.stderr,
    )


# ============================================================
#  Internal helpers
# ============================================================


def _ensure_dir(path: Path) -> Path:
    """Create ``path`` (and any missing parents) and return it.

    Idempotent: safe to call when the directory already exists.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
