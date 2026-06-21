"""core/logging.py — stdlib ``logging`` wrapper for x-cli (v0.4.x).

A thin façade over :mod:`logging` so the rest of x-cli can call
``get_logger(__name__).debug(...)`` without each module re-doing the
handler setup. The :func:`setup_logging` function is **idempotent**:
calling it a second time removes the previously installed handlers
before adding new ones, so it is safe to invoke from
``x.py``'s top-level argparse handler without worrying about
duplicate log lines.

All loggers live under the ``"x"`` namespace. ``get_logger("foo")``
returns the logger named ``"x.foo"``, so child modules can do::

    from core.logging import get_logger
    log = get_logger(__name__)   # → e.g. "x.core.storage"

The stderr handler is always installed (level-driven); the file
handler is installed only when ``log_path`` is not ``None``.

This module is **stdlib-only**.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


# ============================================================
#  Constants
# ============================================================


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Root namespace. All x-cli loggers live under this so users can
# silence x-cli globally by toggling ``logging.getLogger("x").setLevel``.
_ROOT_NAME = "x"

# Case-insensitive level name → stdlib numeric level. Includes common
# aliases (``WARN`` for ``WARNING``; ``FATAL`` for ``CRITICAL``) so
# users coming from log4j / logrus feel at home.
_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
    "FATAL": logging.CRITICAL,
}


# ============================================================
#  Public API
# ============================================================


def parse_level(s: str) -> int:
    """Convert a level name (case-insensitive) to its stdlib constant.

    Accepts ``"debug"`` / ``"Debug"`` / ``"DEBUG"`` — all map to
    :data:`logging.DEBUG`. Recognised aliases: ``"WARN"`` →
    ``WARNING``, ``"FATAL"`` → ``CRITICAL``.

    Parameters
    ----------
    s:
        Level name. Whitespace around the name is tolerated.

    Returns
    -------
    int
        One of the stdlib ``logging`` constants (``logging.DEBUG``,
        ``logging.INFO``, …).

    Raises
    ------
    ValueError
        ``s`` is not a recognised level name (the error message lists
        valid choices for quick debugging).
    """
    if not isinstance(s, str):
        raise ValueError(
            f"log level 必须是字符串，得到 {type(s).__name__}"
        )
    key = s.strip().upper()
    if key not in _LEVELS:
        valid = ", ".join(sorted(_LEVELS.keys()))
        raise ValueError(f"未知 log level {s!r}（合法值：{valid}）")
    return _LEVELS[key]


def setup_logging(level: str, log_path: Path | None) -> logging.Logger:
    """Configure the ``x`` root logger and return it.

    Idempotent: any handlers previously attached to the ``x`` logger
    are removed before new ones are added. This means ``x.py`` can
    safely call ``setup_logging`` once per invocation (e.g. inside the
    ``--log-level`` handler) without risking duplicate log lines.

    Parameters
    ----------
    level:
        Level name — see :func:`parse_level`. ``"WARNING"`` is the
        conventional default for normal use.
    log_path:
        Path to a log file. ``None`` means no file handler (e.g. when
        the user wrote ``log_path: null`` in ``config.yaml``). When a
        path is supplied, the parent directory is created if missing.

    Returns
    -------
    logging.Logger
        The configured ``"x"`` logger (the same instance every call).
        Propagation to the root logger is disabled to prevent
        duplicate output if the host program also configures logging.
    """
    numeric_level = parse_level(level)
    logger = logging.getLogger(_ROOT_NAME)
    logger.setLevel(numeric_level)

    # Idempotency: drop any handlers we previously installed.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setLevel(numeric_level)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    if log_path is not None:
        log_path = Path(log_path)
        # ``mode="a"`` so repeated runs append; ``encoding="utf-8"`` so
        # Chinese / emoji in log lines never crash on Windows cp1252.
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_path, mode="a", encoding="utf-8"
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Disable propagation so we don't double-log when the host process
    # (e.g. a test runner) has its own root-logger handlers installed.
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child of the ``x`` root logger.

    ``get_logger("core.storage")`` returns ``logging.getLogger("x.core.storage")``;
    ``get_logger("x.core.storage")`` is returned verbatim (already
    namespaced); ``get_logger(__name__)`` (e.g. from
    ``core/secrets.py``) gives ``x.core.secrets``. The returned logger
    inherits its effective level from the ``x`` root, so
    :func:`setup_logging` controls everything.

    Parameters
    ----------
    name:
        Either a short module path (``"core.storage"``) or an
        already-namespaced path (``"x.core.storage"``).

    Returns
    -------
    logging.Logger
        A configured :class:`logging.Logger` ready for ``.debug`` /
        ``.info`` / … calls.
    """
    if not name:
        return logging.getLogger(_ROOT_NAME)
    if name == _ROOT_NAME or name.startswith(_ROOT_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_ROOT_NAME}.{name}")