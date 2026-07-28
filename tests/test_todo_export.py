"""Tests for export (v0.5 Phase E).

Each test maps to a scenario in
``docs/behaviors/todo-export-behavior.md``.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from core.storage import TaskStore
from x import main


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskStore:
    real_todo = Path.home() / ".xavier" / "TODO"
    real_active_before = (
        sorted(p.name for p in (real_todo / "任务").iterdir())
        if (real_todo / "任务").is_dir()
        else []
    )
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
    yield TaskStore()
    real_active_after = (
        sorted(p.name for p in (real_todo / "任务").iterdir())
        if (real_todo / "任务").is_dir()
        else []
    )
    assert real_active_after == real_active_before


def _invoke(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            rc = main(list(argv))
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 2
    return rc, out.getvalue(), err.getvalue()


# ============================================================
#  Scenario 1: export --format json to stdout
# ============================================================


def test_export_json_stdout(store: TaskStore) -> None:
    """对应 BDD §场景 1：export --format json → stdout 是合法 JSON 数组。"""
    _invoke("todo", "add", "ta", "--priority", "high")
    _invoke("todo", "add", "tb", "--deadline", "2026-07-01")

    rc, out, _ = _invoke("todo", "export", "--format", "json")
    assert rc == 0, f"export failed: {out!r}"

    # Parse as JSON
    data = json.loads(out)
    assert isinstance(data, list), f"expected list, got {type(data)}"
    assert len(data) == 2, f"expected 2 tasks, got {len(data)}"


# ============================================================
#  Scenario 2: export --format json --output file
# ============================================================


def test_export_json_output_file(store: TaskStore, tmp_path: Path) -> None:
    """对应 BDD §场景 2：export --output 写到文件。"""
    _invoke("todo", "add", "ta")
    out_file = tmp_path / "tasks.json"

    rc, out, _ = _invoke("todo", "export", "--format", "json",
                          "--output", str(out_file))
    assert rc == 0, f"export failed: {out!r}"

    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1


# ============================================================
#  Scenario 3: export --format csv
# ============================================================


def test_export_csv(store: TaskStore) -> None:
    """对应 BDD §场景 3：export --format csv 是 CSV，tags 用 ; 分隔。"""
    _invoke("todo", "add", "ta", "--tags", "a,b",
            "--priority", "high", "--deadline", "2026-07-01")

    rc, out, _ = _invoke("todo", "export", "--format", "csv")
    assert rc == 0, f"export failed: {out!r}"

    # Parse CSV
    reader = csv.DictReader(io.StringIO(out))
    rows = list(reader)
    assert len(rows) == 1
    row = rows[0]
    # priority + id + tags
    assert row["priority"] == "high", f"priority wrong: {row.get('priority')!r}"
    assert row["id"] == "ta", f"id wrong: {row.get('id')!r}"
    # tags should be 'a;b' (semicolon-separated)
    assert row["tags"] == "a;b", f"tags wrong: {row.get('tags')!r}"


# ============================================================
#  Scenario 4: export --format md
# ============================================================


def test_export_md(store: TaskStore) -> None:
    """对应 BDD §场景 4：export --format md 是 Markdown 表格。"""
    _invoke("todo", "add", "ta", "--priority", "high")

    rc, out, _ = _invoke("todo", "export", "--format", "md")
    assert rc == 0, f"export failed: {out!r}"

    # Verify markdown table format
    assert "|" in out
    assert "ta" in out
    # Header row with | separator
    lines = out.splitlines()
    assert any("|---" in line or "| ---" in line for line in lines), (
        f"missing markdown separator: {out!r}"
    )


# ============================================================
#  Scenario 5: export --all includes archived
# ============================================================


def test_export_all_includes_archived(store: TaskStore) -> None:
    """对应 BDD §场景 5：export --all 含 archived。"""
    _invoke("todo", "add", "active-task")
    _invoke("todo", "add", "to-archive")
    _invoke("todo", "archive", "to-archive", "--reason", "done")

    rc, out, _ = _invoke("todo", "export", "--format", "json", "--all")
    assert rc == 0

    data = json.loads(out)
    assert len(data) == 2, f"expected 2 tasks with --all, got {len(data)}"
    names = {t.get("name") for t in data}
    assert "active-task" in names
    assert "to-archive" in names


# ============================================================
#  Scenario 6: default no --format
# ============================================================


def test_export_default_no_format(store: TaskStore) -> None:
    """对应 BDD §场景 6：export 无 --format → 退出码 2。"""
    rc, out, stderr = _invoke("todo", "export")
    assert rc == 2
    combined = out + stderr
    assert "format" in combined or "格式" in combined


# ============================================================
#  Scenario 7: export --format invalid
# ============================================================


def test_export_invalid_format(store: TaskStore) -> None:
    """对应 BDD §场景 7：export --format yaml → rc=2。"""
    rc, out, stderr = _invoke("todo", "export", "--format", "yaml")
    assert rc == 2
    combined = out + stderr
    assert "格式" in combined or "format" in combined.lower()
