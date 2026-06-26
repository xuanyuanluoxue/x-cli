"""core/secrets.py — JSON-backed credential store for ``x secret``.

This module is the data layer behind the ``x secret`` subcommand. It
owns a single JSON file (default: ``<xcli_data_dir>/secrets.json``,
overridable via :envvar:`XCLI_SECRETS_DIR`) and exposes a small
CRUD surface: :meth:`SecretStore.list`, :meth:`SecretStore.get`,
:meth:`SecretStore.set`, :meth:`SecretStore.update`,
:meth:`SecretStore.rm`, plus helpers for fuzzy lookup, search,
migration from the legacy ``~/.xavier/密钥/*.md`` directory, and
JSON export for backups.

Design constraints (per ``docs/behaviors/secret-behavior.md`` and
``docs/architecture.md`` §11):

* **Stdlib-only** — ``json``, ``pathlib``, ``os``, ``datetime``,
  ``dataclasses``. No third-party deps.
* **File permissions** — ``os.chmod(path, 0o600)`` is called on
  creation. On Windows this is a no-op (ACLs are not modified); the
  limitation is documented in a comment near :meth:`SecretStore._init_db`.
* **MVP has no encryption** — values are stored in plaintext. The
  :envvar:`XCLI_SECRETS_DIR` override plus 600 permissions are the
  only OS-level protection.
* **Atomicity** — writes go through a temp file + ``os.replace`` so
  a crash mid-write cannot corrupt the DB.

The module is independent of the legacy ``~/.xavier/密钥/`` layout
on purpose: ``x secret`` is a generic CLI tool, not a wrapper around
xavier's personal data directory.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.paths import xcli_secrets_path


# ============================================================
#  Constants
# ============================================================


DB_VERSION = "1.0"

# A ``## <title>`` heading at the start of a line. Anchored to the
# start of line so it does not match ``### `` (deeper headings).
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")

# A fenced code block. We capture the language tag and the body so
# the MD importer can pick out ``text`` blocks while ignoring others.
_FENCE_RE = re.compile(
    r"^```(\S+)?\s*$", re.MULTILINE
)

# A pipe-delimited table row: ``| 字段 | 值 |`` (or ``|------|---|``).
_TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*$")

# A separator row: ``|------|------|`` (or any dash-only cells).
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|\s*$")


# ============================================================
#  Exceptions
# ============================================================


class SecretError(Exception):
    """Base class for all :class:`SecretStore` errors."""


class SecretNotFoundError(SecretError, LookupError):
    """Raised when looking up a secret name that does not exist."""

    def __init__(self, name: str) -> None:
        super().__init__(f"secret not found: {name}")
        self.name = name


class SecretAlreadyExistsError(SecretError, ValueError):
    """Raised when inserting a secret whose name already exists."""

    def __init__(self, name: str) -> None:
        super().__init__(f"secret already exists: {name}")
        self.name = name


# ============================================================
#  Data model
# ============================================================


@dataclass
class SecretEntry:
    """In-memory representation of one credential.

    Attributes
    ----------
    name:
        Unique identifier (1-64 chars). Comparison is case-insensitive
        but the original casing is preserved on round-trip.
    category:
        Free-form label (default ``"default"``). The ``x secret import``
        command fills this with the source ``.md`` filename (without
        the ``.md`` extension).
    value:
        The credential itself. May contain newlines (multi-line
        ``key: value`` blocks).
    note:
        Optional free-form annotation. The ``import`` command packs
        the source section's metadata table into this field as one
        ``key: value`` line per row.
    created_at, updated_at:
        ISO 8601 timestamps. ``set`` populates both with the same
        value; ``update`` only refreshes ``updated_at`` and leaves
        ``created_at`` alone.
    """

    name: str
    category: str = "default"
    value: str = ""
    note: str = ""
    created_at: str = ""
    updated_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    # --------------------------------------------------------
    #  Serialisation
    # --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dict for this entry.

        ``extra`` is flattened in (top-level keys) so the on-disk
        shape is flat — easier for humans to diff and edit by hand.
        """
        data = asdict(self)
        # ``asdict`` would also serialise ``extra`` under its own key.
        # We want the extra fields to be siblings of the known ones.
        extra = data.pop("extra", {}) or {}
        merged: dict[str, Any] = {}
        # Known fields first (stable order), then extras.
        for key in (
            "name",
            "category",
            "value",
            "note",
            "created_at",
            "updated_at",
        ):
            if key in data:
                merged[key] = data[key]
        for key, value in extra.items():
            merged[key] = value
        return merged

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SecretEntry":
        """Build a :class:`SecretEntry` from a JSON dict.

        Unknown keys land in :attr:`extra` so future schema additions
        do not silently drop user metadata.
        """
        known = {
            "name",
            "category",
            "value",
            "note",
            "created_at",
            "updated_at",
        }
        kwargs: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for key, value in d.items():
            if key in known:
                kwargs[key] = value
            else:
                extra[key] = value
        return cls(extra=extra, **kwargs)


# ============================================================
#  SecretStore
# ============================================================


class SecretStore:
    """JSON-backed CRUD layer for the ``x secret`` subcommand.

    Parameters
    ----------
    db_path:
        Explicit path to the secrets JSON file. When ``None`` (the
        default), the constructor falls back to
        :func:`core.paths.xcli_secrets_path`, which honours the
        :envvar:`XCLI_SECRETS_DIR` override and the per-platform
        default. Tests should pass a ``tmp_path`` here (or set the
        env var) so the real ``%LOCALAPPDATA%\\x-cli\\secrets.json``
        is never touched.

    Notes
    -----
    The store is **single-process-safe** for create/update/delete
    via the temp-file + ``os.replace`` write strategy, but does not
    implement file locking. Concurrent writes from multiple
    processes may clobber each other — acceptable for a personal
    CLI tool but worth knowing.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            self.db_path: Path = xcli_secrets_path()
        else:
            self.db_path = Path(db_path)
        self._init_db()

    # --------------------------------------------------------
    #  Internal: DB lifecycle
    # --------------------------------------------------------

    def _init_db(self) -> None:
        """Create the DB file with an empty secrets list if missing.

        Sets file permissions to ``0o600`` (owner read/write only).
        On Windows ``os.chmod`` is effectively a no-op; the OS still
        applies DACLs based on the creating user, but the call is
        kept for cross-platform parity (and to make the intent
        explicit to readers of the code).

        The on-disk file is **not** validated here; corruption is
        detected lazily on the first read (e.g. via :meth:`list`),
        which raises :class:`SecretError`. This avoids forcing a
        read on every ``SecretStore()`` construction (the typical
        single-op CLI invocation).
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            self._write_raw({"version": DB_VERSION, "secrets": []})
            return
        # File already exists — still try to tighten permissions.
        # We do this lazily: only on first construction, and only if
        # the file is currently readable by the group/others.
        try:
            mode = self.db_path.stat().st_mode
            if mode & 0o077:
                os.chmod(self.db_path, 0o600)
        except OSError:
            # Windows: chmod may fail; safe to ignore.
            pass

    def _load(self) -> list[dict[str, Any]]:
        """Read the secrets list from disk. Returns ``[]`` if empty."""
        text = self.db_path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SecretError(
                f"secrets DB is corrupt ({self.db_path}): {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise SecretError(
                f"secrets DB has unexpected shape: top-level must be an object"
            )
        secrets = data.get("secrets", [])
        if not isinstance(secrets, list):
            raise SecretError(
                f"secrets DB has unexpected shape: 'secrets' must be a list"
            )
        return secrets

    def _save(self, secrets: list[dict[str, Any]]) -> None:
        """Persist the secrets list to disk (atomic via temp file)."""
        payload = {"version": DB_VERSION, "secrets": secrets}
        self._write_raw(payload)

    def _write_raw(self, payload: dict[str, Any]) -> None:
        """Write ``payload`` to ``self.db_path`` with 0600 permissions."""
        tmp_path = self.db_path.with_suffix(self.db_path.suffix + ".tmp")
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        tmp_path.write_text(text, encoding="utf-8")
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            # Windows: chmod is a no-op for normal users; safe to ignore.
            pass
        os.replace(tmp_path, self.db_path)

    def _now(self) -> str:
        """Return the current local time as an ISO 8601 string."""
        return datetime.now().replace(microsecond=0).isoformat()

    # --------------------------------------------------------
    #  Read paths
    # --------------------------------------------------------

    def list(self, category: str | None = None) -> list[SecretEntry]:
        """Return all entries, sorted by ``name`` (case-insensitive).

        Parameters
        ----------
        category:
            When provided, only return entries whose ``category``
            matches (case-insensitive). When ``None`` (the default),
            return all entries.
        """
        raw = self._load()
        entries = [SecretEntry.from_dict(d) for d in raw]
        if category is not None:
            needle = category.casefold()
            entries = [e for e in entries if e.category.casefold() == needle]
        entries.sort(key=lambda e: e.name.casefold())
        return entries

    def get(self, name: str) -> SecretEntry | None:
        """Look up an entry by exact name. Returns ``None`` if not found.

        ``get`` is case-sensitive; case-insensitive substring lookup
        is provided by :meth:`find`. Original casing is preserved
        on disk per BDD §"字段约束".
        """
        if not name:
            return None
        for d in self._load():
            if d.get("name") == name:
                return SecretEntry.from_dict(d)
        return None

    def find(self, name: str) -> SecretEntry | None:
        """Return the first entry whose name contains ``name`` (case-insensitive).

        Used by ``x secret get <name>`` to support partial matches
        (per ``secret-behavior.md`` scenario 3). Returns ``None`` when
        no entry matches.
        """
        if not name:
            return None
        needle = name.casefold()
        for d in self._load():
            candidate = d.get("name", "")
            if needle in candidate.casefold():
                return SecretEntry.from_dict(d)
        return None

    def search(self, keyword: str) -> list[SecretEntry]:
        """Return entries whose ``name`` or ``note`` matches ``keyword``.

        Matching is case-insensitive and **lenient**: an entry is a
        match when either

        1. ``keyword`` is a substring of the name or note, **or**
        2. every character of ``keyword`` appears in the name or
           note (loose, order-independent — for the "fuzzy" use case
           like searching ``api`` and finding ``openai-prod``).

        The ``value`` field is **deliberately excluded** from the
        search space (per ``secret-behavior.md`` scenario 12 — we
        never want a casual ``x secret search api`` to leak a real
        credential through a value match).

        Empty ``keyword`` returns ``[]`` (no accidental full-DB
        dump via ``x secret search`` with no args). The result is
        sorted by name (case-insensitive), mirroring :meth:`list`.
        """
        if not keyword:
            return []
        needle = keyword.casefold()
        results: list[SecretEntry] = []
        for d in self._load():
            name = d.get("name", "")
            note = d.get("note", "")
            name_lc = name.casefold()
            note_lc = note.casefold()
            if (
                needle in name_lc
                or needle in note_lc
                or (needle and all(c in name_lc for c in needle))
                or (needle and all(c in note_lc for c in needle))
            ):
                results.append(SecretEntry.from_dict(d))
        results.sort(key=lambda e: e.name.casefold())
        return results

    # --------------------------------------------------------
    #  Write paths
    # --------------------------------------------------------

    def set(
        self,
        name: str,
        value: str,
        category: str = "default",
        note: str = "",
    ) -> SecretEntry:
        """Insert a brand-new secret.

        Raises
        ------
        SecretAlreadyExistsError
            If an entry with the same ``name`` already exists. Use
            :meth:`update` to modify an existing entry.
        """
        if not name:
            raise ValueError("secret name is required")
        if self.get(name) is not None:
            raise SecretAlreadyExistsError(name)
        now = self._now()
        entry = SecretEntry(
            name=name,
            category=category or "default",
            value=value,
            note=note,
            created_at=now,
            updated_at=now,
        )
        self._save(self._load() + [entry.to_dict()])
        return entry

    def update(
        self,
        name: str,
        value: str | None = None,
        note: str | None = None,
        category: str | None = None,
    ) -> SecretEntry:
        """Update ``value`` and/or ``note`` and/or ``category`` on an existing entry.

        Only fields whose argument is not ``None`` are mutated. The
        ``created_at`` timestamp is preserved; ``updated_at`` is
        refreshed to the current time. Lookup is case-sensitive —
        use the exact name you got from :meth:`get` or
        :meth:`list`.

        Raises
        ------
        SecretNotFoundError
            If no entry with the given ``name`` exists.
        """
        rows = self._load()
        for i, d in enumerate(rows):
            if d.get("name") == name:
                if value is not None:
                    d["value"] = value
                if note is not None:
                    d["note"] = note
                if category is not None:
                    d["category"] = category
                d["updated_at"] = self._now()
                rows[i] = d
                self._save(rows)
                return SecretEntry.from_dict(d)
        raise SecretNotFoundError(name)

    def rm(self, name: str) -> SecretEntry:
        """Delete the entry with the given name.

        Returns the removed entry (useful for "undo" UIs / confirmation
        messages). Lookup is case-sensitive — pass the exact name
        you got from :meth:`get` or :meth:`list`. Raises
        :class:`SecretNotFoundError` if the entry does not exist.
        """
        rows = self._load()
        for i, d in enumerate(rows):
            if d.get("name") == name:
                rows.pop(i)
                self._save(rows)
                return SecretEntry.from_dict(d)
        raise SecretNotFoundError(name)

    # --------------------------------------------------------
    #  Migration & backup
    # --------------------------------------------------------

    def import_from_dir(self, src_dir: Path) -> tuple[int, int]:
        """Migrate credentials from a directory of ``.md`` files.

        The expected on-disk shape is documented in
        ``docs/behaviors/secret-behavior.md`` scenario 13 and
        ``docs/architecture.md`` §11.5: each ``.md`` file contains
        one or more ``## <title>`` sections, each with a metadata
        table and a ``text``-fenced code block.

        Returns
        -------
        (imported, skipped)
            ``imported`` is the number of new entries added;
            ``skipped`` is the number of ``## <title>`` sections
            that were ignored (because the name already exists in
            the DB, or because the section has no ``text`` block).
            Old ``.md`` files are never deleted.

        Raises
        ------
        FileNotFoundError
            If ``src_dir`` does not exist.
        """
        src_dir = Path(src_dir)
        if not src_dir.is_dir():
            raise FileNotFoundError(f"source directory not found: {src_dir}")

        rows = self._load()
        existing_names = {d.get("name") for d in rows}
        imported = 0
        skipped = 0

        for md_path in sorted(src_dir.glob("*.md")):
            # Skip README / index files (they document the format, not real secrets).
            if md_path.stem.lower() in {"readme", "index", "模板"}:
                continue
            category = md_path.stem
            text = md_path.read_text(encoding="utf-8")
            for entry in _parse_markdown_sections(text, category):
                if entry.name in existing_names:
                    skipped += 1
                    continue
                # Stamp the import time so the row has a usable updated_at for `list`.
                now = self._now()
                entry.created_at = now
                entry.updated_at = now
                rows.append(entry.to_dict())
                existing_names.add(entry.name)
                imported += 1

        if imported:
            self._save(rows)
        return imported, skipped

    def export(self, dest: Path | None = None) -> Path:
        """Write the current DB to ``dest`` (or an auto-named backup file).

        Parameters
        ----------
        dest:
            Target path. When ``None``, the store writes a
            timestamped backup file alongside the DB:
            ``<db_dir>/secrets-backup-YYYYMMDD-HHMMSS.json``.

        Returns
        -------
        Path
            Absolute path to the file that was written.
        """
        if dest is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = self.db_path.parent / f"secrets-backup-{stamp}.json"
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Re-use the same atomic-write strategy as the live DB.
        rows = self._load()
        payload = {"version": DB_VERSION, "secrets": rows}
        tmp_path = dest.with_suffix(dest.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, dest)
        return dest


# ============================================================
#  MD file parser (used by import_from_dir)
# ============================================================


def _parse_markdown_sections(text: str, category: str) -> list[SecretEntry]:
    """Parse a ``~/.xavier/密钥/*.md`` file into :class:`SecretEntry` rows.

    The format is a series of ``## <title>`` sections, each optionally
    preceded by a ``| 字段 | 值 |`` table and always containing a
    ``text``-fenced code block whose body becomes the ``value``.

    Sections with no ``text`` block are skipped (counted in the
    caller's ``skipped`` tally). Section titles that are also the
    first line of the document (i.e. the H1 ``# 接口密钥``) are
    ignored.

    State machine
    -------------
    * ``OUTSIDE`` — pre-section preamble (H1, frontmatter, blanks).
    * ``IN_SECTION`` — between ``## `` heading and first fence.
      Table rows are captured as ``note`` lines; non-text fences
      flip us to ``IN_OTHER_FENCE``.
    * ``IN_TEXT_FENCE`` — collecting the section's ``value``.
    * ``IN_OTHER_FENCE`` — scanning for the closing ````` so we can
      return to ``IN_SECTION`` and look at the next table row.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sections: list[dict[str, Any]] = []
    title: str | None = None
    value: list[str] = []
    note: list[str] = []
    state = "OUTSIDE"

    def _flush() -> None:
        nonlocal title, value, note, state
        if title is not None and value:
            sections.append(
                {
                    "title": title,
                    "value": "\n".join(value).strip("\n"),
                    "note": "\n".join(note),
                }
            )
        title = None
        value = []
        note = []
        state = "OUTSIDE"

    for line in lines:
        heading = _HEADING_RE.match(line)
        if heading:
            # New section begins — close out the previous one.
            _flush()
            title = heading.group(1).strip()
            state = "IN_SECTION"
            continue
        if state == "OUTSIDE":
            # Preamble: ignore until the first ``## `` heading.
            continue

        if state == "IN_TEXT_FENCE":
            if line.strip().startswith("```"):
                state = "IN_SECTION"
            else:
                # Store the line verbatim — no transformations. If the
                # user wants only the value, they put only the value in
                # ``x secret set``; for .md imports the whole ``key: value``
                # block is the canonical source so we preserve it as-is.
                value.append(line)
            continue

        if state == "IN_OTHER_FENCE":
            if line.strip().startswith("```"):
                state = "IN_SECTION"
            continue

        # state == IN_SECTION
        fence = _FENCE_RE.match(line)
        if fence:
            lang = (fence.group(1) or "").lower()
            if lang == "text":
                state = "IN_TEXT_FENCE"
            else:
                state = "IN_OTHER_FENCE"
            continue
        if _TABLE_ROW_RE.match(line) and not _TABLE_SEP_RE.match(line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2 and cells[0]:
                note.append(f"{cells[0]}: {cells[1]}")

    _flush()

    entries: list[SecretEntry] = []
    for section in sections:
        entries.append(
            SecretEntry(
                name=section["title"],
                category=category,
                value=section["value"],
                note=section["note"],
            )
        )
    return entries
