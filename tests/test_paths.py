"""Tests for ``core/paths.py`` — cross-platform secrets DB path resolution.

All tests use ``tmp_path`` plus :func:`pytest.MonkeyPatch.setenv` so
the real ``%LOCALAPPDATA%`` / ``$XDG_DATA_HOME`` is never read or
written.  Path resolution follows
:file:`docs/behaviors/secret-behavior.md` §"存储约定":

* Windows → ``%LOCALAPPDATA%\\x-cli\\secrets.json``
* macOS/Linux → ``$XDG_DATA_HOME/x-cli/secrets.json`` (fallback
  ``~/.local/share/x-cli/secrets.json`` when ``XDG_DATA_HOME`` is unset)
* Override via ``XCLI_SECRETS_DIR`` (points to a file path, not a dir)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from core.paths import xcli_data_dir, xcli_secrets_path


# ============================================================
#  Helpers
# ============================================================


def _clear_secrets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip both override and platform-specific data-dir vars."""
    monkeypatch.delenv("XCLI_SECRETS_DIR", raising=False)
    if sys.platform == "win32":
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
    else:
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)


# ============================================================
#  xcli_data_dir
# ============================================================


def test_xcli_data_dir_returns_path_under_platform_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``xcli_data_dir()`` returns ``<platform_dir>/x-cli`` and creates it."""
    _clear_secrets_env(monkeypatch)
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    result = xcli_data_dir()

    assert result == tmp_path / "x-cli"
    assert result.is_dir()  # created on demand


def test_xcli_data_dir_creates_nested_directory(monkeypatch, tmp_path):
    """The function creates intermediate directories if missing."""
    _clear_secrets_env(monkeypatch)
    deep = tmp_path / "level1" / "level2"
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(deep))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(deep))

    result = xcli_data_dir()

    assert result.exists()
    assert result.is_dir()


def test_xcli_data_dir_idempotent(monkeypatch, tmp_path):
    """Calling twice does not raise and returns the same path."""
    _clear_secrets_env(monkeypatch)
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    first = xcli_data_dir()
    second = xcli_data_dir()
    assert first == second
    assert first.is_dir()


# ============================================================
#  xcli_secrets_path
# ============================================================


def test_xcli_secrets_path_default_under_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No ``XCLI_SECRETS_DIR`` → ``<data_dir>/secrets.json``."""
    _clear_secrets_env(monkeypatch)
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    result = xcli_secrets_path()

    assert result == (tmp_path / "x-cli" / "secrets.json")
    # Parent directory should exist (xcli_data_dir creates it)
    assert result.parent.is_dir()


def test_xcli_secrets_path_env_override_takes_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``XCLI_SECRETS_DIR`` overrides whatever the default would be."""
    _clear_secrets_env(monkeypatch)
    custom = tmp_path / "custom.json"
    monkeypatch.setenv("XCLI_SECRETS_DIR", str(custom))

    result = xcli_secrets_path()
    assert result == custom


def test_xcli_secrets_path_override_wins_even_if_data_dir_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Both env vars set → ``XCLI_SECRETS_DIR`` wins."""
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "ignored"))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "ignored"))

    override = tmp_path / "explicit" / "secrets.json"
    monkeypatch.setenv("XCLI_SECRETS_DIR", str(override))

    result = xcli_secrets_path()
    assert result == override


def test_xcli_secrets_path_xdg_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """On non-Windows without ``XDG_DATA_HOME`` → ``~/.local/share/x-cli``."""
    if sys.platform == "win32":
        pytest.skip("XDG fallback only applies to POSIX platforms")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XCLI_SECRETS_DIR", raising=False)
    # Force HOME to a temp dir so the fallback is deterministic
    monkeypatch.setenv("HOME", str(tmp_path))

    result = xcli_secrets_path()
    assert result == tmp_path / ".local" / "share" / "x-cli" / "secrets.json"


# ============================================================
#  Cross-cutting: env var isolation
# ============================================================


def test_no_real_localappdata_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If our env vars are unset and the real LOCALAPPDATA would point
    somewhere dangerous, we must not read from it.

    We don't try to detect "dangerous" — we just guarantee that with
    XCLI_SECRETS_DIR set, the function never touches the real user
    directory.
    """
    _clear_secrets_env(monkeypatch)
    safe = tmp_path / "safe.json"
    monkeypatch.setenv("XCLI_SECRETS_DIR", str(safe))

    result = xcli_secrets_path()
    assert result == safe
    assert "x-cli" not in str(result)  # override wins, no default path used


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))