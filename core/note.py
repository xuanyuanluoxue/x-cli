"""Topic-oriented Markdown storage for ``x note``.

Each note is a standalone UTF-8 Markdown file with YAML frontmatter.
The implementation is stdlib-only and reuses x-cli's handwritten
frontmatter parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from core.parser import dump_frontmatter, parse_frontmatter
from core.paths import xcli_notes_dir


_NOTE_ID_RE = re.compile(r"^n-\d{8}-\d{6}(?:-(?:[2-9]|[1-9]\d+))?$")
_KNOWN_FIELDS = {"id", "title", "tags", "created_at", "updated_at"}


class NoteError(Exception):
    """Base class for note-store errors."""


class NoteNotFoundError(NoteError):
    """Raised when a requested note ID does not exist."""


class NoteDataError(NoteError):
    """Raised when a note file cannot be read or validated."""


@dataclass(slots=True)
class Note:
    id: str
    title: str
    tags: list[str]
    created_at: str
    updated_at: str
    body: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        metadata: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        metadata.update(self.extra)
        return dump_frontmatter(metadata, self.body)


class NoteStore:
    """Create and query topic notes stored as Markdown files."""

    def __init__(self, notes_dir: Path | None = None) -> None:
        self.notes_dir = Path(notes_dir) if notes_dir is not None else xcli_notes_dir()
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    def add(
        self,
        title: str,
        *,
        body: str = "",
        tags: Iterable[str] | None = None,
        now: datetime | None = None,
    ) -> Note:
        """Create a note without ever overwriting an existing file."""
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("笔记标题不能为空")

        current = (now or datetime.now()).replace(microsecond=0)
        timestamp = current.isoformat(timespec="seconds")
        base_id = f"n-{current:%Y%m%d-%H%M%S}"
        clean_body = body.replace("\r\n", "\n").replace("\r", "\n").strip()
        clean_tags = _normalize_tags(tags or [])

        suffix = 1
        while True:
            note_id = base_id if suffix == 1 else f"{base_id}-{suffix}"
            target = self.notes_dir / f"{note_id}.md"
            note = Note(
                id=note_id,
                title=clean_title,
                tags=clean_tags,
                created_at=timestamp,
                updated_at=timestamp,
                body=clean_body,
            )
            try:
                with target.open("x", encoding="utf-8", newline="") as stream:
                    stream.write(note.to_markdown())
            except FileExistsError:
                suffix += 1
                continue
            except OSError as exc:
                raise NoteDataError(f"{target.name}（无法写入：{exc}）") from exc
            return self._read_path(target)

    def get(self, note_id: str) -> Note:
        """Return the note with ``note_id`` or raise ``NoteNotFoundError``."""
        if not _NOTE_ID_RE.fullmatch(note_id):
            raise NoteNotFoundError(note_id)
        path = self.notes_dir / f"{note_id}.md"
        if not path.is_file():
            raise NoteNotFoundError(note_id)
        return self._read_path(path)

    def list_notes(self, *, tag: str | None = None, limit: int = 20) -> list[Note]:
        """List notes by updated time descending, optionally filtered by tag."""
        _validate_limit(limit)
        notes = self._load_all()
        if tag is not None:
            wanted = tag.strip().casefold()
            notes = [
                note
                for note in notes
                if any(item.casefold() == wanted for item in note.tags)
            ]
        return _sort_notes(notes)[:limit]

    def search(self, keyword: str, *, limit: int = 20) -> list[Note]:
        """Search title, tags, and body using a case-insensitive substring."""
        query = keyword.strip().casefold()
        if not query:
            raise ValueError("搜索关键词不能为空")
        _validate_limit(limit)
        matches: list[Note] = []
        for note in self._load_all():
            haystack = "\n".join([note.title, *note.tags, note.body]).casefold()
            if query in haystack:
                matches.append(note)
        return _sort_notes(matches)[:limit]

    def _load_all(self) -> list[Note]:
        notes: list[Note] = []
        try:
            paths = sorted(self.notes_dir.glob("*.md"))
        except OSError as exc:
            raise NoteDataError(f"{self.notes_dir}（无法读取目录：{exc}）") from exc
        for path in paths:
            if path.is_file():
                notes.append(self._read_path(path))
        return notes

    def _read_path(self, path: Path) -> Note:
        try:
            text = path.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(text)
            return _note_from_parts(path, metadata, body)
        except NoteDataError:
            raise
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise NoteDataError(f"{path.name}（{exc}）") from exc


def _normalize_tags(tags: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = str(raw).strip()
        folded = tag.casefold()
        if not tag or folded in seen:
            continue
        seen.add(folded)
        normalized.append(tag)
    return normalized


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit 必须是正整数")


def _sort_notes(notes: list[Note]) -> list[Note]:
    return sorted(notes, key=lambda note: (note.updated_at, note.id), reverse=True)


def _note_from_parts(path: Path, metadata: dict[str, Any], body: str) -> Note:
    required = ("id", "title", "tags", "created_at", "updated_at")
    missing = [name for name in required if name not in metadata]
    if missing:
        raise NoteDataError(f"{path.name}（缺少字段：{', '.join(missing)}）")

    note_id = metadata["id"]
    title = metadata["title"]
    tags = metadata["tags"]
    created_at = metadata["created_at"]
    updated_at = metadata["updated_at"]

    if not isinstance(note_id, str) or not _NOTE_ID_RE.fullmatch(note_id):
        raise NoteDataError(f"{path.name}（id 格式非法）")
    if path.stem != note_id:
        raise NoteDataError(f"{path.name}（文件名与 id 不一致）")
    if not isinstance(title, str) or not title.strip():
        raise NoteDataError(f"{path.name}（title 不能为空）")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise NoteDataError(f"{path.name}（tags 必须是字符串列表）")
    if not isinstance(created_at, str) or not isinstance(updated_at, str):
        raise NoteDataError(f"{path.name}（时间字段必须是字符串）")
    try:
        datetime.fromisoformat(created_at)
        datetime.fromisoformat(updated_at)
    except ValueError as exc:
        raise NoteDataError(f"{path.name}（时间字段格式非法）") from exc

    extra = {key: value for key, value in metadata.items() if key not in _KNOWN_FIELDS}
    return Note(
        id=note_id,
        title=title.strip(),
        tags=_normalize_tags(tags),
        created_at=created_at,
        updated_at=updated_at,
        body=body,
        extra=extra,
    )
