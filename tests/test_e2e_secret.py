"""E2E subprocess tests for ``x secret`` commands.

These tests launch the installed ``x`` script as a **separate process**
and assert on the real exit code / stdout / stderr a user would see in
PowerShell. They complement in-process unit tests in tests/test_secrets.py.

Each test maps to a scenario in docs/behaviors/secret-behavior.md.

Storage: uses XCLI_SECRETS_DIR env var to redirect to a temp file.
NEVER touches the real %LOCALAPPDATA%\\x-cli\\secrets.json.
"""

from __future__ import annotations

import os
import subprocess
import sysconfig
from pathlib import Path
from typing import Sequence

import pytest


def _x_executable() -> str:
    scripts_dir = Path(sysconfig.get_path("scripts"))
    name = "x.exe" if os.name == "nt" else "x"
    return str(scripts_dir / name)


@pytest.fixture
def x_path() -> str:
    p = _x_executable()
    if not Path(p).exists():
        pytest.skip(f"x not installed at {p}")
    return p


@pytest.fixture
def secrets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect secrets DB to a temp file via XCLI_SECRETS_DIR."""
    db_file = tmp_path / "secrets.json"
    monkeypatch.setenv("XCLI_SECRETS_DIR", str(db_file))
    return tmp_path


def _run_x(
    x_path: str,
    args: Sequence[str],
    secrets_dir: Path,
    *,
    timeout: float = 30.0,
) -> tuple[int, str, str]:
    """Run x <args> as subprocess with XCLI_SECRETS_DIR redirected."""
    env = os.environ.copy()
    env["XCLI_SECRETS_DIR"] = str(secrets_dir / "secrets.json")
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
#  BDD scenario 16: x secret (no action) shows help
# ============================================================

def test_e2e_secret_no_action_shows_help(x_path, secrets_dir):
    code, out, _ = _run_x(x_path, ["secret"], secrets_dir)
    assert code == 0
    # All 8 sub-commands listed
    for action in ("list", "get", "set", "update", "rm", "search", "import", "export"):
        assert action in out, f"action {action!r} missing from secret help"


# ============================================================
#  BDD scenario 17: x secret --help
# ============================================================

def test_e2e_secret_help_flag(x_path, secrets_dir):
    code, out, _ = _run_x(x_path, ["secret", "--help"], secrets_dir)
    assert code == 0
    assert "usage" in out.lower() or "用法" in out


# ============================================================
#  BDD scenario 1: list empty store
# ============================================================

def test_e2e_list_empty(x_path, secrets_dir):
    code, out, err = _run_x(x_path, ["secret", "list"], secrets_dir)
    assert code == 0
    assert err == ""
    # Empty store prints header only, no data
    # (acceptable: header + 0 rows, or "📭 empty" message)


# ============================================================
#  BDD scenario 5 + 1: set then list
# ============================================================

def test_e2e_set_then_list(x_path, secrets_dir):
    code, out, err = _run_x(
        x_path,
        ["secret", "set", "minimax", "--value", "sk-test1234", "--category", "接口密钥"],
        secrets_dir,
    )
    assert code == 0
    assert "✅" in out
    assert "minimax" in out

    # Subsequent list shows it
    code2, out2, _ = _run_x(x_path, ["secret", "list"], secrets_dir)
    assert code2 == 0
    assert "minimax" in out2
    assert "接口密钥" in out2
    # CRITICAL: value MUST NOT appear in list output
    assert "sk-test1234" not in out2


# ============================================================
#  BDD scenario 2: get prints value to stdout + warning to stderr
# ============================================================

def test_e2e_get_returns_value(x_path, secrets_dir):
    _run_x(
        x_path,
        ["secret", "set", "minimax", "--value", "sk-test1234"],
        secrets_dir,
    )
    code, out, err = _run_x(x_path, ["secret", "get", "minimax"], secrets_dir)
    assert code == 0
    # stdout: the value (first line)
    assert "sk-test1234" in out
    # stderr: warning
    assert "🔐" in err or "警告" in err


def test_e2e_get_full_shows_metadata(x_path, secrets_dir):
    _run_x(
        x_path,
        ["secret", "set", "minimax", "--value", "sk-x", "--note", "for testing"],
        secrets_dir,
    )
    code, out, _ = _run_x(x_path, ["secret", "get", "minimax", "--full"], secrets_dir)
    assert code == 0
    for field in ("minimax", "sk-x", "for testing", "category", "value", "note"):
        assert field in out.lower(), f"field {field!r} missing"


def test_e2e_get_nonexistent_exits_3(x_path, secrets_dir):
    code, _, err = _run_x(x_path, ["secret", "get", "nonexistent"], secrets_dir)
    assert code == 3
    assert "不存在" in err or "nonexistent" in err


# ============================================================
#  BDD scenario 6: set with no --value fails (argparse)
# ============================================================

def test_e2e_set_missing_value_exits_2(x_path, secrets_dir):
    code, _, err = _run_x(x_path, ["secret", "set", "minimax"], secrets_dir)
    assert code == 2
    assert "required" in err.lower() or "value" in err.lower()


# ============================================================
#  BDD scenario 7: set duplicate exits 4
# ============================================================

def test_e2e_set_duplicate_exits_4(x_path, secrets_dir):
    _run_x(
        x_path,
        ["secret", "set", "minimax", "--value", "sk-1"],
        secrets_dir,
    )
    code, _, err = _run_x(
        x_path,
        ["secret", "set", "minimax", "--value", "sk-2"],
        secrets_dir,
    )
    assert code == 4
    assert "已存在" in err or "exists" in err.lower()


# ============================================================
#  BDD scenario 8: update changes value
# ============================================================

def test_e2e_update_changes_value(x_path, secrets_dir):
    _run_x(
        x_path,
        ["secret", "set", "minimax", "--value", "sk-old"],
        secrets_dir,
    )
    code, out, _ = _run_x(
        x_path,
        ["secret", "update", "minimax", "--value", "sk-new"],
        secrets_dir,
    )
    assert code == 0
    assert "✅" in out

    # Verify via get
    _, out2, _ = _run_x(x_path, ["secret", "get", "minimax"], secrets_dir)
    assert "sk-new" in out2
    assert "sk-old" not in out2


def test_e2e_update_nonexistent_exits_3(x_path, secrets_dir):
    code, _, err = _run_x(
        x_path,
        ["secret", "update", "nonexistent", "--value", "sk-x"],
        secrets_dir,
    )
    assert code == 3


# ============================================================
#  BDD scenario 10 + 11: rm
# ============================================================

def test_e2e_rm_removes_entry(x_path, secrets_dir):
    _run_x(
        x_path,
        ["secret", "set", "minimax", "--value", "sk-x"],
        secrets_dir,
    )
    code, out, _ = _run_x(x_path, ["secret", "rm", "minimax"], secrets_dir)
    assert code == 0
    assert "✅" in out

    # Verify gone
    code2, _, _ = _run_x(x_path, ["secret", "get", "minimax"], secrets_dir)
    assert code2 == 3


def test_e2e_rm_nonexistent_exits_3(x_path, secrets_dir):
    code, _, err = _run_x(x_path, ["secret", "rm", "nonexistent"], secrets_dir)
    assert code == 3


# ============================================================
#  BDD scenario 12: search by keyword (name/note, NOT value)
# ============================================================

def test_e2e_search_matches_name(x_path, secrets_dir):
    _run_x(x_path, ["secret", "set", "minimax-prod", "--value", "sk-x"], secrets_dir)
    _run_x(x_path, ["secret", "set", "openai", "--value", "sk-y"], secrets_dir)

    code, out, _ = _run_x(x_path, ["secret", "search", "minimax"], secrets_dir)
    assert code == 0
    assert "minimax-prod" in out
    assert "openai" not in out


def test_e2e_search_does_not_match_value(x_path, secrets_dir):
    """CRITICAL: search must NOT leak value matches."""
    _run_x(
        x_path,
        ["secret", "set", "minimax", "--value", "sk-very-unique-secret"],
        secrets_dir,
    )
    code, out, _ = _run_x(
        x_path,
        ["secret", "search", "very-unique-secret"],
        secrets_dir,
    )
    assert code == 0
    assert "minimax" not in out  # value match must not be returned


# ============================================================
#  BDD scenario 13: import from a .md dir
# ============================================================

def test_e2e_import_from_md_dir(x_path, secrets_dir, tmp_path):
    """Create a tmp dir with .md files, import, verify entries created."""
    md_file = tmp_path / "接口密钥.md"
    md_file.write_text(
        "---\n"
        "version: \"1.0\"\n"
        "count: 1\n"
        "---\n"
        "\n"
        "## minimax\n"
        "\n"
        "```text\n"
        "api_key: sk-from-md\n"
        "```\n",
        encoding="utf-8",
    )

    code, out, _ = _run_x(
        x_path,
        ["secret", "import", "--from", str(tmp_path)],
        secrets_dir,
    )
    assert code == 0
    assert "📥" in out or "导入" in out or "import" in out.lower()

    # Verify entry exists
    code2, out2, _ = _run_x(x_path, ["secret", "get", "minimax"], secrets_dir)
    assert code2 == 0
    assert "sk-from-md" in out2

    # CRITICAL: old .md file is preserved
    assert md_file.exists()


def test_e2e_import_missing_dir_exits_5(x_path, secrets_dir):
    code, _, err = _run_x(
        x_path,
        ["secret", "import", "--from", "/nonexistent/path/xyz"],
        secrets_dir,
    )
    assert code == 5
    assert "不存在" in err or "not found" in err.lower()


# ============================================================
#  BDD scenario 15: export creates backup
# ============================================================

def test_e2e_export_creates_backup(x_path, secrets_dir, tmp_path):
    _run_x(
        x_path,
        ["secret", "set", "minimax", "--value", "sk-x"],
        secrets_dir,
    )

    backup = tmp_path / "backup.json"
    code, out, _ = _run_x(
        x_path,
        ["secret", "export", "--to", str(backup)],
        secrets_dir,
    )
    assert code == 0
    assert backup.exists()
    assert "✅" in out


# ============================================================
#  Hard constraint: list NEVER shows value
# ============================================================

def test_e2e_list_never_shows_value(x_path, secrets_dir):
    """Even with many entries, list output must never include values."""
    secrets = [
        ("minimax", "sk-secret-1"),
        ("openai", "sk-secret-2"),
        ("aliyun", "sk-secret-3"),
    ]
    for name, value in secrets:
        _run_x(
            x_path,
            ["secret", "set", name, "--value", value],
            secrets_dir,
        )

    code, out, _ = _run_x(x_path, ["secret", "list"], secrets_dir)
    assert code == 0
    for _, value in secrets:
        assert value not in out, f"value {value!r} leaked in list output:\n{out}"