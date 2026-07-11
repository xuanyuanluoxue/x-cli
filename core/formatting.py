"""core/formatting.py — Shared display-width helpers for CLI table rendering.

x-cli's table renderers need CJK-aware monospace alignment (CJK chars take
2 display cells, ASCII takes 1). These helpers are used by both
``plugins.todo`` and ``plugins.secret`` so they live in ``core`` (no
plugin can import from another plugin).

Public API:

* :func:`display_width` — monospace cell count for a string
* :func:`pad` — right-pad a string to a target display width
* :func:`supports_color` — whether ANSI escapes should be emitted (v0.5)
* :func:`colorize` — wrap text in ANSI color, no-op if unsupported (v0.5)

Design notes:

* Tab / newline / CR are treated as 0 cells so they don't break padding.
* Emoji width is terminal-dependent (Windows Terminal = 2, legacy
  conhost = 1) — :func:`unicodedata.east_asian_width` reports these as
  ``A`` (Ambiguous) which we treat as 1 (the safe common case).
* These helpers are stdlib-only (no ``wcwidth`` dependency).
* Color detection per [no-color.org](https://no-color.org/) standard:
  NO_COLOR env var > explicit flag > TTY check > TERM hint.
* Windows: tries to enable VT100 mode via ctypes for legacy cmd.
"""

from __future__ import annotations

import os
import sys
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


# ============================================================
#  v0.5 Phase D — terminal color detection (PLAN-v0.5.md §6.5)
# ============================================================

# ANSI escape codes (cached as constants to avoid repeated string concat)
_ANSI_RESET = "\x1b[0m"
_ANSI_RED = "\x1b[31m"

# Windows VT100 enable state (lazy, set once per process)
_win_vt100_enabled = False


def _enable_windows_vt100() -> bool:
    """Try to enable VT100 processing on Windows console.

    Uses ctypes to call ``SetConsoleMode`` with
    ``ENABLE_VIRTUAL_TERMINAL_PROCESSING``. Returns True if successful.
    No-op on non-Windows.
    """
    global _win_vt100_enabled
    if _win_vt100_enabled:
        return True
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if kernel32.SetConsoleMode(handle, new_mode):
            _win_vt100_enabled = True
            return True
    except Exception:  # noqa: BLE001 — best-effort, fallback to no color
        pass
    return False


def supports_color(*, force: bool | None = None) -> bool:
    """Whether ANSI color escapes should be emitted.

    Resolution order (first match wins):
    1. Explicit ``force`` parameter (True → yes, False → no)
    2. ``NO_COLOR`` env var present (any non-empty value) → no
       (per [no-color.org](https://no-color.org/) standard)
    3. ``stdout.isatty()`` → no (piped / redirected output)
    4. Windows Terminal / VS Code / modern cmd → yes (try enable VT100)
    5. Anything else (e.g. dumb terminal, unknown TERM) → no
    """
    # 1. Explicit override
    if force is not None:
        return force

    # 2. NO_COLOR env var (any non-empty value disables)
    if os.environ.get("NO_COLOR"):
        return False

    # 3. TTY check (piped output never gets color)
    stdout = sys.stdout
    if not hasattr(stdout, "isatty") or not stdout.isatty():
        return False

    # 4. Windows: try to enable VT100 mode for legacy cmd
    if sys.platform == "win32":
        return _enable_windows_vt100()

    # 5. Unix: trust TERM (anything other than "dumb" gets color)
    term = os.environ.get("TERM", "")
    return term != "" and term != "dumb"


def colorize(text: str, color: str = "red", *, enabled: bool | None = None) -> str:
    """Wrap ``text`` in an ANSI color escape if colors are supported.

    Args:
        text: The string to colorize.
        color: Color name (currently only "red" — extend as needed).
        enabled: Explicit override for color support. ``None`` auto-detects.

    Returns:
        ``text`` wrapped in ANSI escapes if enabled, otherwise ``text`` verbatim.
    """
    if enabled is None:
        enabled = supports_color()
    if not enabled:
        return text
    if color == "red":
        return f"{_ANSI_RED}{text}{_ANSI_RESET}"
    # Unknown color name → no formatting
    return text