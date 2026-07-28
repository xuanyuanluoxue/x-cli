"""Local Markdown storage for ``x diary``.

P0 stores one UTF-8 file per local calendar day and appends timestamped
Markdown list items. The module is stdlib-only and contains no CLI logic.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from core.paths import xcli_diary_dir


_DIARY_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DiaryStore:
    """Read and append diary entries in a directory of daily Markdown files."""

    def __init__(self, diary_dir: Path | None = None) -> None:
        self.diary_dir = Path(diary_dir) if diary_dir is not None else xcli_diary_dir()
        self.diary_dir.mkdir(parents=True, exist_ok=True)

    def append(self, content: str, *, now: datetime | None = None) -> Path:
        """Append ``content`` to the Markdown file for ``now``'s local date."""
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("日记内容不能为空")

        current = now or datetime.now()
        day = current.date().isoformat()
        target = self.diary_dir / f"{day}.md"
        entry = self._format_entry(normalized, current)

        if not target.exists() or target.stat().st_size == 0:
            target.write_text(f"# {day}\n\n{entry}", encoding="utf-8")
            return target

        existing = target.read_text(encoding="utf-8")
        separator = "" if existing.endswith("\n") else "\n"
        with target.open("a", encoding="utf-8", newline="") as stream:
            stream.write(f"{separator}{entry}")
        return target

    def list_dates(self, *, limit: int = 7) -> list[date]:
        """Return up to ``limit`` valid diary dates, newest first."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit 必须是正整数")

        dates: list[date] = []
        for path in self.diary_dir.iterdir():
            if not path.is_file() or path.suffix != ".md":
                continue
            if not _DIARY_STEM_RE.fullmatch(path.stem):
                continue
            try:
                dates.append(date.fromisoformat(path.stem))
            except ValueError:
                continue
        return sorted(dates, reverse=True)[:limit]

    @staticmethod
    def _format_entry(content: str, current: datetime) -> str:
        lines = content.split("\n")
        first = f"- {current:%H:%M} {lines[0]}"
        continuations = [f"  {line}" for line in lines[1:]]
        return "\n".join([first, *continuations]) + "\n"
