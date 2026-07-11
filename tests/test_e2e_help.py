"""E2E subprocess tests for ``x help`` and ``x <subcommand> --help`` passthrough.

Mirrors the pattern in :mod:`tests.test_e2e_todo` — spawns the installed
``x`` script and asserts on real exit code / stdout / stderr.

Maps to :mod:`docs.behaviors.help_passthrough_behavior` (6 scenarios):
  1. ``x help``                       -> top-level help
  2. ``x todo --help``                -> x todo help (not top-level)
  3. ``x todo -h``                    -> x todo help (short flag)
  4. ``x secret --help``              -> x secret help (not top-level)
  5. ``x web --help``                 -> x web help (not top-level)
  6. ``x todo help``                  -> x todo help (positional alias)
"""

from __future__ import annotations

import os
import subprocess
import sysconfig
from pathlib import Path
from typing import Sequence

import pytest


def _x_executable() -> str:
    """Path to installed ``x`` script (Windows: ``x.exe``; POSIX: ``x``)."""
    scripts_dir = Path(sysconfig.get_path("scripts"))
    name = "x.exe" if os.name == "nt" else "x"
    return str(scripts_dir / name)


@pytest.fixture
def x_path() -> str:
    p = _x_executable()
    if not Path(p).exists():
        pytest.skip(f"x not installed at {p}; run `pip install -e .` in venv")
    return p


def _run_x(
    x_path: str,
    args: Sequence[str],
    tmp_dir: Path,
    *,
    timeout: float = 30.0,
) -> tuple[int, str, str]:
    """Run ``x <args>`` with XCLI_TODO_DIR + XCLI_SECRETS_DIR isolated."""
    env = os.environ.copy()
    env["XCLI_TODO_DIR"] = str(tmp_dir)
    env["XCLI_SECRETS_DIR"] = str(tmp_dir)
    proc = subprocess.run(
        [x_path, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ============================================================
#  Scenario 1: x help
# ============================================================


def test_e2e_help_alias_prints_top_help(x_path: str, tmp_path: Path):
    """``x help`` (no leading dashes) prints top-level help and exits 0."""
    code, out, err = _run_x(x_path, ["help"], tmp_path)
    assert code == 0, f"stderr={err!r}"
    assert err == "", f"unexpected stderr: {err!r}"
    # Top-level markers
    assert "usage: x" in out, f"missing 'usage: x' in:\n{out}"
    assert "--config" in out, f"missing --config in:\n{out}"
    assert "SUBCOMMAND" in out, f"missing SUBCOMMAND in:\n{out}"
    # Subcommands listed
    for sub in ("todo", "secret", "web"):
        assert sub in out, f"missing subcommand {sub!r} in:\n{out}"


# ============================================================
#  Scenario 2: x todo --help (passthrough)
# ============================================================


def test_e2e_todo_help_flag_passes_through(x_path: str, tmp_path: Path):
    """``x todo --help`` prints *x todo* help, not top-level."""
    code, out, err = _run_x(x_path, ["todo", "--help"], tmp_path)
    assert code == 0, f"stderr={err!r}"
    # x todo markers
    assert "usage: x todo" in out, f"missing 'usage: x todo' in:\n{out}"
    assert "TODO 管理" in out, f"missing 'TODO 管理' description in:\n{out}"
    # TODO actions advertised
    for action in ("list", "add", "update", "archive", "stats"):
        assert action in out, f"action {action!r} missing from todo help:\n{out}"
    # Should NOT contain top-level --log-level (proves it's not top help)
    assert "--log-level" not in out, (
        f"top-level flag leaked into todo help:\n{out}"
    )


# ============================================================
#  Scenario 3: x todo -h
# ============================================================


def test_e2e_todo_short_help_flag(x_path: str, tmp_path: Path):
    """``x todo -h`` is equivalent to ``x todo --help``."""
    code, out, _ = _run_x(x_path, ["todo", "-h"], tmp_path)
    assert code == 0
    assert "usage: x todo" in out, f"missing 'usage: x todo' in:\n{out}"


# ============================================================
#  Scenario 4: x secret --help
# ============================================================


def test_e2e_secret_help_flag_passes_through(x_path: str, tmp_path: Path):
    """``x secret --help`` prints *x secret* help, not top-level."""
    code, out, err = _run_x(x_path, ["secret", "--help"], tmp_path)
    assert code == 0, f"stderr={err!r}"
    assert "usage: x secret" in out, f"missing 'usage: x secret' in:\n{out}"
    # Secret actions
    for action in ("list", "get", "set", "update", "rm", "search", "import", "export"):
        assert action in out, f"action {action!r} missing from secret help:\n{out}"
    # Should NOT contain top-level --log-level
    assert "--log-level" not in out, (
        f"top-level flag leaked into secret help:\n{out}"
    )


# ============================================================
#  Scenario 5: x web --help
# ============================================================


def test_e2e_web_help_flag_passes_through(x_path: str, tmp_path: Path):
    """``x web --help`` prints *x web* help, not top-level."""
    code, out, err = _run_x(x_path, ["web", "--help"], tmp_path)
    assert code == 0, f"stderr={err!r}"
    assert "usage: x web" in out, f"missing 'usage: x web' in:\n{out}"
    # Web flags
    for flag in ("--host", "--port", "--token", "--no-browser"):
        assert flag in out, f"flag {flag!r} missing from web help:\n{out}"
    # Should NOT contain top-level --log-level
    assert "--log-level" not in out, (
        f"top-level flag leaked into web help:\n{out}"
    )


# ============================================================
#  Scenario 6: x todo help (positional alias)
# ============================================================


def test_e2e_todo_positional_help(x_path: str, tmp_path: Path):
    """``x todo help`` (positional) is an alias for ``x todo --help``."""
    code, out, err = _run_x(x_path, ["todo", "help"], tmp_path)
    assert code == 0, f"stderr={err!r}"
    assert "usage: x todo" in out, f"missing 'usage: x todo' in:\n{out}"
    # No leakage of top-level flags
    assert "--log-level" not in out