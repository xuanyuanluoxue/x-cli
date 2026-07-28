"""Tests for shared terminal formatting helpers."""

from __future__ import annotations

import io

from core import formatting


def test_display_width_and_padding_handle_cjk_and_control_characters() -> None:
    assert formatting.display_width("A中\t\n\r") == 3
    assert formatting.pad("中A", 5) == "中A  "
    assert formatting.pad("already-wide", 3) == "already-wide"


def test_supports_color_honors_explicit_override_and_no_color(
    monkeypatch,
) -> None:
    assert formatting.supports_color(force=True) is True
    assert formatting.supports_color(force=False) is False

    monkeypatch.setenv("NO_COLOR", "1")
    assert formatting.supports_color() is False


def test_supports_color_rejects_non_tty_output(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(formatting.sys, "stdout", io.StringIO())

    assert formatting.supports_color() is False


def test_supports_color_uses_term_on_unix(monkeypatch) -> None:
    class Tty:
        def isatty(self) -> bool:
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(formatting.sys, "stdout", Tty())
    monkeypatch.setattr(formatting.sys, "platform", "linux")

    monkeypatch.setenv("TERM", "xterm-256color")
    assert formatting.supports_color() is True

    monkeypatch.setenv("TERM", "dumb")
    assert formatting.supports_color() is False


def test_colorize_handles_red_disabled_and_unknown_colors(monkeypatch) -> None:
    assert formatting.colorize("urgent", enabled=True) == "\x1b[31murgent\x1b[0m"
    assert formatting.colorize("urgent", enabled=False) == "urgent"
    assert formatting.colorize("urgent", color="unknown", enabled=True) == "urgent"

    monkeypatch.setattr(formatting, "supports_color", lambda: True)
    assert formatting.colorize("auto") == "\x1b[31mauto\x1b[0m"


def test_windows_vt100_helper_is_noop_on_other_platforms(monkeypatch) -> None:
    monkeypatch.setattr(formatting.sys, "platform", "linux")
    monkeypatch.setattr(formatting, "_win_vt100_enabled", False)

    assert formatting._enable_windows_vt100() is False
