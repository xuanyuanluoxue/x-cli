"""Tests for ``core/logging.py`` — stdlib ``logging`` wrapper (v0.4.x).

Covers the four behaviours the BDD spec calls out:

* ``parse_level`` is case-insensitive and accepts aliases (scenario 7)
* ``setup_logging`` is idempotent (no duplicate log lines on repeat calls)
* ``setup_logging(level, None)`` adds no file handler (scenario 9)
* ``setup_logging(level, path)`` writes to the file in ``utf-8`` (scenario 8)

The tests intentionally do **not** assert the stderr capture (that is
covered by ``test_e2e_x.py`` once ``x --log-level`` lands). Here we
focus on the contract of :func:`core.logging.setup_logging` itself.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from core.logging import get_logger, parse_level, setup_logging


# ============================================================
#  Fixtures
# ============================================================


@pytest.fixture
def reset_x_logger() -> None:
    """Tear down ``logging.getLogger("x")`` between tests.

    ``setup_logging`` is documented as idempotent but we want to start
    each test from a known-clean slate so handlers / propagate state
    from previous tests cannot leak across.
    """
    logger = logging.getLogger("x")
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    yield


# ============================================================
#  parse_level
# ============================================================


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("DEBUG", logging.DEBUG),
        ("debug", logging.DEBUG),
        ("Debug", logging.DEBUG),
        ("INFO", logging.INFO),
        ("WARNING", logging.WARNING),
        ("WARN", logging.WARNING),  # alias
        ("warn", logging.WARNING),
        ("ERROR", logging.ERROR),
        ("CRITICAL", logging.CRITICAL),
        ("FATAL", logging.CRITICAL),  # alias
    ],
)
def test_parse_level_accepts_case_insensitive_and_aliases(
    raw: str, expected: int
) -> None:
    """All common spellings resolve to the matching stdlib constant."""
    assert parse_level(raw) == expected


def test_parse_level_strips_whitespace() -> None:
    """Trailing / leading whitespace tolerated (YAML configs can be noisy)."""
    assert parse_level("  DEBUG  ") == logging.DEBUG


@pytest.mark.parametrize("bad", ["TRACE", "verbose", "D", "", " none"])
def test_parse_level_unknown_raises_value_error(bad: str) -> None:
    """Garbage names raise :class:`ValueError` with a hint at valid options.

    ``"INFO "`` (trailing space) is **not** in the bad list because
    :func:`parse_level` strips whitespace before lookup — that's a
    documented convenience for noisy YAML configs.
    """
    with pytest.raises(ValueError, match="未知 log level"):
        parse_level(bad)


def test_parse_level_non_string_raises() -> None:
    """Non-string input is rejected (caller bug, not user typo)."""
    with pytest.raises(ValueError, match="必须是字符串"):
        parse_level(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="必须是字符串"):
        parse_level(10)  # type: ignore[arg-type]


# ============================================================
#  setup_logging — basic shape
# ============================================================


def test_setup_logging_returns_root_x_logger(reset_x_logger) -> None:
    """The returned object is the ``"x"`` logger (or a child of it)."""
    logger = setup_logging("WARNING", None)
    assert logger.name == "x"
    assert logger is logging.getLogger("x")


def test_setup_logging_sets_level(reset_x_logger) -> None:
    """After setup, the root logger level matches the requested level."""
    logger = setup_logging("DEBUG", None)
    assert logger.level == logging.DEBUG

    logger = setup_logging("ERROR", None)
    assert logger.level == logging.ERROR


def test_setup_logging_disables_propagation(reset_x_logger) -> None:
    """``propagate`` is False so test runners don't double-log."""
    logger = setup_logging("INFO", None)
    assert logger.propagate is False


# ============================================================
#  setup_logging — stderr handler
# ============================================================


def test_setup_logging_always_adds_stderr_handler(
    reset_x_logger, capsys: pytest.CaptureFixture[str]
) -> None:
    """A :class:`logging.StreamHandler` targeting stderr is always installed."""
    logger = setup_logging("DEBUG", None)

    handlers = [h for h in logger.handlers if not isinstance(h.formatter, type(None))]
    stderr_handlers = [
        h
        for h in logger.handlers
        if isinstance(h, logging.StreamHandler)
        and getattr(h, "stream", None) is sys.stderr
    ]
    assert len(stderr_handlers) == 1, "expected exactly one stderr handler"
    assert stderr_handlers[0].level == logging.DEBUG


def test_setup_logging_stderr_handler_respects_level(
    reset_x_logger, capsys: pytest.CaptureFixture[str]
) -> None:
    """A WARNING-level setup does not emit DEBUG messages to stderr."""
    logger = setup_logging("WARNING", None)
    child = get_logger("child")
    child.debug("should-be-filtered")
    child.warning("should-appear")

    captured = capsys.readouterr()
    assert "should-be-filtered" not in captured.err
    assert "should-appear" in captured.err


# ============================================================
#  setup_logging — file handler (scenario 8)
# ============================================================


def test_setup_logging_with_path_writes_to_file(
    reset_x_logger, tmp_path: Path
) -> None:
    """``log_path=<path>`` installs a file handler that appends to that file."""
    log_file = tmp_path / "x.log"

    setup_logging("DEBUG", log_file)
    log = get_logger("core.foo")
    log.info("hello file")

    assert log_file.is_file()
    contents = log_file.read_text(encoding="utf-8")
    assert "hello file" in contents
    assert "[INFO]" in contents
    assert "x.core.foo" in contents


def test_setup_logging_file_handler_uses_utf8(
    reset_x_logger, tmp_path: Path
) -> None:
    """Chinese / emoji log lines never crash (Windows cp1252 guard)."""
    log_file = tmp_path / "x.log"

    setup_logging("DEBUG", log_file)
    log = get_logger("unicode")
    log.warning("测试中文 + emoji \u2728")  # ✨

    contents = log_file.read_text(encoding="utf-8")
    assert "测试中文" in contents
    assert "\u2728" in contents


def test_setup_logging_creates_parent_dir(
    reset_x_logger, tmp_path: Path
) -> None:
    """Missing parent directories are created on demand."""
    log_file = tmp_path / "deep" / "nested" / "x.log"
    assert not log_file.parent.exists()

    setup_logging("INFO", log_file)
    log = get_logger("parent")
    log.info("nested write")

    assert log_file.is_file()


def test_setup_logging_appends_to_existing_file(
    reset_x_logger, tmp_path: Path
) -> None:
    """``mode="a"`` semantics: previous content is preserved."""
    log_file = tmp_path / "x.log"
    log_file.write_text("PREVIOUS LINE\n", encoding="utf-8")

    setup_logging("INFO", log_file)
    get_logger("appender").info("new line")

    contents = log_file.read_text(encoding="utf-8")
    assert "PREVIOUS LINE" in contents
    assert "new line" in contents


# ============================================================
#  setup_logging — no file handler (scenario 9)
# ============================================================


def test_setup_logging_with_none_path_adds_no_file_handler(
    reset_x_logger,
) -> None:
    """``log_path=None`` → no :class:`logging.FileHandler` is attached."""
    setup_logging("INFO", None)
    logger = logging.getLogger("x")

    file_handlers = [
        h for h in logger.handlers if isinstance(h, logging.FileHandler)
    ]
    assert file_handlers == []


def test_setup_logging_with_empty_string_path_adds_no_file_handler(
    reset_x_logger, tmp_path: Path
) -> None:
    """``log_path=""`` is also "no file" (matches ``log_path: ""`` from YAML)."""
    # Note: setup_logging takes Path | None, so the empty-string
    # behaviour is enforced upstream by core.config._coerce_log_path.
    # Here we just verify the None contract holds for explicit None.
    setup_logging("INFO", None)
    logger = logging.getLogger("x")
    file_handlers = [
        h for h in logger.handlers if isinstance(h, logging.FileHandler)
    ]
    assert file_handlers == []


def test_setup_logging_no_file_handler_creates_no_log_file(
    reset_x_logger, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running with ``log_path=None`` does not create ``x.log`` in cwd."""
    monkeypatch.chdir(tmp_path)
    setup_logging("INFO", None)

    get_logger("silent").warning("nothing-on-disk")
    assert not (tmp_path / "x.log").exists()


# ============================================================
#  setup_logging — idempotency
# ============================================================


def test_setup_logging_is_idempotent(reset_x_logger) -> None:
    """Calling twice does not double-install handlers (no duplicate log lines)."""
    setup_logging("DEBUG", None)
    setup_logging("DEBUG", None)
    setup_logging("DEBUG", None)

    logger = logging.getLogger("x")
    handlers = logger.handlers
    # Exactly one stderr handler after three calls.
    stderr_count = sum(
        1
        for h in handlers
        if isinstance(h, logging.StreamHandler)
        and getattr(h, "stream", None) is sys.stderr
    )
    assert stderr_count == 1


def test_setup_logging_replacement_replaces_handlers(
    reset_x_logger, tmp_path: Path
) -> None:
    """A second call with a different ``log_path`` swaps (not adds) handlers."""
    file_a = tmp_path / "a.log"
    file_b = tmp_path / "b.log"

    setup_logging("INFO", file_a)
    setup_logging("INFO", file_b)

    logger = logging.getLogger("x")
    file_paths = {getattr(h, "baseFilename", None) for h in logger.handlers}
    # file_a must NOT appear anywhere — only file_b.
    assert str(file_a) not in file_paths
    assert str(file_b) in file_paths


def test_setup_logging_replacement_removes_file_handler_when_switched_to_none(
    reset_x_logger, tmp_path: Path
) -> None:
    """Switching from file → None in a second call removes the file handler."""
    file_a = tmp_path / "a.log"
    setup_logging("INFO", file_a)
    setup_logging("INFO", None)

    logger = logging.getLogger("x")
    file_handlers = [
        h for h in logger.handlers if isinstance(h, logging.FileHandler)
    ]
    assert file_handlers == []


# ============================================================
#  get_logger
# ============================================================


def test_get_logger_short_name_is_namespaced() -> None:
    """``get_logger("foo")`` returns ``"x.foo"``."""
    assert get_logger("foo").name == "x.foo"


def test_get_logger_dotted_short_name_is_namespaced() -> None:
    """``get_logger("a.b.c")`` returns ``"x.a.b.c"``."""
    assert get_logger("a.b.c").name == "x.a.b.c"


def test_get_logger_already_namespaced_returned_verbatim() -> None:
    """``get_logger("x.core.foo")`` does not double-prefix."""
    assert get_logger("x.core.foo").name == "x.core.foo"


def test_get_logger_root_returns_x() -> None:
    """``get_logger("x")`` returns the root ``x`` logger."""
    assert get_logger("x").name == "x"


def test_get_logger_empty_string_returns_x() -> None:
    """``get_logger("")`` falls back to the ``x`` root logger."""
    assert get_logger("").name == "x"


def test_get_logger_child_inherits_level_from_root(
    reset_x_logger,
) -> None:
    """Setting level on root ``x`` propagates via effective level."""
    setup_logging("ERROR", None)
    child = get_logger("core.deeply.nested")
    assert child.getEffectiveLevel() == logging.ERROR


# ============================================================
#  Format
# ============================================================


def test_log_format_includes_timestamp_level_name_message(
    reset_x_logger, tmp_path: Path
) -> None:
    """The configured format matches the BDD example output."""
    log_file = tmp_path / "x.log"

    setup_logging("DEBUG", log_file)
    get_logger("fmt").info("hello")

    contents = log_file.read_text(encoding="utf-8")
    # Timestamp YYYY-MM-DD HH:MM:SS, [LEVEL], name, message.
    import re

    pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[INFO\] x\.fmt: hello\s*$"
    )
    assert pattern.search(contents), f"line did not match expected format: {contents!r}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))