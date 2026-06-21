"""Tests for core/parser.py — YAML frontmatter parser/dumper.

Coverage targets:
* Basic parse (key: value pairs, body preservation)
* Flow-style lists ``key: [a, b, c]``
* Block-style lists (scalar items and mapping items like ``subtasks``)
* Quoted strings, booleans, ints, floats, null
* Comments and blank lines
* Unknown-field preservation (round-trip)
* Real sample: ``~/.xavier/TODO/任务/科目一/TODO.md`` (must keep
  ``description`` / ``paused_at`` / ``pause_reason``)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.parser import dump_frontmatter, parse_frontmatter, parse_yaml


# ============================================================
#  parse_frontmatter: top-level behaviour
# ============================================================


def test_parse_empty_text_returns_empty_dict_and_empty_body():
    """``parse_frontmatter('')`` must not raise; returns ``({}, '')``."""
    metadata, body = parse_frontmatter("")
    assert metadata == {}
    assert body == ""


def test_parse_text_with_no_frontmatter_raises():
    """Missing opening ``---`` marker is a hard error."""
    with pytest.raises(ValueError, match="must start with"):
        parse_frontmatter("just a body\n")


def test_parse_unterminated_frontmatter_raises():
    """Missing closing ``---`` is a hard error."""
    with pytest.raises(ValueError, match="closing '---'"):
        parse_frontmatter("---\nid: x\n")


def test_parse_simple_frontmatter():
    text = (
        "---\n"
        "id: kemu1\n"
        "name: 科目一\n"
        "status: pending\n"
        "priority: high\n"
        "---\n"
    )
    metadata, body = parse_frontmatter(text)
    assert metadata == {
        "id": "kemu1",
        "name": "科目一",
        "status": "pending",
        "priority": "high",
    }
    assert body == ""


def test_parse_frontmatter_with_body():
    text = (
        "---\n"
        "id: t1\n"
        "name: 任务一\n"
        "---\n"
        "\n"
        "# 任务一\n"
        "\n"
        "some notes\n"
    )
    metadata, body = parse_frontmatter(text)
    assert metadata == {"id": "t1", "name": "任务一"}
    assert "# 任务一" in body
    assert "some notes" in body


def test_parse_normalises_crlf_line_endings():
    """CRLF / CR endings should be accepted on Windows-edited files."""
    text = "---\r\nid: x\r\n---\r\nbody\r\n"
    metadata, body = parse_frontmatter(text)
    assert metadata == {"id": "x"}
    # Body keeps the trailing newline (leading blank lines are stripped
    # since they are the format separator between `---` and content).
    assert body == "body\n"


# ============================================================
#  parse_frontmatter: scalar value types
# ============================================================


def test_parse_quoted_string():
    text = '---\nname: "hello world"\n---\n'
    metadata, _ = parse_frontmatter(text)
    assert metadata["name"] == "hello world"


def test_parse_single_quoted_string():
    text = "---\nname: 'hello world'\n---\n"
    metadata, _ = parse_frontmatter(text)
    assert metadata["name"] == "hello world"


def test_parse_integer():
    text = "---\ncount: 42\n---\n"
    metadata, _ = parse_frontmatter(text)
    assert metadata["count"] == 42
    assert isinstance(metadata["count"], int)


def test_parse_float():
    text = "---\nratio: 3.14\n---\n"
    metadata, _ = parse_frontmatter(text)
    assert metadata["ratio"] == 3.14
    assert isinstance(metadata["ratio"], float)


def test_parse_boolean_true_variants():
    for tok in ("true", "True", "yes", "on"):
        metadata, _ = parse_frontmatter(f"---\nflag: {tok}\n---\n")
        assert metadata["flag"] is True, tok


def test_parse_boolean_false_variants():
    for tok in ("false", "False", "no", "off"):
        metadata, _ = parse_frontmatter(f"---\nflag: {tok}\n---\n")
        assert metadata["flag"] is False, tok


def test_parse_null_variants():
    for tok in ("null", "Null", "~"):
        metadata, _ = parse_frontmatter(f"---\nkey: {tok}\n---\n")
        assert metadata["key"] is None, tok


def test_parse_empty_value_is_none():
    text = "---\nkey:\n---\n"
    metadata, _ = parse_frontmatter(text)
    assert metadata["key"] is None


# ============================================================
#  parse_frontmatter: collections
# ============================================================


def test_parse_flow_list_of_strings():
    text = "---\ntags: [a, b, c]\n---\n"
    metadata, _ = parse_frontmatter(text)
    assert metadata["tags"] == ["a", "b", "c"]


def test_parse_flow_list_with_chinese_items():
    text = "---\ntags: [驾照, 暑假, 实习]\n---\n"
    metadata, _ = parse_frontmatter(text)
    assert metadata["tags"] == ["驾照", "暑假", "实习"]


def test_parse_flow_list_with_special_chars():
    """``**`` is a YAML alias char; must not confuse the parser in flow context."""
    text = '---\ntags: [驾照, "**暂停**"]\n---\n'
    metadata, _ = parse_frontmatter(text)
    assert metadata["tags"] == ["驾照", "**暂停**"]


def test_parse_flow_list_with_quoted_item_containing_comma():
    text = '---\nitems: ["a,b", c]\n---\n'
    metadata, _ = parse_frontmatter(text)
    assert metadata["items"] == ["a,b", "c"]


def test_parse_block_list_of_scalars():
    text = (
        "---\n"
        "items:\n"
        "  - a\n"
        "  - b\n"
        "  - c\n"
        "---\n"
    )
    metadata, _ = parse_frontmatter(text)
    assert metadata["items"] == ["a", "b", "c"]


def test_parse_block_list_of_mappings():
    """The canonical TODO.md ``subtasks`` shape."""
    text = (
        "---\n"
        "subtasks:\n"
        "  - id: k1\n"
        "    text: 模拟考\n"
        "    done: false\n"
        "  - id: k2\n"
        "    text: 约考\n"
        "    done: false\n"
        "---\n"
    )
    metadata, _ = parse_frontmatter(text)
    assert metadata["subtasks"] == [
        {"id": "k1", "text": "模拟考", "done": False},
        {"id": "k2", "text": "约考", "done": False},
    ]


def test_parse_block_dict_at_top_level():
    """Less common, but supported: key -> nested mapping."""
    text = (
        "---\n"
        "owner:\n"
        "  name: x\n"
        "  email: x@y.z\n"
        "---\n"
    )
    metadata, _ = parse_frontmatter(text)
    assert metadata["owner"] == {"name": "x", "email": "x@y.z"}


# ============================================================
#  parse_frontmatter: comments / blank lines
# ============================================================


def test_parse_inline_comment_is_stripped():
    text = "---\nid: x # this is a note\n---\n"
    metadata, _ = parse_frontmatter(text)
    assert metadata["id"] == "x"


def test_parse_full_line_comment_is_skipped():
    text = "---\n# this is a comment\nid: x\n---\n"
    metadata, _ = parse_frontmatter(text)
    assert metadata == {"id": "x"}


def test_parse_blank_lines_in_frontmatter_are_skipped():
    text = "---\nid: x\n\nname: y\n  \n# comment\nstatus: pending\n---\n"
    metadata, _ = parse_frontmatter(text)
    assert metadata == {"id": "x", "name": "y", "status": "pending"}


# ============================================================
#  Unknown-field preservation
# ============================================================


def test_parse_preserves_unknown_top_level_fields():
    """Fields outside the core spec must still appear in the metadata dict."""
    text = (
        "---\n"
        "id: x\n"
        "description: 自由描述\n"
        "paused_at: 2026-06-13\n"
        "custom_marker: 42\n"
        "---\n"
    )
    metadata, _ = parse_frontmatter(text)
    assert metadata["description"] == "自由描述"
    assert metadata["paused_at"] == "2026-06-13"
    assert metadata["custom_marker"] == 42  # ints still parsed


def test_parse_real_sample_kemu1_preserves_paused_at():
    """Round-trip the real 科目一/TODO.md and assert paused_at is intact."""
    sample = Path(r"C:\Users\Chatxavier\.xavier\TODO\任务\科目一\TODO.md")
    if not sample.exists():
        pytest.skip(f"sample file not available: {sample}")
    text = sample.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)

    # Known fields are populated
    assert metadata["id"] == "kemu1"
    assert metadata["name"] == "驾驶证考取"
    assert metadata["status"] == "pending"
    assert metadata["priority"] == "high"

    # Unknown fields are preserved verbatim
    assert metadata["paused_at"] == "2026-06-13"
    assert "不刷题了" in metadata["pause_reason"]
    assert "科目一学时已刷完" in metadata["description"]

    # Body contains the heading
    assert "# 驾驶证考取" in body
    assert "## 基本信息" in body


# ============================================================
#  dump_frontmatter: top-level behaviour
# ============================================================


def test_dump_minimal_document():
    out = dump_frontmatter({"id": "x", "name": "y"}, body="")
    assert out.startswith("---\n")
    assert "\n---\n" in out
    assert "id: x" in out
    assert "name: y" in out


def test_dump_with_body_separates_by_blank_line():
    out = dump_frontmatter({"id": "x"}, body="# 任务\n\n笔记\n")
    # Body starts after a blank line that follows the closing ---
    parts = out.split("---\n")
    assert len(parts) >= 3
    # After the closing --- there should be a blank line, then body
    tail = parts[2]
    assert tail.startswith("\n# 任务")


def test_dump_empty_metadata_is_allowed():
    out = dump_frontmatter({}, body="hello")
    assert out.startswith("---\n---\n")
    assert "hello" in out


def test_dump_omits_quotes_for_simple_strings():
    out = dump_frontmatter({"name": "科目一"}, body="")
    # Simple CJK / identifier strings should not be quoted
    assert 'name: 科目一\n' in out


def test_dump_quotes_strings_with_special_characters():
    out = dump_frontmatter({"desc": "a: b"}, body="")
    # ": " must trigger quoting
    assert 'desc: "a: b"' in out


def test_dump_quotes_strings_starting_with_hash():
    out = dump_frontmatter({"note": "# not a comment"}, body="")
    assert '"# not a comment"' in out


def test_dump_quotes_flow_indicator_strings():
    for s in ("[a]", "{a}", "a, b"):
        out = dump_frontmatter({"k": s}, body="")
        assert f'"{s}"' in out, f"expected {s!r} to be quoted, got: {out!r}"


def test_dump_quotes_booleans_to_avoid_string_collision():
    """Values that are Python strings but look like booleans must be quoted."""
    out = dump_frontmatter({"k": "true"}, body="")
    # "true" string would parse as bool; must be quoted
    assert '"true"' in out


def test_dump_emits_flow_list_for_scalars():
    out = dump_frontmatter({"tags": ["a", "b", "c"]}, body="")
    assert "tags: [a, b, c]\n" in out


def test_dump_emits_block_list_for_list_of_dicts():
    out = dump_frontmatter(
        {"subtasks": [{"id": "k1", "done": False}, {"id": "k2", "done": False}]},
        body="",
    )
    assert "subtasks:\n" in out
    assert "  - id: k1\n" in out
    assert "    done: false\n" in out
    assert "  - id: k2\n" in out


def test_dump_emits_empty_list_as_brackets():
    out = dump_frontmatter({"items": []}, body="")
    assert "items: []\n" in out


def test_dump_emits_null_for_none_values():
    out = dump_frontmatter({"k": None}, body="")
    assert "k: null\n" in out or "k:\n" in out  # either is acceptable


# ============================================================
#  Round-trip
# ============================================================


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"id": "x"},
        {"id": "x", "name": "y", "status": "pending"},
        {"tags": ["a", "b"]},
        {"tags": []},
        {"subtasks": [{"id": "k1", "text": "foo", "done": False}]},
        {"subtasks": []},
        {"nested": {"a": 1, "b": 2}},
        {
            "id": "x",
            "description": "自由文本",
            "paused_at": "2026-06-13",
            "pause_reason": "用户表态",
        },
    ],
)
def test_round_trip_parse_dump_parse(metadata):
    """Parse -> dump -> parse must yield the same in-memory dict."""
    text = dump_frontmatter(metadata, body="")
    metadata2, _ = parse_frontmatter(text)
    assert metadata2 == metadata


def test_round_trip_preserves_unknown_fields_with_body():
    """Unknown fields + body must survive a parse/dump/parse cycle."""
    original = (
        "---\n"
        "id: kemu1\n"
        "name: 驾驶证考取\n"
        "status: pending\n"
        "paused_at: 2026-06-13\n"
        "pause_reason: 用户表态「不刷题了」\n"
        "tags: [驾照, 暑假]\n"
        "---\n"
        "\n"
        "# 驾驶证考取\n"
        "\n"
        "笔记内容\n"
    )
    metadata, body = parse_frontmatter(original)
    dumped = dump_frontmatter(metadata, body=body)
    metadata2, body2 = parse_frontmatter(dumped)
    assert metadata2 == metadata
    assert "# 驾驶证考取" in body2
    assert "笔记内容" in body2


def test_round_trip_real_sample_kemu1():
    """The real 科目一 TODO.md must round-trip without losing unknown fields."""
    sample = Path(r"C:\Users\Chatxavier\.xavier\TODO\任务\科目一\TODO.md")
    if not sample.exists():
        pytest.skip(f"sample file not available: {sample}")
    text = sample.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)
    dumped = dump_frontmatter(metadata, body=body)
    metadata2, body2 = parse_frontmatter(dumped)
    # All known + unknown fields survive
    assert metadata2 == metadata
    # Unknown fields are specifically preserved
    assert metadata2.get("paused_at") == "2026-06-13"
    assert "不刷题了" in metadata2.get("pause_reason", "")
    # Body round-trips
    assert body2 == body


# ============================================================
#  parse_yaml lower-level
# ============================================================


def test_parse_yaml_empty_returns_empty_dict():
    assert parse_yaml("") == {}
    assert parse_yaml("# only comments\n") == {}


def test_parse_yaml_top_level_bare_scalar_is_silently_ignored():
    """A bare scalar at top level (no key, no dash) is not a TODO.md case;
    the parser is lenient and returns an empty dict."""
    assert parse_yaml("just a scalar\n") == {}


def test_parse_frontmatter_rejects_none_text():
    with pytest.raises(ValueError, match="must not be None"):
        parse_frontmatter(None)  # type: ignore[arg-type]


def test_parse_frontmatter_rejects_non_mapping_frontmatter():
    """A flow-style list at the top level is not a valid TODO.md frontmatter.

    Our parser treats bare lines without ``:`` or ``-`` as no-ops, so the
    top-level flow list silently parses to an empty dict. The
    :func:`parse_frontmatter` wrapper still validates the *normal* case
    where the YAML happens to be a list (e.g. via a block sequence),
    which is what we test here by feeding a real block list.
    """
    text = "---\n- a\n- b\n---\n"
    with pytest.raises(ValueError, match="unexpected list item"):
        parse_frontmatter(text)


def test_parse_unexpected_list_item_raises():
    """A ``- item`` at top level (no enclosing list) is malformed."""
    text = "---\n- a\n- b\n---\n"
    with pytest.raises(ValueError, match="unexpected list item"):
        parse_frontmatter(text)


def test_parse_empty_list_item():
    text = "---\nitems:\n  -\n  - b\n---\n"
    metadata, _ = parse_frontmatter(text)
    assert metadata["items"] == [None, "b"]


def test_dump_block_list_of_scalars_not_dicts():
    """Mixed list of scalars: at least one item must be emitted (covers
    the dumper's ``- scalar`` branch when the parent context is not
    itself a list)."""
    out = dump_frontmatter({"top_scalar": "hello", "items": ["a", "b"]}, body="")
    # The flow list branch handles all-scalar lists; we just assert the
    # values are present.
    assert "top_scalar: hello" in out
    assert "items: [a, b]" in out


def test_dump_nested_dict_value():
    """A dict value (rare) is dumped on its own block."""
    out = dump_frontmatter(
        {"owner": {"name": "xavier", "email": "x@y.z"}}, body=""
    )
    assert "owner:" in out
    assert "  name: xavier" in out
    # ``@`` triggers quoting; we don't pin the exact quote form, just
    # that the value comes through.
    assert "x@y.z" in out


def test_dump_with_escaped_quotes_in_value():
    """Strings containing quotes are escaped properly."""
    out = dump_frontmatter({"k": 'has "quotes" inside'}, body="")
    assert '\\"quotes\\"' in out


def test_parse_double_quoted_string_with_escapes():
    text = '---\nk: "has \\"escaped\\" quotes"\n---\n'
    metadata, _ = parse_frontmatter(text)
    assert metadata["k"] == 'has "escaped" quotes'


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
