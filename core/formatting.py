"""core/formatting.py — Shared display-width helpers for CLI table rendering.

x-cli's table renderers need CJK-aware monospace alignment (CJK chars take
2 display cells, ASCII takes 1). These helpers are used by both
``plugins.todo`` and ``plugins.secret`` so they live in ``core`` (no
plugin can import from another plugin).

Public API:

* :func:`display_width` — monospace cell count for a string
* :func:`pad` — right-pad a string to a target display width

Design notes:

* Tab / newline / CR are treated as 0 cells so they don't break padding.
* Emoji width is terminal-dependent (Windows Terminal = 2, legacy
  conhost = 1) — :func:`unicodedata.east_asian_width` reports these as
  ``A`` (Ambiguous) which we treat as 1 (the safe common case).
* These helpers are stdlib-only (no ``wcwidth`` dependency).
"""

from __future__ import annotations

import unicodedata


def display_width(s: str) -> int:
    """Monospace display width of ``s`` (CJK / emoji = 2, ASCII = 1).

    Uses :func:`unicodedata.east_asian_width` to decide width:

    * ``W`` (Wide) / ``F`` (Fullwidth) -> 2 cells
    * ``H`` (Halfwidth) / ``Na`` (Narrow) / ``A`` (Ambiguous) -> 1 cell

    Tab / newline / CR are treated as 0 so they don't break padding.
    """
    width = 0
    for ch in s:
        if ch in ("\t", "\n", "\r"):
            continue
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def pad(s: str, width: int) -> str:
    """Right-pad ``s`` so its display width is at least ``width``.

    Adds the minimum number of spaces to reach the requested display
    width. Useful for monospace table alignment with mixed ASCII + CJK.
    """
    pad_count = max(0, width - display_width(s))
    return s + " " * pad_count