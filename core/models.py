"""core/models.py — Task data model and enums.

The :class:`Task` dataclass is the in-memory representation of a single
TODO.md file. Known fields are first-class attributes; everything else
lives in :attr:`Task.extra` so the storage layer can round-trip
user-managed metadata (e.g. ``paused_at``, ``description``) without
losing it on the next ``update`` or ``archive``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from core.parser import dump_frontmatter, parse_frontmatter


# ============================================================
#  Enums
# ============================================================


class TaskStatus(StrEnum):
    """Lifecycle status of a task (per ~/.xavier/TODO/00-TODO-SPEC.md §3.3)."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    WAITING = "waiting"
    ARCHIVED = "archived"


class Priority(StrEnum):
    """Task priority. Free-form ordering, so we only validate the set."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ArchiveReason(StrEnum):
    """Why a task was archived (per spec §3.5). Only valid for archived tasks."""

    DONE = "done"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


# ============================================================
#  Constants
# ============================================================


# Fields we recognise as first-class Task attributes. Anything else
# in the YAML frontmatter goes into ``extra``.
_KNOWN_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "name",
        "status",
        "priority",
        "created",
        "updated",
        "deadline",
        "folder",
        "tags",
        "subtasks",
        "reason",  # only valid when status == archived
        # v0.5 Phase A — time precision (all optional, see BDD §场景 12)
        "time",          # "HH:MM" 24h
        "end_time",      # "HH:MM" 24h
        "duration_min",  # int, minutes
        # v0.5 Phase B — subtask parent reference (id of parent task, optional)
        "parent",
        # v0.5 Phase C — reminder offsets (list of "1d"/"2h"/"30m" strings)
        "remind",
    }
)


# ============================================================
#  Task dataclass
# ============================================================


@dataclass
class Task:
    """In-memory representation of one TODO.md file.

    Attributes
    ----------
    id:
        Unique kebab-case identifier (e.g. ``kemu1``).
    name:
        Human-readable task name (matches the on-disk folder name for
        active tasks).
    status:
        One of :class:`TaskStatus`. Defaults to ``pending``.
    priority:
        One of :class:`Priority`. Defaults to ``medium``.
    created, updated:
        ``YYYY-MM-DD`` date strings.
    deadline:
        Optional ``YYYY-MM-DD`` date string. ``None`` when no deadline.
    folder:
        Path relative to the TODO root (e.g. ``任务/科目一`` or
        ``归档/20260621-科目一``).
    tags:
        Optional list of tag strings.
    subtasks:
        Optional list of subtask dicts (kept as raw data to avoid
        imposing a schema we do not yet need).
    reason:
        Archive reason — only meaningful when ``status == archived``.
    time:
        Optional ``HH:MM`` 24h start time (v0.5 Phase A).
    end_time:
        Optional ``HH:MM`` 24h end time. Mutually exclusive with
        :attr:`duration_min` (enforced at the CLI layer).
    duration_min:
        Optional integer duration in minutes. Mutually exclusive with
        :attr:`end_time`. End time is derived at display time via
        ``compute_end_time(time, duration_min)`` and not written back.
    parent:
        Optional ``id`` of the parent task (v0.5 Phase B). Max chain
        depth is 2 (root → child → grandchild). Enforced at CLI layer.
    remind:
        Optional list of reminder offsets, e.g. ``["1d", "2h", "30m"]``
        (v0.5 Phase C, **read-only mode** — no daemon/notifications
        until v0.6+ exe packaging).
    body:
        Markdown body text (everything after the ``---`` delimiter).
    extra:
        All frontmatter fields not in the known set. Always round-tripped
        through parse/dump so the user can stash arbitrary metadata.
    """

    id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    priority: Priority = Priority.MEDIUM
    created: str | None = None
    updated: str | None = None
    deadline: str | None = None
    folder: str | None = None
    tags: list[str] | None = None
    subtasks: list[dict[str, Any]] | None = None
    reason: ArchiveReason | None = None
    time: str | None = None  # v0.5 Phase A
    end_time: str | None = None  # v0.5 Phase A
    duration_min: int | None = None  # v0.5 Phase A
    parent: str | None = None  # v0.5 Phase B (kebab-case id of parent task)
    remind: list[str] | None = None  # v0.5 Phase C (e.g. ["1d", "2h"])
    body: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    # --------------------------------------------------------
    #  Constructors / serialisation
    # --------------------------------------------------------

    @classmethod
    def from_frontmatter(cls, metadata: dict[str, Any], body: str = "") -> "Task":
        """Build a :class:`Task` from a parsed frontmatter dict + body.

        Unknown fields land in :attr:`extra` (preserved verbatim). Known
        fields that are missing from ``metadata`` fall back to defaults.
        """
        kwargs: dict[str, Any] = {}
        extra: dict[str, Any] = {}

        for key, value in metadata.items():
            if key in _KNOWN_FIELDS:
                if key in ("status", "priority", "reason") and isinstance(value, str):
                    # Coerce to the matching enum when possible; fall back
                    # to the raw string if it does not match (caller can
                    # decide what to do).
                    enum_cls = {
                        "status": TaskStatus,
                        "priority": Priority,
                        "reason": ArchiveReason,
                    }[key]
                    try:
                        kwargs[key] = enum_cls(value)
                    except ValueError:
                        kwargs[key] = value
                else:
                    kwargs[key] = value
            else:
                extra[key] = value

        kwargs.setdefault("id", "")
        kwargs.setdefault("name", "")
        kwargs["body"] = body
        kwargs["extra"] = extra
        return cls(**kwargs)

    def to_frontmatter_body(self) -> tuple[dict[str, Any], str]:
        """Serialise back to ``(metadata_dict, body)`` for dumping.

        ``None`` values are omitted so the dumped YAML stays clean.
        The order is: known fields first (in the order they were declared
        in the dataclass), then ``extra`` (insertion order).
        """
        metadata: dict[str, Any] = {}

        # First: known scalar/list fields, in declaration order
        ordered_known = (
            "id",
            "name",
            "status",
            "priority",
            "created",
            "updated",
            "deadline",
            "time",
            "end_time",
            "duration_min",
            "parent",  # v0.5 Phase B
            "remind",  # v0.5 Phase C
            "folder",
            "tags",
            "subtasks",
            "reason",
        )
        for field_name in ordered_known:
            value = getattr(self, field_name)
            if value is None:
                continue
            # Convert enums to their string values for clean YAML
            if isinstance(value, (TaskStatus, Priority, ArchiveReason)):
                metadata[field_name] = value.value
            elif field_name == "tags" and isinstance(value, list) and not value:
                # Empty tag list → skip rather than emit `tags: []`
                continue
            elif field_name == "subtasks" and isinstance(value, list) and not value:
                # Empty subtask list → skip
                continue
            elif field_name == "remind" and isinstance(value, list) and not value:
                # Empty remind list → skip (same as tags / subtasks)
                continue
            else:
                metadata[field_name] = value

        # Then: extra (preserves insertion order, so unknown fields keep
        # their original position from the source file).
        for key, value in self.extra.items():
            if key in metadata:
                # Don't overwrite a known field with an extra collision
                continue
            metadata[key] = value

        return metadata, self.body

    # --------------------------------------------------------
    #  Convenience
    # --------------------------------------------------------

    def to_markdown(self) -> str:
        """Render the task as a full markdown document (frontmatter + body)."""
        metadata, body = self.to_frontmatter_body()
        return dump_frontmatter(metadata, body=body)

    def folder_path(self, base: Path | None = None) -> Path:
        """Return the absolute path to this task's folder.

        ``base`` defaults to the parent directory of the folder (i.e. the
        TODO root). When the folder is, e.g., ``任务/科目一`` and the TODO
        root is ``~/.xavier/TODO``, this returns
        ``~/.xavier/TODO/任务/科目一``.
        """
        if self.folder is None:
            raise ValueError("task has no folder set")
        folder = Path(self.folder)
        if folder.is_absolute():
            return folder
        if base is None:
            # Treat the folder as a top-level path under cwd
            return folder
        return base / folder
