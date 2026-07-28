"""Tests for ``x note`` P0.

BDD: :mod:`docs.behaviors.note-behavior`.
"""

from __future__ import annotations

import sys
from datetime import datetime

import pytest

from core.note import NoteDataError, NoteNotFoundError, NoteStore
from core.dispatch import SUBCOMMAND_MODULES
from core.parser import dump_frontmatter, parse_frontmatter
from core.paths import xcli_notes_dir
from plugins import note as note_plugin
from x import main


def test_notes_path_defaults_under_xcli_data_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("XCLI_NOTES_DIR", raising=False)
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    result = xcli_notes_dir()

    assert result == tmp_path / "x-cli" / "notes"
    assert result.is_dir()


def test_notes_path_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "knowledge"
    monkeypatch.setenv("XCLI_NOTES_DIR", str(custom))

    result = xcli_notes_dir()

    assert result == custom
    assert result.is_dir()


def test_add_writes_frontmatter_and_body(tmp_path):
    store = NoteStore(tmp_path)

    note = store.add(
        "  MiniMax API 配置  ",
        body="这里是正文。",
        tags=["AI", "API"],
        now=datetime(2026, 7, 17, 14, 30, 12),
    )

    assert note.id == "n-20260717-143012"
    assert note.title == "MiniMax API 配置"
    path = tmp_path / f"{note.id}.md"
    metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert metadata == {
        "id": "n-20260717-143012",
        "title": "MiniMax API 配置",
        "tags": ["AI", "API"],
        "created_at": "2026-07-17T14:30:12",
        "updated_at": "2026-07-17T14:30:12",
    }
    assert body == "这里是正文。\n"


def test_add_uses_collision_suffix_without_overwriting(tmp_path):
    store = NoteStore(tmp_path)
    now = datetime(2026, 7, 17, 14, 30, 12)
    first = store.add("第一篇", now=now)
    second = store.add("第二篇", now=now)
    third = store.add("第三篇", now=now)

    assert [first.id, second.id, third.id] == [
        "n-20260717-143012",
        "n-20260717-143012-2",
        "n-20260717-143012-3",
    ]
    assert (tmp_path / f"{first.id}.md").read_text(encoding="utf-8")


def test_tenth_same_second_collision_remains_readable(tmp_path):
    store = NoteStore(tmp_path)
    now = datetime(2026, 7, 17, 14, 30, 12)

    notes = [store.add(f"第 {index} 篇", now=now) for index in range(1, 11)]

    assert notes[-1].id == "n-20260717-143012-10"
    assert store.get(notes[-1].id).title == "第 10 篇"


@pytest.mark.parametrize("title", ["", "   ", "\t\r\n"])
def test_add_rejects_blank_title(tmp_path, title):
    with pytest.raises(ValueError, match="笔记标题不能为空"):
        NoteStore(tmp_path).add(title)
    assert list(tmp_path.glob("*.md")) == []


def test_add_normalizes_and_deduplicates_tags(tmp_path):
    note = NoteStore(tmp_path).add(
        "标签测试",
        tags=[" AI ", "api", "ai", "", "API", "工具"],
        now=datetime(2026, 7, 17, 10, 0, 0),
    )
    assert note.tags == ["AI", "api", "工具"]


def test_list_notes_orders_newest_first_and_defaults_to_twenty(tmp_path):
    store = NoteStore(tmp_path)
    for minute in range(25):
        store.add(
            f"笔记 {minute}",
            now=datetime(2026, 7, 17, 10, minute, 0),
        )

    notes = store.list_notes()

    assert len(notes) == 20
    assert notes[0].title == "笔记 24"
    assert notes[-1].title == "笔记 5"


def test_list_notes_filters_tag_case_insensitively(tmp_path):
    store = NoteStore(tmp_path)
    store.add("AI 笔记", tags=["AI"], now=datetime(2026, 7, 17, 10, 0, 0))
    store.add("生活笔记", tags=["生活"], now=datetime(2026, 7, 17, 11, 0, 0))

    notes = store.list_notes(tag="ai", limit=3)

    assert [note.title for note in notes] == ["AI 笔记"]


def test_list_notes_uses_id_descending_as_tie_breaker(tmp_path):
    store = NoteStore(tmp_path)
    now = datetime(2026, 7, 17, 10, 0, 0)
    first = store.add("第一篇", now=now)
    second = store.add("第二篇", now=now)

    assert [note.id for note in store.list_notes()] == [second.id, first.id]


@pytest.mark.parametrize("limit", [0, -1, True])
def test_store_rejects_invalid_limit(tmp_path, limit):
    with pytest.raises(ValueError, match="limit 必须是正整数"):
        NoteStore(tmp_path).list_notes(limit=limit)


def test_get_returns_note_and_missing_raises(tmp_path):
    store = NoteStore(tmp_path)
    created = store.add("要显示的笔记", body="正文", now=datetime(2026, 7, 17, 12, 0, 0))

    assert store.get(created.id).body == "正文\n"
    with pytest.raises(NoteNotFoundError, match="n-missing"):
        store.get("n-missing")


@pytest.mark.parametrize(
    ("title", "body", "tags", "keyword"),
    [
        ("MiniMax 配置", "正文", [], "minimax"),
        ("模型配置", "使用 MiniMax API", [], "MINIMAX"),
        ("模型配置", "正文", ["MiniMax"], "minimax"),
    ],
)
def test_search_matches_title_body_and_tags_case_insensitively(
    tmp_path, title, body, tags, keyword
):
    store = NoteStore(tmp_path)
    created = store.add(
        title,
        body=body,
        tags=tags,
        now=datetime(2026, 7, 17, 12, 0, 0),
    )

    assert [note.id for note in store.search(keyword)] == [created.id]


def test_search_rejects_blank_keyword_before_reading_files(tmp_path):
    (tmp_path / "broken.md").write_text("not frontmatter", encoding="utf-8")

    with pytest.raises(ValueError, match="搜索关键词不能为空"):
        NoteStore(tmp_path).search("   ")


@pytest.mark.parametrize(
    "content",
    [
        "plain markdown",
        dump_frontmatter(
            {
                "id": "broken",
                "tags": [],
                "created_at": "2026-07-17T12:00:00",
                "updated_at": "2026-07-17T12:00:00",
            }
        ),
        dump_frontmatter(
            {
                "id": "broken",
                "title": "损坏",
                "tags": [],
                "created_at": "bad-time",
                "updated_at": "bad-time",
            }
        ),
        dump_frontmatter(
            {
                "id": "different-id",
                "title": "损坏",
                "tags": [],
                "created_at": "2026-07-17T12:00:00",
                "updated_at": "2026-07-17T12:00:00",
            }
        ),
    ],
)
def test_list_rejects_corrupt_note_files(tmp_path, content):
    (tmp_path / "broken.md").write_text(content, encoding="utf-8")

    with pytest.raises(NoteDataError, match="broken.md"):
        NoteStore(tmp_path).list_notes()


def test_plugin_add_list_show_and_search(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XCLI_NOTES_DIR", str(tmp_path))

    assert note_plugin.run([
        "add",
        "MiniMax API 配置",
        "--body",
        "这里是正文。",
        "--tags",
        "AI,API,ai",
    ]) == 0
    added = capsys.readouterr()
    assert added.err == ""
    assert "✅ 笔记已创建：MiniMax API 配置（ID: " in added.out
    note_id = next(tmp_path.glob("*.md")).stem

    assert note_plugin.run(["list", "--tag", "ai", "--limit", "1"]) == 0
    listed = capsys.readouterr()
    assert listed.err == ""
    assert "ID" in listed.out and note_id in listed.out
    assert "MiniMax API 配置" in listed.out

    assert note_plugin.run(["show", note_id]) == 0
    shown = capsys.readouterr()
    assert shown.err == ""
    for expected in ("# MiniMax API 配置", f"ID: {note_id}", "Tags: AI, API", "这里是正文。"):
        assert expected in shown.out

    assert note_plugin.run(["search", "minimax", "--limit", "1"]) == 0
    searched = capsys.readouterr()
    assert searched.err == ""
    assert note_id in searched.out


def test_plugin_empty_list(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XCLI_NOTES_DIR", str(tmp_path))
    assert note_plugin.run(["list"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "📭 暂无笔记\n"
    assert captured.err == ""


def test_plugin_blank_title_and_keyword(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XCLI_NOTES_DIR", str(tmp_path))

    assert note_plugin.run(["add", "   "]) == 2
    assert capsys.readouterr().err == "❌ 笔记标题不能为空\n"

    assert note_plugin.run(["search", "   "]) == 2
    assert capsys.readouterr().err == "❌ 搜索关键词不能为空\n"


def test_plugin_show_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XCLI_NOTES_DIR", str(tmp_path))
    assert note_plugin.run(["show", "n-missing"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "❌ 笔记不存在：n-missing\n"


def test_plugin_corrupt_data_returns_five(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XCLI_NOTES_DIR", str(tmp_path))
    (tmp_path / "broken.md").write_text("plain markdown", encoding="utf-8")

    assert note_plugin.run(["list"]) == 5

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("❌ 笔记数据损坏：broken.md（")


@pytest.mark.parametrize("action", ["list", "search"])
@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_plugin_rejects_invalid_limit(action, value):
    args = [action]
    if action == "search":
        args.append("keyword")
    args.extend(["--limit", value])

    with pytest.raises(SystemExit) as exc_info:
        note_plugin.run(args)
    assert exc_info.value.code == 2


def test_note_help_and_top_level_dispatch(capsys):
    assert "note" in SUBCOMMAND_MODULES

    with pytest.raises(SystemExit) as exc_info:
        main(["note", "--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "usage: x note" in output
    for action in ("add", "list", "show", "search"):
        assert action in output
