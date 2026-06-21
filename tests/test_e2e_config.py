"""E2E subprocess tests for ``x --config`` / ``x --config-init`` / ``x --log-level``.

These tests launch the installed ``x`` script as a **separate process**
(via ``subprocess.run``) and assert on the real exit code / stdout /
stderr a user would see in PowerShell. They complement the in-process
unit tests in ``tests/test_config.py`` and ``tests/test_logging.py``
by catching issues that only show up in the actual entry point:

* ``pyproject.toml`` script entry wiring (``[project.scripts] x = "x:main"``)
* The full ``x`` -> ``x.main`` -> ``AppConfig.from_env_and_default`` chain
* Setuptools-generated ``x.exe`` wrapper on Windows
* argparse `--config` / `--config-init` / `--log-level` flag wiring

Each test maps to a scenario in ``docs/behaviors/config-behavior.md``.

Environment isolation
---------------------
System ``python`` on this machine is polluted with ``hydra-core`` which
imports ``antlr4`` at pytest collection time and breaks ``pytest`` on
Python 3.14. The tests therefore assume the project-local venv at
``.venv/`` exists and is used to run pytest. To set it up::

    py -3.14 -m venv .venv
    .venv/Scripts/python.exe -m pip install -e ".[dev]"
    .venv/Scripts/python.exe -m pytest tests/test_e2e_config.py

Per-test isolation policy:

* ``XAVIER_TODO_DIR`` and ``XCLI_SECRETS_DIR`` are **always** redirected
  to a tmp directory so the test never touches the real TODO / secrets
  store.
* ``XCLI_CONFIG`` is **always** stripped from the inherited env unless
  the test sets it explicitly — otherwise the developer's shell would
  leak into the subprocess.
* ``LOCALAPPDATA`` (Windows) / ``XDG_DATA_HOME`` (Unix) is **only**
  redirected by the ``--config-init`` tests, because ``x --config-init``
  writes to ``<data_dir>/config.yaml`` and there is currently no flag
  to redirect that path. Other tests avoid the issue by setting
  ``log_path: null`` in their custom config so no log file is created.
* We **never** introduce third-party dependencies; everything is
  stdlib + pytest.
"""

from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Sequence

import pytest


# ============================================================
#  Fixtures and helpers
# ============================================================


def _x_executable() -> str:
    """Return the absolute path to the installed ``x`` script.

    setuptools-generated entry point lives in the venv's ``scripts/``
    directory. On Windows this is ``x.exe``; on POSIX it is ``x``.
    """
    scripts_dir = Path(sysconfig.get_path("scripts"))
    name = "x.exe" if os.name == "nt" else "x"
    return str(scripts_dir / name)


@pytest.fixture
def x_path() -> str:
    """Absolute path to the installed ``x`` script (skip if missing)."""
    p = _x_executable()
    if not Path(p).exists():
        pytest.skip(
            f"x not installed at {p}; run `pip install -e .` in venv"
        )
    return p


def _isolation_env(tmp_path: Path) -> dict[str, str]:
    """Build the env-overrides dict that isolates storage subsystems.

    Always returned as a fresh dict; callers can pass it directly as
    ``env_overrides=_isolation_env(tmp_path)`` or merge with extra
    keys (``env_overrides={**_isolation_env(tmp_path), "XCLI_CONFIG": ...}``).
    """
    return {
        "XAVIER_TODO_DIR": str(tmp_path / "todo"),
        "XCLI_SECRETS_DIR": str(tmp_path / "secrets.json"),
    }


def _run_x(
    x_path: str,
    args: Sequence[str],
    *,
    env_overrides: dict[str, str] | None = None,
    env_pops: Sequence[str] = (),
    timeout: float = 30.0,
) -> tuple[int, str, str]:
    """Run ``x <args>`` with a controlled subprocess environment.

    Starts from a copy of the current process env, then removes keys
    listed in ``env_pops`` and applies ``env_overrides``. Returns
    ``(returncode, stdout, stderr)`` decoded as UTF-8.

    Note: callers are responsible for setting ``XAVIER_TODO_DIR`` and
    ``XCLI_SECRETS_DIR`` in ``env_overrides`` (use ``_isolation_env``)
    — this helper does not auto-isolate.
    """
    merged = os.environ.copy()
    for key in env_pops:
        merged.pop(key, None)
    if env_overrides:
        merged.update(env_overrides)
    proc = subprocess.run(
        [x_path, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=merged,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _data_dir_redirect(tmp_path: Path) -> dict[str, str]:
    """Redirect the platform-specific data dir to a tmp path.

    ``x --config-init`` writes ``<xcli_data_dir>/config.yaml`` and
    there is no flag/env to override that path directly — so we
    override the underlying env var (``LOCALAPPDATA`` on Windows,
    ``XDG_DATA_HOME`` on Unix) instead. This keeps the test off the
    real ``%LOCALAPPDATA%\\x-cli\\`` tree.
    """
    target = tmp_path / "data"
    if sys.platform == "win32":
        return {"LOCALAPPDATA": str(target)}
    # Unix: also pin HOME so any fallback that reads ``Path.home()``
    # is also redirected.
    return {
        "XDG_DATA_HOME": str(target),
        "HOME": str(tmp_path / "home"),
    }


# ============================================================
#  §1: Default config (no file)
# ============================================================


def test_e2e_no_config_file_uses_defaults(x_path: str, tmp_path: Path):
    """BDD §1: no XCLI_CONFIG + no --config → uses hardcoded defaults, exit 0.

    Verifies the no-config-found fallback path of ``AppConfig.from_env_and_default``:
    no file is found, hardcoded defaults are used, the command runs
    without error, and no unexpected log file content is produced.
    """
    (tmp_path / "todo").mkdir()
    code, out, err = _run_x(
        x_path,
        ["todo", "list"],
        env_overrides=_isolation_env(tmp_path),
        env_pops=("XCLI_CONFIG",),
    )
    assert code == 0, f"stderr={err!r}"
    # Empty TODO prints the "no tasks" indicator
    assert "没有任务" in out or "📭" in out, (
        f"expected empty-state message; got stdout={out!r}"
    )
    # Default log_level=WARNING → no DEBUG chatter
    assert "[DEBUG]" not in err, (
        f"unexpected DEBUG log on stderr with default config: {err!r}"
    )


# ============================================================
#  §2: --config-init
# ============================================================


def test_e2e_config_init_writes_default(x_path: str, tmp_path: Path):
    """BDD §2 (positive): `x --config-init` writes default config to data dir."""
    env_extra = _data_dir_redirect(tmp_path)
    code, out, err = _run_x(
        x_path,
        ["--config-init"],
        env_overrides=env_extra,
    )
    assert code == 0, f"stderr={err!r}"

    # xcli_data_dir() resolves to <LOCALAPPDATA>/x-cli (or XDG equivalent)
    config_path = tmp_path / "data" / "x-cli" / "config.yaml"
    assert config_path.is_file(), f"expected config at {config_path}"

    body = config_path.read_text(encoding="utf-8")
    for key in ("todo_dir", "secrets_path", "log_level", "log_path"):
        assert key in body, f"missing key {key!r} in generated config:\n{body}"
    assert "log_level: WARNING" in body, (
        f"default log_level should be WARNING; got:\n{body}"
    )

    # stdout announces success with the full path
    assert "✅" in out and "config.yaml" in out, (
        f"expected success indicator on stdout; got: {out!r}"
    )
    # No error chatter
    assert "❌" not in err


def test_e2e_config_init_does_not_overwrite(x_path: str, tmp_path: Path):
    """BDD §2 (negative): `x --config-init` on an existing file → exit 2, untouched."""
    env_extra = _data_dir_redirect(tmp_path)

    # Pre-create the config file with a user's stub
    cfg = tmp_path / "data" / "x-cli" / "config.yaml"
    cfg.parent.mkdir(parents=True)
    original = "# my custom config — DO NOT OVERWRITE\ntodo_dir: /my/custom/path\n"
    cfg.write_text(original, encoding="utf-8")

    code, out, err = _run_x(
        x_path,
        ["--config-init"],
        env_overrides=env_extra,
    )
    assert code == 2, (
        f"expected exit 2 on existing config; got {code}; stderr={err!r}"
    )
    # Stderr should explain why we refused
    assert "已存在" in err or "exists" in err.lower(), (
        f"stderr should mention the existing file; got: {err!r}"
    )

    # File must be byte-identical to the pre-seeded content
    assert cfg.read_text(encoding="utf-8") == original, (
        f"existing config was overwritten:\n{cfg.read_text(encoding='utf-8')!r}"
    )


# ============================================================
#  §3: XCLI_CONFIG=<path> env var
# ============================================================


def test_e2e_env_config_overrides_default(x_path: str, tmp_path: Path):
    """BDD §3: XCLI_CONFIG=<tmp> → that config file is loaded.

    Verification strategy: write a config with ``log_level: DEBUG``
    and ``log_path: null`` (no file pollution); run ``x todo list``;
    assert that x.main emits its ``effective config`` DEBUG log on
    stderr. A correctly-loaded config turns on DEBUG output; the
    default config (WARNING) would suppress it.
    """
    cfg = tmp_path / "my-config.yaml"
    cfg.write_text(
        "# env-driven config\n"
        "log_level: DEBUG\n"
        "log_path: null\n",
        encoding="utf-8",
    )
    (tmp_path / "todo").mkdir()

    code, out, err = _run_x(
        x_path,
        ["todo", "list"],
        env_overrides={
            **_isolation_env(tmp_path),
            "XCLI_CONFIG": str(cfg),
        },
    )
    assert code == 0, f"stderr={err!r}"
    # Config says DEBUG → x.main's effective-config log must surface
    assert "[DEBUG]" in err, (
        f"expected [DEBUG] log from config file in stderr; got: {err!r}"
    )
    # And it should mention the x.main logger / effective config payload
    assert "x.main" in err or "effective config" in err, (
        f"expected x.main effective-config log line; got: {err!r}"
    )


# ============================================================
#  §4: --config <path> CLI flag
# ============================================================


def test_e2e_cli_config_flag_overrides(x_path: str, tmp_path: Path):
    """BDD §4: `x --config <tmp> ...` loads that config file (env override optional)."""
    cfg = tmp_path / "alt-config.yaml"
    cfg.write_text(
        "log_level: DEBUG\n"
        "log_path: null\n",
        encoding="utf-8",
    )
    (tmp_path / "todo").mkdir()

    code, out, err = _run_x(
        x_path,
        ["--config", str(cfg), "todo", "list"],
        env_overrides=_isolation_env(tmp_path),
        env_pops=("XCLI_CONFIG",),
    )
    assert code == 0, f"stderr={err!r}"
    assert "[DEBUG]" in err, (
        f"expected [DEBUG] from --config file in stderr; got: {err!r}"
    )


# ============================================================
#  §5: --config <missing path> → exit 5
# ============================================================


def test_e2e_missing_explicit_config_exits_5(x_path: str, tmp_path: Path):
    """BDD §5: `x --config /nonexistent ...` → exit 5 + clear stderr message."""
    (tmp_path / "todo").mkdir()
    code, out, err = _run_x(
        x_path,
        ["--config", "/nonexistent/path/never-exists.yaml", "todo", "list"],
        env_overrides=_isolation_env(tmp_path),
        env_pops=("XCLI_CONFIG",),
    )
    assert code == 5, (
        f"expected exit 5 for missing explicit config; got {code}; stderr={err!r}"
    )
    assert "不存在" in err or "not found" in err.lower(), (
        f"stderr should explain the missing file; got: {err!r}"
    )


# ============================================================
#  §6: Bad YAML → exit 5
# ============================================================


def test_e2e_bad_yaml_config_exits_5(x_path: str, tmp_path: Path):
    """BDD §6: `x --config <bad-yaml> ...` → exit 5 + parse-error message.

    The YAML below deliberately mixes a list item with a mapping item
    at the same indent level, which the hand-written parser in
    :mod:`core.parser` rejects with ``ValueError: unexpected list
    item at indent 0``. ``AppConfig.from_yaml_file`` wraps that into
    ``ConfigError`` → exit 5.
    """
    cfg = tmp_path / "bad.yaml"
    cfg.write_text(
        "log_level: DEBUG\n"
        "todo_dir:\n"
        "- a\n"
        "- b\n"
        "- c: [broken\n",
        encoding="utf-8",
    )
    (tmp_path / "todo").mkdir()

    code, out, err = _run_x(
        x_path,
        ["--config", str(cfg), "todo", "list"],
        env_overrides=_isolation_env(tmp_path),
        env_pops=("XCLI_CONFIG",),
    )
    assert code == 5, (
        f"expected exit 5 for bad YAML; got {code}; stderr={err!r}"
    )
    assert "解析失败" in err or "parse" in err.lower(), (
        f"stderr should mention parse failure; got: {err!r}"
    )


# ============================================================
#  §7: log_level values
# ============================================================


def test_e2e_log_level_debug_shows_debug(x_path: str, tmp_path: Path):
    """BDD §7 (DEBUG): `x --log-level DEBUG ...` → stderr includes [DEBUG]."""
    (tmp_path / "todo").mkdir()
    code, out, err = _run_x(
        x_path,
        ["--log-level", "DEBUG", "todo", "list"],
        env_overrides=_isolation_env(tmp_path),
        env_pops=("XCLI_CONFIG",),
    )
    assert code == 0, f"stderr={err!r}"
    # DEBUG threshold means x.main's "effective config" log surfaces
    assert "[DEBUG]" in err, (
        f"expected [DEBUG] in stderr with --log-level DEBUG; got: {err!r}"
    )


def test_e2e_log_level_warning_silences_debug(x_path: str, tmp_path: Path):
    """BDD §7 (WARNING): `x --log-level WARNING ...` → stderr has NO [DEBUG]."""
    (tmp_path / "todo").mkdir()
    code, out, err = _run_x(
        x_path,
        ["--log-level", "WARNING", "todo", "list"],
        env_overrides=_isolation_env(tmp_path),
        env_pops=("XCLI_CONFIG",),
    )
    assert code == 0, f"stderr={err!r}"
    # WARNING threshold: DEBUG lines must NOT be emitted, even though
    # x.main tries to log them (the logger filters by level).
    assert "[DEBUG]" not in err, (
        f"expected NO [DEBUG] with --log-level WARNING; got: {err!r}"
    )


# ============================================================
#  §8: log_path writes to file
# ============================================================


def test_e2e_log_writes_to_file(x_path: str, tmp_path: Path):
    """BDD §8: log_path=<tmp>/x.log → DEBUG/INFO/WARNING lines written to that file.

    The hand-written config sets ``log_level: DEBUG`` (so x.main's
    ``effective config`` log is emitted) and ``log_path: <tmp>/x.log``
    (so the file handler is installed). After the run, both stderr
    AND the file must contain the DEBUG line — that's the "dual
    write" behaviour the BDD promises.
    """
    log_file = tmp_path / "x.log"
    # Pre-clean (paranoid: leftover from a previous failed run)
    if log_file.exists():
        log_file.unlink()

    cfg = tmp_path / "config-with-log.yaml"
    cfg.write_text(
        f"log_level: DEBUG\n"
        f"log_path: {log_file}\n",
        encoding="utf-8",
    )
    (tmp_path / "todo").mkdir()

    code, out, err = _run_x(
        x_path,
        ["--config", str(cfg), "todo", "list"],
        env_overrides=_isolation_env(tmp_path),
        env_pops=("XCLI_CONFIG",),
    )
    assert code == 0, f"stderr={err!r}"

    # File must exist and carry the DEBUG line
    assert log_file.is_file(), f"expected log file at {log_file}"
    body = log_file.read_text(encoding="utf-8")
    assert "[DEBUG]" in body, (
        f"expected [DEBUG] in log file; got: {body!r}"
    )
    # Sanity: stderr should also have the line (dual write)
    assert "[DEBUG]" in err, (
        f"expected [DEBUG] in stderr as well (dual write); got: {err!r}"
    )

    # Cleanup so a re-run doesn't see stale content
    log_file.unlink(missing_ok=True)


# ============================================================
#  §9: log_path: null → no file
# ============================================================


def test_e2e_log_null_no_file(x_path: str, tmp_path: Path):
    """BDD §9: log_path: null → WARNING/DEBUG go to stderr, NO file created.

    The config sets ``log_level: DEBUG`` so x.main would normally log;
    ``log_path: null`` disables the file handler. The DEBUG line
    should still appear on stderr (logging not silenced globally),
    but no ``x*.log`` file may appear under the tmp dir.
    """
    cfg = tmp_path / "config-null-log.yaml"
    cfg.write_text(
        "log_level: DEBUG\n"
        "log_path: null\n",
        encoding="utf-8",
    )
    (tmp_path / "todo").mkdir()

    # Pre-clean any leftover log files in tmp_path
    for stale in tmp_path.glob("x*.log"):
        stale.unlink()
    stale_log = tmp_path / "x.log"
    if stale_log.exists():
        stale_log.unlink()

    code, out, err = _run_x(
        x_path,
        ["--config", str(cfg), "todo", "list"],
        env_overrides=_isolation_env(tmp_path),
        env_pops=("XCLI_CONFIG",),
    )
    assert code == 0, f"stderr={err!r}"

    # Stderr still has DEBUG (the file handler is just absent)
    assert "[DEBUG]" in err, (
        f"expected [DEBUG] in stderr even with log_path: null; got: {err!r}"
    )

    # No log file anywhere under tmp_path
    log_candidates = (
        list(tmp_path.glob("*.log"))
        + list(tmp_path.glob("x*.log"))
        + [tmp_path / "x.log"]
    )
    log_candidates = [p for p in log_candidates if p.exists()]
    assert log_candidates == [], (
        f"log_path: null should create NO file; found: {log_candidates}"
    )


# ============================================================
#  §10: Backward compat
# ============================================================


def test_e2e_no_args_still_works(x_path: str, tmp_path: Path):
    """BDD §10: `x todo list` (no flags, no XCLI_CONFIG) keeps old behaviour.

    The hard invariant the BDD calls out: upgrading to a binary that
    knows about ``--config`` / ``--log-level`` MUST NOT break old
    invocations. We verify by running the canonical ``x todo list``
    with no env overrides beyond storage isolation and confirming it
    succeeds with the expected empty-state output and no DEBUG noise.
    """
    (tmp_path / "todo").mkdir()
    code, out, err = _run_x(
        x_path,
        ["todo", "list"],
        env_overrides=_isolation_env(tmp_path),
        env_pops=("XCLI_CONFIG",),
    )
    assert code == 0, f"stderr={err!r}"
    # Empty TODO prints the mail indicator
    assert "没有任务" in out or "📭" in out, (
        f"expected empty-state output; got stdout={out!r}"
    )
    # Default log_level=WARNING → no DEBUG chatter on stderr
    assert "[DEBUG]" not in err, (
        f"default WARNING level must suppress DEBUG output; got: {err!r}"
    )