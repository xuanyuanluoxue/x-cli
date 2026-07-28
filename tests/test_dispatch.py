"""Architecture tests for the top-level lazy plugin dispatcher.

Behavior specification: docs/behaviors/cli-lazy-dispatch-behavior.md
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MODULES = {
    "plugins.todo",
    "plugins.secret",
    "plugins.diary",
    "plugins.note",
    "plugins.web",
}


def _run_isolated(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _last_json_line(output: str):
    return json.loads(output.strip().splitlines()[-1])


def test_importing_x_does_not_import_plugins():
    result = _run_isolated(
        "import json, sys, x; "
        "print(json.dumps(sorted(name for name in sys.modules "
        "if name in " + repr(PLUGIN_MODULES) + ")))"
    )

    assert result.returncode == 0, result.stderr
    assert _last_json_line(result.stdout) == []


@pytest.mark.parametrize("argv", [["--version"], ["--help"], ["help"]])
def test_top_level_early_exits_do_not_import_plugins(argv):
    source = f"""
import contextlib
import io
import json
import sys
import x

with contextlib.redirect_stdout(io.StringIO()):
    code = x.main({argv!r})
loaded = sorted(name for name in sys.modules if name in {PLUGIN_MODULES!r})
print(json.dumps({{"code": code, "loaded": loaded}}))
"""
    result = _run_isolated(source)

    assert result.returncode == 0, result.stderr
    payload = _last_json_line(result.stdout)
    assert payload == {"code": 0, "loaded": []}


def test_unknown_subcommand_does_not_import_plugins():
    source = f"""
import contextlib
import io
import json
import sys
import x

with contextlib.redirect_stderr(io.StringIO()):
    code = x.main(["unknown"])
loaded = sorted(name for name in sys.modules if name in {PLUGIN_MODULES!r})
print(json.dumps({{"code": code, "loaded": loaded}}))
"""
    result = _run_isolated(source)

    assert result.returncode == 0, result.stderr
    payload = _last_json_line(result.stdout)
    assert payload == {"code": 1, "loaded": []}


def test_note_help_only_imports_note_plugin():
    source = f"""
import contextlib
import io
import json
import sys
import x

with contextlib.redirect_stdout(io.StringIO()):
    try:
        x.main(["note", "--help"])
    except SystemExit as exc:
        code = exc.code
    else:
        code = 0
loaded = sorted(name for name in sys.modules if name in {PLUGIN_MODULES!r})
print(json.dumps({{"code": code, "loaded": loaded}}))
"""
    result = _run_isolated(source)

    assert result.returncode == 0, result.stderr
    payload = _last_json_line(result.stdout)
    assert payload == {"code": 0, "loaded": ["plugins.note"]}


def test_registry_keeps_stable_user_facing_order():
    from core.dispatch import SUBCOMMAND_MODULES

    assert list(SUBCOMMAND_MODULES) == ["todo", "secret", "diary", "note", "web"]


def test_loader_returns_none_for_unknown_plugin():
    from core.dispatch import load_subcommand_handler

    assert load_subcommand_handler("unknown") is None


def test_loader_rejects_plugin_without_callable_run(monkeypatch):
    from core import dispatch

    monkeypatch.setitem(dispatch.SUBCOMMAND_MODULES, "broken", "plugins.broken")
    monkeypatch.setattr(
        dispatch.importlib,
        "import_module",
        lambda _: SimpleNamespace(run="not-callable"),
    )

    with pytest.raises(TypeError, match=r"plugins\.broken.*callable run"):
        dispatch.load_subcommand_handler("broken")


def _imports_forbidden_root(path: Path, forbidden_root: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".", 1)[0] == forbidden_root:
                return True
        if isinstance(node, ast.Import):
            if any(alias.name.split(".", 1)[0] == forbidden_root for alias in node.names):
                return True
    return False


def test_core_and_plugins_do_not_import_entrypoint():
    offenders = [
        path.relative_to(ROOT).as_posix()
        for package in (ROOT / "core", ROOT / "plugins")
        for path in package.rglob("*.py")
        if _imports_forbidden_root(path, "x")
    ]

    assert offenders == []


def test_entrypoint_does_not_statically_import_plugins():
    assert not _imports_forbidden_root(ROOT / "x.py", "plugins")
