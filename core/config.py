"""core/config.py — YAML configuration loader for x-cli (v0.4.x).

The :class:`AppConfig` dataclass is the in-memory representation of one
``config.yaml`` file. It is intentionally minimal and exposes six knobs:

* ``todo_dir`` — overrides :func:`core.paths.xcli_todo_dir`
* ``secrets_path`` — overrides :func:`core.paths.xcli_secrets_path`
* ``log_level`` — passed to :func:`core.logging.setup_logging`
* ``log_path`` — file path for the log handler (``null`` → no file)
* ``web_auth`` — opt-in Token authentication for ``x web``
* ``web_secret_confirmation`` — warn before the browser reads secret values

Anything outside that set is **silently ignored** so a future schema
extension does not break old clients (forward compatibility).

Loading is done with the hand-written parser in :mod:`core.parser`
(reused via :func:`core.parser.parse_yaml`). We do **not** pull in
PyYAML — see AGENTS.md §9 ("能少即少").

Resolution order (highest to lowest), per
:file:`docs/behaviors/config-behavior.md` §"路径与不变量":

1. ``--config <path>`` CLI flag (handled by ``x.py``; explicit and must exist)
2. ``$XCLI_CONFIG`` env var (explicit, must exist → :class:`ConfigError`)
3. ``<xcli_data_dir>/config.yaml`` (silent if missing)
4. Hardcoded defaults resolved via :mod:`core.paths`

This module is **stdlib-only**.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.parser import parse_yaml
from core.paths import (
    xcli_config_path,
    xcli_data_dir,
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
    {
        "todo_dir",
        "secrets_path",
        "log_level",
        "log_path",
        "web_auth",
        "web_secret_confirmation",
    }
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
    web_auth:
        Whether ``x web`` requires ``X-Web-Token`` authentication.
        Defaults to ``False`` so the loopback-only UI opens directly.
    web_secret_confirmation:
        Whether the Web UI confirms before reading complete secret records.
        Defaults to ``True`` and fails closed on invalid values.
    """

    todo_dir: Path = field(default_factory=xcli_todo_dir)
    secrets_path: Path = field(default_factory=xcli_secrets_path)
    log_level: str = "WARNING"
    log_path: Path | None = field(default_factory=xcli_log_path)
    web_auth: bool = False
    web_secret_confirmation: bool = True

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
        if "web_auth" in mapping:
            kwargs["web_auth"] = _coerce_config_bool(
                mapping["web_auth"], key="web_auth", source=source
            )
        if "web_secret_confirmation" in mapping:
            kwargs["web_secret_confirmation"] = _coerce_config_bool(
                mapping["web_secret_confirmation"],
                key="web_secret_confirmation",
                source=source,
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
                web_auth=self.web_auth,
                web_secret_confirmation=self.web_secret_confirmation,
            )
        return self

    def to_yaml(self) -> str:
        """Render the config as a YAML string with explanatory comments.

        Used by ``x --config-init`` to write the user's first
        ``config.yaml``. Quoting is added when a value contains
        characters that would be ambiguous in YAML (colons, spaces,
        etc.) — :func:`core.parser._needs_quoting` decides.
        """
        lines: list[str] = [
            "# x-cli configuration (auto-generated by `x --config-init`)",
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
        lines.append("# x web Token 认证（默认关闭；true = 开启）")
        lines.append(f"web_auth: {'true' if self.web_auth else 'false'}")
        lines.append("")
        lines.append("# 查看/编辑密钥明文前显示安全确认（默认开启）")
        lines.append(
            "web_secret_confirmation: "
            f"{'true' if self.web_secret_confirmation else 'false'}"
        )
        lines.append("")
        return "\n".join(lines)


_WEB_SECRET_CONFIRMATION_LINE = re.compile(
    r"^(web_secret_confirmation[ \t]*:[ \t]*)"
    r"([^#\r\n]*?)"
    r"([ \t]*(?:#.*)?)(\r?\n)?$"
)


def set_web_secret_confirmation(path: Path, required: bool) -> None:
    """Atomically persist the one Web secret-confirmation preference.

    This deliberately is not a generic configuration writer. Existing
    comments, unknown fields, order and unrelated values remain byte-for-byte
    unchanged; only the top-level target scalar is replaced or appended.

    Raises
    ------
    TypeError
        ``required`` is not a real bool.
    ConfigError
        The file cannot be read or atomically replaced.
    """
    if not isinstance(required, bool):
        raise TypeError("required must be a bool")

    target = Path(path)
    try:
        if target.is_file():
            original = target.read_text(encoding="utf-8")
        else:
            original = AppConfig.default().to_yaml()
    except OSError as exc:
        raise ConfigError(f"配置文件读取失败：{target} ({exc})") from exc

    replacement = "true" if required else "false"
    lines = original.splitlines(keepends=True)
    updated_lines: list[str] = []
    found = False
    for line in lines:
        match = _WEB_SECRET_CONFIRMATION_LINE.match(line)
        if match:
            found = True
            line = (
                f"{match.group(1)}{replacement}{match.group(3)}"
                f"{match.group(4) or ''}"
            )
        updated_lines.append(line)

    updated = "".join(updated_lines)
    if not found:
        if updated and not updated.endswith(("\n", "\r")):
            updated += "\n"
        updated += f"web_secret_confirmation: {replacement}\n"

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        file_descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temp_path = Path(raw_temp_path)
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            os.chmod(temp_path, target.stat().st_mode)
        os.replace(temp_path, target)
        temp_path = None
    except OSError as exc:
        raise ConfigError(f"配置文件写入失败：{target} ({exc})") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


# ============================================================
#  Auto-archive (opt-in)
# ============================================================


# Env-var truthy spellings (case-insensitive). Anything else → disabled
# (or for the "non-empty non-truthy" branch in :func:`is_auto_archive_enabled`,
# we treat non-empty as enabled to be permissive — see docstring).
_AUTO_ARCHIVE_TRUTHY: frozenset[str] = frozenset(
    {"1", "true", "yes", "on"}
)


def is_auto_archive_enabled(env: dict[str, str] | None = None) -> bool:
    """Return ``True`` iff the ``x todo`` auto-archive feature is enabled.

    对应 BDD: ``docs/behaviors/todo-auto-archive-behavior.md`` §设计要点.

    Resolution order (any one enabled → enabled, OR relation):

    1. ``$XCLI_TODO_AUTO_ARCHIVE`` env var — any non-empty value whose
       lower-cased form is in ``{"1", "true", "yes", "on"}`` (and a
       permissive catch-all for any other non-empty value, to match the
       spirit of "set it to anything truthy and it works").
    2. ``<xcli_data_dir>/config.yaml`` with ``todo.auto_archive: true``.

    Note: this helper does **not** consult ``$XCLI_CONFIG`` or the
    ``--config <path>`` CLI flag — those paths require constructing a
    full :class:`AppConfig` and are intentionally out of scope for the
    fast-path check inside ``x todo list`` / ``stats`` / ``search``.

    Parameters
    ----------
    env:
        Optional env-var override dict for testability. Defaults to
        :data:`os.environ` when ``None``. The shape mirrors
        :data:`os.environ` (a ``str → str`` mapping).
    """
    env_map = env if env is not None else os.environ

    # 1. Env var (highest priority — matches the BDD env-var beats YAML spec).
    raw = env_map.get("XCLI_TODO_AUTO_ARCHIVE", "")
    raw = raw.strip().lower() if isinstance(raw, str) else ""
    if raw:
        if raw in _AUTO_ARCHIVE_TRUTHY:
            return True
        # Permissive catch-all: any other non-empty value (e.g. "enabled",
        # " 1 ", "ON") also enables. Reject only the explicit-falsy set.
        if raw not in {"0", "false", "no", "off", ""}:
            return True

    # 2. Default config file under <xcli_data_dir>/config.yaml.
    try:
        cfg_path = xcli_data_dir() / "config.yaml"
    except OSError:
        # xcli_data_dir() can fail in pathological envs (no home dir, no
        # LOCALAPPDATA). Treat as "no config" — feature stays disabled.
        return False
    if not cfg_path.is_file():
        return False
    try:
        text = cfg_path.read_text(encoding="utf-8")
        parsed = parse_yaml(text)
    except (OSError, ValueError):
        # Broken config / unreadable file → fall back to disabled.
        # Surfacing the error here would spam the user every time they
        # run ``x todo list``, which is the wrong trade-off. Users who
        # want to debug config errors can run ``x --config-init``.
        return False
    if not isinstance(parsed, dict):
        return False
    todo_section = parsed.get("todo")
    if not isinstance(todo_section, dict):
        return False
    return _coerce_bool(todo_section.get("auto_archive"), default=False)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """Coerce a YAML scalar to ``bool``.

    Accepts the canonical YAML boolean spellings (``true`` / ``false`` /
    ``yes`` / ``no`` / ``on`` / ``off`` / ``null``) and the integers
    ``0`` and ``1``. Anything else (e.g. a string that isn't recognised)
    falls back to ``default`` — we **don't** raise, because the
    auto-archive feature is opt-in and we don't want a typo in
    ``config.yaml`` to surface on every ``x todo list`` invocation.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        # 0 → False, anything else → True (matches Python's bool() of int)
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _AUTO_ARCHIVE_TRUTHY:
            return True
        if lowered in {"0", "false", "no", "off", ""}:
            return False
    return default


# ============================================================
#  Internal helpers
# ============================================================


def _coerce_config_bool(value: Any, key: str, source: str) -> bool:
    """Parse a user-facing boolean and reject ambiguous spellings.

    Security-related switches must fail closed: a typo such as
    ``web_auth: tru`` raises instead of silently disabling authentication.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "on", "1"}:
            return True
        if lowered in {"false", "no", "off", "0"}:
            return False
    raise ConfigError(f"{source}: {key} 必须是 true 或 false")


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
