"""Tests for ``TaskStore.search_tasks`` (v0.4.x new feature).

对应 BDD: ``docs/behaviors/todo-search-behavior.md`` (12 场景).

Style: matches ``test_storage.py`` — uses ``XCLI_TODO_DIR=tmp_path`` to
never touch the real ``~/.xavier/TODO`` and a local ``_write_task``
helper for fixture construction.

The ``search_tasks`` method is being implemented in parallel by
Subagent A. Tests target the documented API:

    TaskStore.search_tasks(
        keyword, *, include_archived=True, include_active=True
    ) -> list[Task]

Until Subagent A lands, all of these fail with ``AttributeError``
(TDD red state).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.models import ArchiveReason, Priority, Task, TaskStatus
from core.storage import TaskStore


# ============================================================
#  Fixtures + helpers
# ============================================================


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskStore:
    """Root the TaskStore at ``tmp_path``; never touches the real TODO dir."""
    monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))
    return TaskStore()


def _write_task(
    store: TaskStore,
    name: str,
    *,
    task_id: str | None = None,
    status: str = "pending",
    priority: str = "medium",
    created: str = "2026-06-01",
    updated: str = "2026-06-01",
    deadline: str | None = None,
    folder: str | None = None,
    tags: list[str] | None = None,
    note: str | None = None,
    reason: str | None = None,
    body: str = "",
    extra: dict | None = None,
    archived: bool = False,
    archive_date: str = "20260521",
) -> Task:
    """Drop a TODO.md on disk matching the BDD fixture for search tests."""
    if archived:
        target_dir = store.archive_dir / f"{archive_date}-{name}"
        relative_folder = f"归档/{archive_date}-{name}"
        if status == "pending":
            status_to_write = "archived"
        else:
            status_to_write = status
        reason_to_write = reason if reason is not None else "done"
    else:
        target_dir = store.active_dir / name
        relative_folder = folder or f"任务/{name}"
        status_to_write = status
        reason_to_write = reason
    target_dir.mkdir(parents=True, exist_ok=True)
    fields = {
        "id": task_id or name,
        "name": name,
        "status": TaskStatus(status_to_write),
        "priority": Priority(priority),
        "created": created,
        "updated": updated,
        "deadline": deadline,
        "folder": relative_folder,
        "tags": tags,
        "reason": ArchiveReason(reason_to_write) if reason_to_write else None,
        "body": body,
        "extra": dict(extra or {}),
    }
    if note is not None:
        fields["extra"] = {**fields["extra"], "note": note}
    task = Task(**fields)
    (target_dir / "TODO.md").write_text(task.to_markdown(), encoding="utf-8")
    return task


def _names(tasks: list[Task]) -> set[str]:
    """Return the set of task names (ignores duplicates by id)."""
    return {t.name for t in tasks}


# ============================================================
#  Scenario 1: 基本搜索（name 命中）
# ============================================================


def test_search_matches_name(store: TaskStore) -> None:
    """BDD §todo-search 1: substring in name field is a hit."""
    _write_task(store, "驾驶证考取", task_id="kemu1")
    _write_task(store, "助学金-下学期材料", task_id="zijin")
    results = store.search_tasks("驾驶")
    assert _names(results) == {"驾驶证考取"}


# ============================================================
#  Scenario 2: note 字段也参与搜索
# ============================================================


def test_search_matches_note(store: TaskStore) -> None:
    """BDD §todo-search 2: substring in note field is a hit."""
    _write_task(
        store, "kemu1", task_id="kemu1", note="跟朋友 AA 分摊"
    )
    results = store.search_tasks("AA")
    assert _names(results) == {"kemu1"}


# ============================================================
#  Scenario 3: tags 字段也参与搜索
# ============================================================


def test_search_matches_tag(store: TaskStore) -> None:
    """BDD §todo-search 3: substring in tags field is a hit."""
    _write_task(store, "kemu1", task_id="kemu1", tags=["驾照", "暑假"])
    results = store.search_tasks("驾照")
    assert _names(results) == {"kemu1"}


# ============================================================
#  Scenario 4: 大小写不敏感
# ============================================================


def test_search_is_case_insensitive(store: TaskStore) -> None:
    """BDD §todo-search 4: 'ALIYUN' matches 'aliyun'."""
    _write_task(store, "aliyun", task_id="aliyun")
    results = store.search_tasks("ALIYUN")
    assert _names(results) == {"aliyun"}


# ============================================================
#  Scenario 5: 默认包含归档
# ============================================================


def test_search_includes_archived_by_default(store: TaskStore) -> None:
    """BDD §todo-search 5: archive hits returned when include_archived=True (default)."""
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
    )
    results = store.search_tasks("kemu1")
    assert len(results) == 1
    assert results[0].id == "kemu1"
    assert results[0].status is TaskStatus.ARCHIVED


# ============================================================
#  Scenario 6: --active-only 只看 active
# ============================================================


def test_search_active_only_excludes_archived(store: TaskStore) -> None:
    """BDD §todo-search 6: include_active=True + include_archived=False hides archive."""
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
    )
    # No active kemu1 → empty result
    results = store.search_tasks("kemu1", include_active=True, include_archived=False)
    assert results == []


# ============================================================
#  Scenario 7: --archived-only 只看归档
# ============================================================


def test_search_archived_only_excludes_active(store: TaskStore) -> None:
    """BDD §todo-search 7: include_archived=True + include_active=False hides active."""
    _write_task(store, "kemu1", task_id="kemu1")  # active
    _write_task(
        store,
        "kemu1",
        task_id="kemu1",
        archived=True,
        archive_date="20260521",
    )
    results = store.search_tasks("kemu1", include_active=False, include_archived=True)
    assert len(results) == 1
    assert results[0].status is TaskStatus.ARCHIVED


# ============================================================
#  Scenario 8: 空 keyword (core 层: 返回空)
# ============================================================


def test_search_empty_keyword_returns_empty(store: TaskStore) -> None:
    """BDD §todo-search 8: empty keyword — CLI raises exit 2, core returns [].

    The storage layer's contract: an empty keyword yields no results
    (defensive default; the CLI translates this into exit 2).
    """
    _write_task(store, "kemu1", task_id="kemu1")
    results = store.search_tasks("")
    assert results == []


# ============================================================
#  Scenario 9: 无匹配
# ============================================================


def test_search_no_match_returns_empty(store: TaskStore) -> None:
    """BDD §todo-search 9: unmatched keyword → empty list (CLI prints hint)."""
    _write_task(store, "kemu1", task_id="kemu1")
    _write_task(store, "zijiashixi", task_id="zijiashixi")
    results = store.search_tasks("xyz_no_match_hopefully")
    assert results == []


# ============================================================
#  Scenario 10: 组合过滤（status + keyword）
# ============================================================


def test_search_combined_with_status_filter_at_core_layer(store: TaskStore) -> None:
    """BDD §todo-search 10: combined filter is a CLI concern.

    The core API returns all keyword matches; the CLI applies status
    filtering on top. This test verifies the core returns ALL keyword
    matches (so the CLI can filter).
    """
    _write_task(store, "A", task_id="A", status="in_progress")
    _write_task(store, "B", task_id="B", status="pending")
    _write_task(store, "C", task_id="C", status="in_progress")
    results = store.search_tasks("X")  # placeholder; see parametrised version
    # Just verify the core layer does NOT silently filter on status.
    assert isinstance(results, list)


def test_search_returns_all_keyword_matches_unfiltered(store: TaskStore) -> None:
    """Core layer returns all keyword hits; status filtering is CLI-side."""
    _write_task(store, "XA", task_id="XA", status="in_progress")
    _write_task(store, "XB", task_id="XB", status="pending")
    _write_task(store, "XC", task_id="XC", status="in_progress")
    _write_task(store, "YD", task_id="YD", status="in_progress")
    results = store.search_tasks("X")
    assert _names(results) == {"XA", "XB", "XC"}


# ============================================================
#  Scenario 11: 模糊匹配（多字符都出现）
# ============================================================


def test_search_fuzzy_per_char_present(store: TaskStore) -> None:
    """BDD §todo-search 11: every char of keyword appears in the field.

    '助材' should match '助学金-下学期材料' because both 助 and 材 appear.
    """
    _write_task(store, "助学金-下学期材料", task_id="zijin")
    results = store.search_tasks("助材")
    assert _names(results) == {"助学金-下学期材料"}


# ============================================================
#  Scenario 12: YAML 解析失败的任务不参与搜索
# ============================================================


def test_search_silently_skips_broken_yaml(store: TaskStore) -> None:
    """BDD §todo-search 12: broken YAML task is skipped, no exception, no warning."""
    # Valid task that should match
    _write_task(store, "goodX", task_id="goodX", note="contains X")
    # Broken task with the same keyword in the filename
    broken = store.active_dir / "坏X任务"
    broken.mkdir(parents=True)
    (broken / "TODO.md").write_text(
        "not valid frontmatter\n---\nrandom: 1\n", encoding="utf-8"
    )
    # Search must not raise; only the valid task matches
    results = store.search_tasks("X")
    assert _names(results) == {"goodX"}


# ============================================================
#  Cross-cutting
# ============================================================


def test_search_includes_active_by_default(store: TaskStore) -> None:
    """Active tasks are included by default (the archive opt-out is the only knob)."""
    _write_task(store, "kemu1", task_id="kemu1")
    results = store.search_tasks("kemu1")
    assert len(results) == 1
    assert results[0].status is not TaskStatus.ARCHIVED


def test_search_empty_store_returns_empty(store: TaskStore) -> None:
    """No tasks at all → empty list (not an error)."""
    assert store.search_tasks("anything") == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
