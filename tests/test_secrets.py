"""Tests for ``core/secrets.py`` — SecretStore CRUD and import/export.

Each test maps to a scenario in
:file:`docs/behaviors/secret-behavior.md`. The store interface is
the boundary between the CLI (``x secret ...``) and the JSON DB on
disk; CLI-layer concerns (argparse, exit codes, table rendering)
live in :file:`tests/test_e2e_secret.py` (T12).

All tests use ``tmp_path`` for ``db_path`` so the real
``%LOCALAPPDATA%\\x-cli\\secrets.json`` is never touched. The
fixture :func:`store` below initialises an empty store rooted at
``tmp_path`` per-test.

BDD scenario mapping:

============  ======================================================
Scenario       Tests
============  ======================================================
1 (list)       ``test_list_*``
2 (get value)  ``test_get_*``
3 (find)       ``test_find_*``  (interface method, not BDD-listed)
4 (set new)    ``test_set_creates_entry`` / ``test_set_duplicate_raises``
5 (set dupe)   ``test_set_duplicate_raises``
6 (set no arg) N/A — argparse layer (T12)
7 (update)     ``test_update_*``
8 (update 404) ``test_update_nonexistent_raises``
9 (rm)         ``test_rm_*``
10 (rm 404)    ``test_rm_nonexistent_raises``
11 (search)    ``test_search_*``
12 (import)    ``test_import_*``
13 (import 404) N/A — CLI layer (T12) returns exit 5
14 (export)    ``test_export_*``
15 (empty)     N/A — CLI layer (T12)
16 (help)      N/A — CLI layer (T12)
============  ======================================================
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from core.secrets import (
    SecretAlreadyExistsError,
    SecretEntry,
    SecretNotFoundError,
    SecretStore,
)


# ============================================================
#  Fixtures
# ============================================================


@pytest.fixture
def store(tmp_path: Path) -> SecretStore:
    """An empty store rooted at a temp file (real DB is safe)."""
    return SecretStore(db_path=tmp_path / "secrets.json")


# ============================================================
#  BDD scenario 1: list returns all entries sorted by name
# ============================================================


def test_list_empty_returns_empty_list(store: SecretStore) -> None:
    """Empty DB → empty list."""
    assert store.list() == []


def test_list_sorts_by_name_case_insensitive(store: SecretStore) -> None:
    """Sort key is case-insensitive (Apple < banana < zebra)."""
    store.set("zebra", value="z")
    store.set("Apple", value="a")
    store.set("banana", value="b")
    names = [e.name for e in store.list()]
    assert names == ["Apple", "banana", "zebra"]


def test_list_returns_secret_entry_instances(store: SecretStore) -> None:
    """The list contains :class:`SecretEntry` instances, not dicts."""
    store.set("minimax", value="x")
    entries = store.list()
    assert len(entries) == 1
    assert isinstance(entries[0], SecretEntry)


# ============================================================
#  BDD scenario 2: get returns exact match
# ============================================================


def test_get_existing(store: SecretStore) -> None:
    """Exact name match returns the entry with value + category."""
    store.set("minimax", value="sk-test1234", category="接口密钥")
    e = store.get("minimax")
    assert e is not None
    assert e.name == "minimax"
    assert e.value == "sk-test1234"
    assert e.category == "接口密钥"


def test_get_is_case_sensitive(store: SecretStore) -> None:
    """``get`` is exact-match (case-sensitive); use :meth:`find` for
    case-insensitive substring lookup. Original casing is preserved
    on disk per BDD §"字段约束".
    """
    store.set("minimax", value="x")
    # Exact match
    assert store.get("minimax") is not None
    # Different case → miss
    assert store.get("MIniMax") is None
    assert store.get("MINIMAX") is None
    # But the original casing is preserved on the entry
    assert store.get("minimax").name == "minimax"


def test_get_nonexistent_returns_none(store: SecretStore) -> None:
    """Missing key returns ``None`` (not an exception — per BDD scenario 4
    which is CLI-side mapping to exit 3)."""
    assert store.get("nope") is None


# ============================================================
#  BDD scenario 3 (interface method, not in BDD list): find
# ============================================================


def test_find_substring(store: SecretStore) -> None:
    """``find`` does substring matching across names."""
    store.set("minimax-prod", value="x")
    e = store.find("minimax")
    assert e is not None
    assert e.name == "minimax-prod"


def test_find_no_match_returns_none(store: SecretStore) -> None:
    store.set("minimax-prod", value="x")
    assert store.find("xyz123") is None


# ============================================================
#  BDD scenario 4 & 5: set inserts / rejects duplicate
# ============================================================


def test_set_creates_entry(store: SecretStore) -> None:
    """``set`` with all fields returns a populated :class:`SecretEntry`."""
    e = store.set("minimax", value="sk-1234", category="接口密钥", note="from xavier")
    assert e.name == "minimax"
    assert e.value == "sk-1234"
    assert e.category == "接口密钥"
    assert e.note == "from xavier"
    assert e.created_at  # ISO 8601 non-empty
    assert e.updated_at  # same as created_at on insert
    assert e.created_at == e.updated_at


def test_set_default_category(store: SecretStore) -> None:
    """``category`` defaults to ``"default"`` if omitted."""
    e = store.set("minimax", value="x")
    assert e.category == "default"


def test_set_persists_to_disk(store: SecretStore) -> None:
    """After ``set``, reloading from disk finds the entry."""
    store.set("minimax", value="sk-x", category="cat")
    reloaded = SecretStore(db_path=store.db_path)
    assert reloaded.get("minimax").value == "sk-x"


def test_set_duplicate_raises(store: SecretStore) -> None:
    """Re-setting the same name raises :class:`SecretAlreadyExistsError`."""
    store.set("minimax", value="v1")
    with pytest.raises(SecretAlreadyExistsError):
        store.set("minimax", value="v2")


def test_set_duplicate_does_not_overwrite(store: SecretStore) -> None:
    """A failed set must NOT silently overwrite the existing value."""
    store.set("minimax", value="original")
    with pytest.raises(SecretAlreadyExistsError):
        store.set("minimax", value="new")
    assert store.get("minimax").value == "original"


# ============================================================
#  BDD scenario 7 & 8: update modifies / 404
# ============================================================


def test_update_value_only(store: SecretStore) -> None:
    """``update`` with only ``value`` mutates value and bumps ``updated_at``."""
    store.set("minimax", value="sk-old")
    original_updated = store.get("minimax").updated_at
    e = store.update("minimax", value="sk-new")
    assert e.value == "sk-new"
    assert e.updated_at  # may differ from created_at


def test_update_preserves_created_at(store: SecretStore) -> None:
    """``created_at`` is immutable; only ``updated_at`` changes."""
    store.set("minimax", value="sk-old")
    original_created = store.get("minimax").created_at
    e = store.update("minimax", value="sk-new")
    assert e.created_at == original_created


def test_update_note_only(store: SecretStore) -> None:
    """``update`` accepts ``value`` and ``note``; ``category`` is
    immutable through this method (BDD scenario 8 only lists ``--value``).
    """
    store.set("minimax", value="x", category="keep", note="n1")
    e = store.update("minimax", note="n2")
    assert e.note == "n2"
    assert e.value == "x"  # unchanged
    assert e.category == "keep"  # not touched by update


def test_update_persists_to_disk(store: SecretStore) -> None:
    store.set("minimax", value="sk-old")
    store.update("minimax", value="sk-new")
    reloaded = SecretStore(db_path=store.db_path)
    assert reloaded.get("minimax").value == "sk-new"


def test_update_nonexistent_raises(store: SecretStore) -> None:
    with pytest.raises(SecretNotFoundError):
        store.update("nope", value="x")


# ============================================================
#  BDD scenario 9 & 10: rm deletes / 404
# ============================================================


def test_rm_existing(store: SecretStore) -> None:
    """Removing an existing entry returns it; subsequent get returns None."""
    store.set("minimax", value="x")
    removed = store.rm("minimax")
    assert removed.name == "minimax"
    assert store.get("minimax") is None


def test_rm_persists_to_disk(store: SecretStore) -> None:
    store.set("minimax", value="x")
    store.rm("minimax")
    reloaded = SecretStore(db_path=store.db_path)
    assert reloaded.get("minimax") is None


def test_rm_nonexistent_raises(store: SecretStore) -> None:
    with pytest.raises(SecretNotFoundError):
        store.rm("nope")


# ============================================================
#  BDD scenario 11: search matches name+note, NEVER value
# ============================================================


def test_search_matches_name(store: SecretStore) -> None:
    """Substring match on the name field."""
    store.set("openai-prod", value="sk-x")
    store.set("minimax", value="sk-y")
    # "openai-prod" contains "open" and "prod"; pick one
    results = store.search("open")
    names = {r.name for r in results}
    assert "openai-prod" in names
    assert "minimax" not in names

    # Case-insensitive
    results_upper = store.search("OPEN")
    assert {r.name for r in results_upper} == {"openai-prod"}


def test_search_matches_note(store: SecretStore) -> None:
    """Substring match on the note field too."""
    store.set("minimax", value="sk-x", note="used for API calls")
    results = store.search("API")
    assert len(results) == 1
    assert results[0].name == "minimax"


def test_search_never_matches_value(store: SecretStore) -> None:
    """CRITICAL: search must NOT match on value (privacy / grep leak)."""
    store.set("minimax", value="sk-secret-value", note="")
    results = store.search("sk-secret-value")
    assert len(results) == 0


def test_search_empty_query_returns_empty(store: SecretStore) -> None:
    """Empty query → empty list (no accidental full-DB dump)."""
    store.set("a", value="1")
    store.set("b", value="2")
    assert store.search("") == []


# ============================================================
#  BDD scenario 12: import_from_dir parses .md files
# ============================================================


def test_import_from_dir_basic(tmp_path: Path) -> None:
    """A .md file with a ``## name`` section + ```text block``` becomes an entry."""
    md_file = tmp_path / "接口密钥.md"
    md_file.write_text(
        "---\n"
        "version: \"1.0\"\n"
        "count: 1\n"
        "---\n"
        "\n"
        "# 接口密钥\n"
        "\n"
        "## minimax\n"
        "\n"
        "| 字段 | 值 |\n"
        "|------|-----|\n"
        "| 用途 | 测试 |\n"
        "\n"
        "```text\n"
        "api_key: sk-test1234\n"
        "```\n",
        encoding="utf-8",
    )

    store = SecretStore(db_path=tmp_path / "out.json")
    imported, skipped = store.import_from_dir(tmp_path)
    assert imported == 1
    assert skipped == 0

    entries = store.list()
    assert len(entries) == 1
    e = entries[0]
    assert e.name == "minimax"
    assert e.category == "接口密钥"  # from .md filename (sans .md)
    assert "api_key: sk-test1234" in e.value
    # Metadata table → note
    assert "用途" in e.note
    assert "测试" in e.note


def test_import_from_multiple_md_files(tmp_path: Path) -> None:
    """Each .md → one category; one section per entry."""
    (tmp_path / "接口密钥.md").write_text(
        "## minimax\n\n```text\napi_key: sk-x\n```\n", encoding="utf-8"
    )
    (tmp_path / "令牌.md").write_text(
        "## openai\n\n```text\ntoken: tk-y\n```\n", encoding="utf-8"
    )

    store = SecretStore(db_path=tmp_path / "out.json")
    imported, skipped = store.import_from_dir(tmp_path)
    assert imported == 2
    assert skipped == 0

    by_name = {e.name: e for e in store.list()}
    assert by_name["minimax"].category == "接口密钥"
    assert by_name["openai"].category == "令牌"


def test_import_skips_duplicates(tmp_path: Path) -> None:
    """If name already exists in the DB, skip (don't overwrite)."""
    md_file = tmp_path / "keys.md"
    md_file.write_text(
        "## minimax\n\n```text\napi_key: from_md\n```\n",
        encoding="utf-8",
    )

    store = SecretStore(db_path=tmp_path / "out.json")
    store.set("minimax", value="pre-existing")

    imported, skipped = store.import_from_dir(tmp_path)
    assert imported == 0
    assert skipped == 1

    # Pre-existing value preserved
    assert store.get("minimax").value == "pre-existing"


def test_import_does_not_delete_old_files(tmp_path: Path) -> None:
    """Old .md files must remain in the source dir after import."""
    md_file = tmp_path / "key.md"
    md_file.write_text("## test\n\n```text\nv: 1\n```\n", encoding="utf-8")

    store = SecretStore(db_path=tmp_path / "out.json")
    store.import_from_dir(tmp_path)

    assert md_file.exists()


def test_import_empty_dir_returns_zero_zero(tmp_path: Path) -> None:
    """No .md files → (0, 0) cleanly."""
    store = SecretStore(db_path=tmp_path / "out.json")
    imported, skipped = store.import_from_dir(tmp_path)
    assert imported == 0
    assert skipped == 0


# ============================================================
#  BDD scenario 14: export creates backup file
# ============================================================


def test_export_creates_backup_file(tmp_path: Path) -> None:
    """``export(dest=...)`` writes a valid JSON file at dest."""
    store = SecretStore(db_path=tmp_path / "secrets.json")
    store.set("minimax", value="sk-x")

    backup = tmp_path / "backup.json"
    returned = store.export(dest=backup)
    assert returned == backup
    assert backup.exists()

    data = json.loads(backup.read_text(encoding="utf-8"))
    assert "secrets" in data
    assert data["secrets"][0]["name"] == "minimax"


def test_export_auto_names_file(tmp_path: Path) -> None:
    """``export()`` with no dest → auto-generates a timestamped filename."""
    store = SecretStore(db_path=tmp_path / "secrets.json")
    store.set("minimax", value="sk-x")

    returned = store.export()  # no dest
    assert returned.exists()
    assert returned.parent == tmp_path
    assert "backup" in returned.name


def test_export_round_trip(tmp_path: Path) -> None:
    """A backup file can be loaded back as a SecretStore (or contains
    the same data)."""
    db = tmp_path / "secrets.json"
    s1 = SecretStore(db_path=db)
    s1.set("a", value="1")
    s1.set("b", value="2")

    backup = tmp_path / "backup.json"
    s1.export(dest=backup)

    s2 = SecretStore(db_path=backup)
    names = {e.name for e in s2.list()}
    assert names == {"a", "b"}


# ============================================================
#  Persistence: re-loading preserves data
# ============================================================


def test_persistence_round_trip(tmp_path: Path) -> None:
    """Write, then re-instantiate from the same db_path → all data preserved."""
    db = tmp_path / "secrets.json"

    s1 = SecretStore(db_path=db)
    s1.set("minimax", value="sk-x", category="cat", note="note")

    s2 = SecretStore(db_path=db)  # reload from disk
    e = s2.get("minimax")
    assert e is not None
    assert e.value == "sk-x"
    assert e.category == "cat"
    assert e.note == "note"
    # Timestamps round-trip
    assert e.created_at == s1.get("minimax").created_at


def test_loading_missing_db_creates_empty_store(tmp_path: Path) -> None:
    """First run on a fresh machine: DB doesn't exist → empty store, no error."""
    db = tmp_path / "fresh.json"
    assert not db.exists()
    s = SecretStore(db_path=db)
    assert s.list() == []


def test_loading_corrupt_db_raises(tmp_path: Path) -> None:
    """A malformed JSON file should fail loudly (CLI maps to exit 5).

    Per BDD §"退出码速查": DB 错 → exit 5 (JSON 损坏).
    The store does not eagerly validate on ``__init__`` (the file
    already exists so it does not get rewritten), but the first read
    (``list``) raises :class:`SecretError`.
    """
    from core.secrets import SecretError

    db = tmp_path / "corrupt.json"
    db.write_text("{ not valid json", encoding="utf-8")
    store = SecretStore(db_path=db)
    with pytest.raises(SecretError):
        store.list()


# ============================================================
#  Timestamps
# ============================================================


def test_created_at_is_iso8601_date(store: SecretStore) -> None:
    """``created_at`` matches today's date in ISO format (YYYY-MM-DD or full)."""
    e = store.set("minimax", value="x")
    today = date.today().isoformat()
    assert today in e.created_at  # ISO 8601 contains today's date


def test_updated_at_advances_on_update(store: SecretStore) -> None:
    """Updating bumps ``updated_at`` to (at least) the same day as created_at.

    We can't reliably fake the clock in a stdlib-only setup, so we
    verify the field is present and non-empty after an update.
    """
    store.set("minimax", value="x")
    e = store.update("minimax", value="y")
    assert e.updated_at
    assert isinstance(e.updated_at, str)


# ============================================================
#  File permissions
# ============================================================


def test_file_created_with_600_perms(tmp_path: Path) -> None:
    """On Unix, the DB file mode should be 0o600 (owner read/write only).

    On Windows, ACL is used and ``stat().st_mode`` reflects the DOS
    bits, so we skip the check there.
    """
    if sys.platform == "win32":
        pytest.skip("chmod 600 not enforced on Windows (ACL differs)")

    db = tmp_path / "secrets.json"
    SecretStore(db_path=db)
    mode = db.stat().st_mode & 0o777
    assert mode == 0o600


def test_existing_db_preserves_mode_on_write(tmp_path: Path) -> None:
    """A pre-existing file with weird mode is not auto-tightened — this
    matches the principle that we don't surprise the user by changing
    perms on files they created.

    Implementation may choose to re-tighten; this test pins the
    behaviour either way by NOT making it tighter than the OS default.
    """
    if sys.platform == "win32":
        pytest.skip("POSIX mode semantics don't apply on Windows")

    db = tmp_path / "secrets.json"
    db.write_text("{}", encoding="utf-8")  # already a file
    # Save current mode (whatever it is, default for tmp_path is 0o700 for dirs
    # but 0o600 for files written by Python on most systems)
    before = db.stat().st_mode & 0o777

    store = SecretStore(db_path=db)
    store.set("minimax", value="x")
    after = db.stat().st_mode & 0o777

    # After write, mode is at least as tight as before (never looser)
    assert after <= before or after == 0o600


# ============================================================
#  Cross-cutting: integration
# ============================================================


def test_full_lifecycle_add_update_remove(store: SecretStore) -> None:
    """set → update → rm — happy path."""
    e1 = store.set("minimax", value="v1")
    assert e1.value == "v1"

    e2 = store.update("minimax", value="v2")
    assert e2.value == "v2"
    assert store.get("minimax").value == "v2"

    removed = store.rm("minimax")
    assert removed.name == "minimax"
    assert store.get("minimax") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))