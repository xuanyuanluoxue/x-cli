"""core/config.py — YAML configuration loader for x-cli (v0.4.x).

The :class:`AppConfig` dataclass is the in-memory representation of one
``config.yaml`` file. It is intentionally minimal — v0.4.x only
exposes four knobs:

* ``todo_dir`` — overrides :func:`core.paths.xcli_todo_dir`
* ``secrets_path`` — overrides :func:`core.paths.xcli_secrets_path`
* ``log_level`` — passed to :func:`core.logging.setup_logging`
* ``log_path`` — file path for the log handler (``null`` → no file)

Anything outside that set is **silently ignored** so a future schema
extension does not break old clients (forward compatibility).

Loading is done with the hand-written parser in :mod:`core.parser`
(reused via :func:`core.parser.parse_yaml`). We do **not** pull in
PyYAML — see AGENTS.md §9 ("能少即少").

Resolution order (highest to lowest), per
:file:`docs/behaviors/config-behavior.md` §"路径与不变量":

1. ``$XCLI_CONFIG`` env var (explicit, must exist → :class:`ConfigError`)
2. ``--config <path>`` CLI flag (handled by ``x.py``; the loader is
   called with the resolved path, so equivalent to (1) here)
3. ``<xcli_data_dir>/config.yaml`` (silent if missing)
4. Hardcoded defaults resolved via :mod:`core.paths`

This module is **stdlib-only**.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.parser import parse_yaml
from core.paths import (
    xcli_config_path,
    xcli_log_path,
    xcli_secrets_path,
    xcli_todo_dir,
)


# ============================================================
#  Exceptions
# ============================================================


class ConfigError(Exception):
    """Raised when configuration loading fails (file missing, bad YAML, etc.).

    Maps to exit code ``5`` per :file:`docs/behaviors/config-behavior.md`
    §"退出码".
    """


# ============================================================
#  Config dataclass
# ============================================================


# Fields we know how to interpret. Anything else in the YAML file is
# silently dropped — forward compatibility (per BDD §"不变量").
_KNOWN_KEYS: frozenset[str] = frozenset(
    {"todo_dir", "secrets_path", "log_level", "log_path"}
)

# Accepted log-level spellings (case-insensitive). Includes the stdlib
# canonical names plus common aliases (WARN / FATAL). Anything outside
# this set triggers a :class:`ConfigError` at load time.
_VALID_LOG_LEVELS: frozenset[str] = frozenset(
    {"DEBUG", "INFO", "WARNING", "WARN", "ERROR", "CRITICAL", "FATAL"}
)

# Maps every accepted spelling (canonical name OR alias) to the canonical
# name we store on :class:`AppConfig`. Used by
# :func:`_coerce_log_level` so ``warn`` and ``WARN`` both round-trip to
# ``"WARNING"`` — the parser-level alias resolution happens once, here.
_LOG_LEVEL_CANONICAL: dict[str, str] = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARNING",
    "WARN": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
    "FATAL": "CRITICAL",
}


@dataclass(frozen=True)
class AppConfig:
    """Resolved x-cli configuration (one instance per program run).

    Defaults are lazy — :attr:`todo_dir`, :attr:`secrets_path`, and
    :attr:`log_path` are resolved at construction time via
    :mod:`core.paths`, so an :class:`AppConfig` constructed inside a
    test (with ``XAVIER_TODO_DIR`` / ``XCLI_SECRETS_DIR`` set) reflects
    the test environment, not the developer's real machine.

    Attributes
    ----------
    todo_dir:
        Root directory for the TODO subsystem. Defaults to
        :func:`core.paths.xcli_todo_dir`.
    secrets_path:
        Path to the secrets JSON file. Defaults to
        :func:`core.paths.xcli_secrets_path`.
    log_level:
        ``DEBUG`` / ``INFO`` / ``WARNING`` / ``ERROR`` / ``CRITICAL``
        (case-insensitive). Defaults to ``"WARNING"``.
    log_path:
        Path to the log file. ``None`` means no file handler.
        Defaults to :func:`core.paths.xcli_log_path`.
    """

    todo_dir: Path = field(default_factory=xcli_todo_dir)
    secrets_path: Path = field(default_factory=xcli_secrets_path)
    log_level: str = "WARNING"
    log_path: Path | None = field(default_factory=xcli_log_path)

    # --------------------------------------------------------
    #  Constructors
    # --------------------------------------------------------

    @classmethod
    def default(cls) -> "AppConfig":
        """Return an :class:`AppConfig` with every field at its hardcoded default.

        Equivalent to ``cls()`` but spelled out for symmetry with
        :meth:`from_yaml_file` and :meth:`from_env_and_default`.
        """
        return cls()

    @classmethod
    def from_yaml_file(cls, path: Path) -> "AppConfig":
        """Load config from the YAML file at ``path``.

        Missing file → :class:`ConfigError` (per BDD scenario 5/6 —
        fail fast on explicit user-provided paths). Bad YAML →
        :class:`ConfigError` (per BDD scenario 6). Unknown keys are
        silently ignored (forward compatibility).

        Parameters
        ----------
        path:
            Absolute or relative path to a YAML config file.

        Raises
        ------
        ConfigError
            ``path`` does not exist, cannot be read, or contains
            invalid YAML / an unknown log level.
        """
        path = Path(path)
        if not path.is_file():
            raise ConfigError(f"配置文件不存在：{path}")

        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"配置文件读取失败：{path} ({exc})") from exc

        try:
            parsed = parse_yaml(text)
        except ValueError as exc:
            raise ConfigError(f"配置文件解析失败：{path} ({exc})") from exc

        if not isinstance(parsed, dict):
            raise ConfigError(
                f"配置文件解析失败：{path} (顶层必须是 mapping)"
            )

        return cls._from_mapping(parsed, source=str(path))

    @classmethod
    def from_env_and_default(cls) -> "AppConfig":
        """Resolve config using the standard priority chain (highest first).

        1. ``$XCLI_CONFIG`` env var — file **must** exist (explicit user
           override; missing → :class:`ConfigError`).
        2. ``<xcli_data_dir>/config.yaml`` — silent if missing.
        3. :meth:`default` — hardcoded fallbacks.

        See :file:`docs/behaviors/config-behavior.md` §"路径与不变量".

        The ``--config <path>`` CLI flag is **not** handled here —
        ``x.py`` resolves it to an explicit file path and calls
        :meth:`from_yaml_file` directly.
        """
        env_path = os.environ.get("XCLI_CONFIG")
        if env_path:
            # Explicit user override → fail fast on missing file.
            return cls.from_yaml_file(Path(env_path))

        default_cfg_path = xcli_config_path()
        if default_cfg_path.is_file():
            return cls.from_yaml_file(default_cfg_path)

        return cls.default()

    @classmethod
    def _from_mapping(cls, mapping: dict[str, Any], source: str = "<unknown>") -> "AppConfig":
        """Build an :class:`AppConfig` from a parsed YAML mapping.

        Unknown keys are silently dropped. Empty / null path values
        (``log_path: null`` or ``log_path: ""``) become ``None`` per BDD
        scenario 9 — both spellings mean "do not write a log file".
        """
        kwargs: dict[str, Any] = {}

        if "todo_dir" in mapping:
            kwargs["todo_dir"] = _coerce_path(mapping["todo_dir"], "todo_dir", source)
        if "secrets_path" in mapping:
            kwargs["secrets_path"] = _coerce_path(
                mapping["secrets_path"], "secrets_path", source
            )
        if "log_level" in mapping:
            kwargs["log_level"] = _coerce_log_level(
                mapping["log_level"], source=source
            )
        if "log_path" in mapping:
            kwargs["log_path"] = _coerce_log_path(
                mapping["log_path"], source=source
            )

        return cls(**kwargs)

    # --------------------------------------------------------
    #  Convenience
    # --------------------------------------------------------

    def effective(self) -> "AppConfig":
        """Return a copy with any ``None`` defaults filled in.

        ``AppConfig`` is constructed with all defaults already resolved
        (thanks to ``default_factory``), so this is effectively a no-op
        for fields that were never set. It exists to give callers a
        single post-construction normalisation point — for example, if
        a future caller builds an :class:`AppConfig` with ``log_path=None``
        on purpose and then wants the platform default back.
        """
        if self.log_path is None:
            return AppConfig(
                todo_dir=self.todo_dir,
                secrets_path=self.secrets_path,
                log_level=self.log_level,
                log_path=None,  # explicit "no file" wins over default
            )
        return self

    def to_yaml(self) -> str:
        """Render the config as a YAML string with explanatory comments.

        Used by ``x --config init`` to write the user's first
        ``config.yaml``. Quoting is added when a value contains
        characters that would be ambiguous in YAML (colons, spaces,
        etc.) — :func:`core.parser._needs_quoting` decides.
        """
        lines: list[str] = [
            "# x-cli configuration (auto-generated by `x --config init`)",
            "# 注释行（# 开头）会被忽略",
            "# 不识别的 key 会被忽略（向前兼容）",
            "",
        ]

        # Order matches the BDD schema example so users see the same
        # sequence in both the doc and the on-disk file.
        lines.append(f"todo_dir: {_yaml_scalar(self.todo_dir)}")
        lines.append(f"secrets_path: {_yaml_scalar(self.secrets_path)}")
        lines.append(f"log_level: {self.log_level}")
        lines.append(
            f"log_path: {_yaml_scalar(self.log_path) if self.log_path else 'null'}"
        )
        lines.append("")
        return "\n".join(lines)


# ============================================================
#  Internal helpers
# ============================================================


def _coerce_path(value: Any, key: str, source: str) -> Path:
    """Convert a YAML scalar to a :class:`Path`.

    Raises :class:`ConfigError` if the value is empty / null (those
    spellings are only meaningful for ``log_path``, not for
    ``todo_dir`` / ``secrets_path``).
    """
    if value is None:
        raise ConfigError(f"{source}: {key} 不能为空")
    if not isinstance(value, str):
        raise ConfigError(f"{source}: {key} 必须是字符串，得到 {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise ConfigError(f"{source}: {key} 不能为空")
    return Path(stripped)


def _coerce_log_path(value: Any, source: str) -> Path | None:
    """Convert a YAML scalar to a log-file path.

    ``None`` and ``""`` both yield ``None`` (per BDD scenario 9:
    "log_path: null 或 log_path: \"\" → 不写文件").
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(
            f"{source}: log_path 必须是字符串或 null，得到 {type(value).__name__}"
        )
    stripped = value.strip()
    if not stripped:
        return None
    return Path(stripped)


def _coerce_log_level(value: Any, source: str) -> str:
    """Validate and canonicalise a log-level string.

    Accepts any case (``debug`` / ``Debug`` / ``DEBUG``) and resolves
    aliases (``WARN`` → ``WARNING``, ``FATAL`` → ``CRITICAL``) so the
    stored value is always a canonical name. Rejects unknown spellings
    with an error message that lists every accepted alias.
    """
    if not isinstance(value, str):
        raise ConfigError(
            f"{source}: log_level 必须是字符串，得到 {type(value).__name__}"
        )
    canonical = value.strip().upper()
    if canonical not in _LOG_LEVEL_CANONICAL:
        valid = ", ".join(sorted(_LOG_LEVEL_CANONICAL.keys()))
        raise ConfigError(f"{source}: 未知 log_level {value!r}（合法值：{valid}）")
    return _LOG_LEVEL_CANONICAL[canonical]


def _yaml_scalar(value: Any) -> str:
    """Quote a string scalar if YAML would otherwise misread it.

    Mirrors the heuristics in :mod:`core.parser` so the dumped config
    round-trips back to the same value through :func:`parse_yaml`.
    """
    if value is None:
        return "null"
    text = str(value)
    if _needs_quoting(text):
        # Use double quotes; escape backslashes and embedded quotes.
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


# Quote-trigger characters lifted from core.parser._QUOTE_TRIGGER_CHARS so
# the config dumper and parser stay in sync. Kept local rather than
# imported from core.parser (private API).
_QUOTE_TRIGGERS = set("[]{},:?#&*!|>'\"%@`")


def _needs_quoting(s: str) -> bool:
    """Decide whether ``s`` needs to be wrapped in double quotes.

    Conservative: any character that has structural meaning in YAML,
    leading/trailing whitespace, or a value that parses as a bool /
    number / null gets quoted. Mirrors
    :func:`core.parser._needs_quoting`.
    """
    if not s:
        return True
    if s[0] in "#&*!|>[{}-'\"" or s[0] in "%@`":
        return True
    if s != s.strip():
        return True
    if any(c in s for c in _QUOTE_TRIGGERS):
        return True
    if ": " in s or s.endswith(":"):
        return True
    if " #" in s:
        return True
    if s.lower() in ("true", "false", "null", "~", "yes", "no", "on", "off"):
        return True
    try:
        float(s)
        return True
    except ValueError:
        pass
    return False