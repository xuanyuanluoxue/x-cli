"""Tests for ``x diary`` P0.

BDD: :mod:`docs.behaviors.diary-behavior`.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from core.diary import DiaryStore
from core.dispatch import SUBCOMMAND_MODULES
from core.paths import xcli_diary_dir
from plugins import diary as diary_plugin
from x import main


def test_diary_path_defaults_under_xcli_data_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("XCLI_DIARY_DIR", raising=False)
    if __import__("sys").platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    result = xcli_diary_dir()

    assert result == tmp_path / "x-cli" / "diary"
    assert result.is_dir()


def test_diary_path_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "my-diary"
    monkeypatch.setenv("XCLI_DIARY_DIR", str(custom))

    result = xcli_diary_dir()

    assert result == custom
    assert result.is_dir()


def test_append_creates_todays_markdown_file(tmp_path):
    store = DiaryStore(tmp_path)

    path = store.append(
        "今天开始开发 x diary",
        now=datetime(2026, 7, 17, 14, 30),
    )

    assert path == tmp_path / "2026-07-17.md"
    assert path.read_text(encoding="utf-8") == (
        "# 2026-07-17\n\n- 14:30 今天开始开发 x diary\n"
    )


def test_append_preserves_existing_entry_and_single_heading(tmp_path):
    store = DiaryStore(tmp_path)
    store.append("第一条", now=datetime(2026, 7, 17, 9, 5))

    path = store.append("第二条", now=datetime(2026, 7, 17, 20, 45))

    text = path.read_text(encoding="utf-8")
    assert text == "# 2026-07-17\n\n- 09:05 第一条\n- 20:45 第二条\n"
    assert text.count("# 2026-07-17") == 1


def test_append_indents_multiline_content(tmp_path):
    store = DiaryStore(tmp_path)

    path = store.append(
        "第一行\r\n第二行\n第三行",
        now=datetime(2026, 7, 17, 8, 0),
    )

    assert path.read_text(encoding="utf-8").endswith(
        "- 08:00 第一行\n  第二行\n  第三行\n"
    )


@pytest.mark.parametrize("content", ["", "   ", "\t\r\n"])
def test_append_rejects_blank_content_without_creating_file(tmp_path, content):
    store = DiaryStore(tmp_path)

    with pytest.raises(ValueError, match="日记内容不能为空"):
        store.append(content, now=datetime(2026, 7, 17, 14, 30))

    assert list(tmp_path.glob("*.md")) == []


def test_list_dates_returns_latest_valid_dates_descending(tmp_path):
    for name in (
        "2026-07-01.md",
        "2026-07-05.md",
        "2026-07-03.md",
        "2026-02-30.md",
        "notes.md",
    ):
        (tmp_path / name).write_text("test", encoding="utf-8")
    (tmp_path / "2026-07-09.md").mkdir()

    result = DiaryStore(tmp_path).list_dates(limit=2)

    assert result == [date(2026, 7, 5), date(2026, 7, 3)]


def test_list_dates_defaults_to_seven(tmp_path):
    for day in range(1, 10):
        (tmp_path / f"2026-07-{day:02d}.md").write_text("test", encoding="utf-8")

    result = DiaryStore(tmp_path).list_dates()

    assert result == [date(2026, 7, day) for day in range(9, 2, -1)]


@pytest.mark.parametrize("limit", [0, -1])
def test_list_dates_rejects_non_positive_limit(tmp_path, limit):
    with pytest.raises(ValueError, match="limit 必须是正整数"):
        DiaryStore(tmp_path).list_dates(limit=limit)


def test_plugin_write_and_list(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XCLI_DIARY_DIR", str(tmp_path))

    assert diary_plugin.run(["从 CLI 写入"]) == 0
    write_output = capsys.readouterr()
    assert write_output.err == ""
    assert "✅ 日记已写入：" in write_output.out

    assert diary_plugin.run(["list", "--limit", "1"]) == 0
    list_output = capsys.readouterr()
    assert list_output.err == ""
    assert "最近 1 个日记日期：" in list_output.out
    assert datetime.now().date().isoformat() in list_output.out


def test_plugin_rejects_blank_content(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XCLI_DIARY_DIR", str(tmp_path))

    assert diary_plugin.run(["   "]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "❌ 日记内容不能为空\n"
    assert list(tmp_path.glob("*.md")) == []


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_plugin_rejects_invalid_limit(value):
    with pytest.raises(SystemExit) as exc_info:
        diary_plugin.run(["list", "--limit", value])
    assert exc_info.value.code == 2


def test_plugin_lists_empty_store(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("XCLI_DIARY_DIR", str(tmp_path))

    assert diary_plugin.run(["list"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "📭 暂无日记\n"
    assert captured.err == ""


def test_diary_help_and_top_level_dispatch(capsys):
    assert "diary" in SUBCOMMAND_MODULES

    with pytest.raises(SystemExit) as exc_info:
        main(["diary", "--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "usage: x diary" in output
    assert "list" in output
    assert "--limit" in output
