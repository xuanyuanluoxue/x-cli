"""Tests for ``core/config.py`` — YAML config loader (v0.4.x).

Covers all 10 scenarios in
:file:`docs/behaviors/config-behavior.md`. The tests are deliberately
environment-isolated: every test sets ``XCLI_CONFIG`` / ``XAVIER_TODO_DIR``
explicitly via ``monkeypatch.setenv`` and tears the ``x-cli`` data dir
to a ``tmp_path`` so we never read the developer's real machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.config import AppConfig, ConfigError
from core.logging import parse_level
from core.paths import (
    xcli_config_path,
    xcli_data_dir,
    xcli_log_path,
    xcli_secrets_path,
    xcli_todo_dir,
)


# ============================================================
#  Helpers
# ============================================================


def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Strip every config-related env var and pin the data dir to ``tmp_path``.

    Called at the top of every test that touches path resolution. This
    is the only way to guarantee ``xcli_*_dir`` does not look at the
    developer's real ``%LOCALAPPDATA%`` on Windows.
    """
    monkeypatch.delenv("XCLI_CONFIG", raising=False)
    monkeypatch.delenv("XAVIER_TODO_DIR", raising=False)
    monkeypatch.delenv("XCLI_SECRETS_DIR", raising=False)
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


# ============================================================
#  Scenario 1: 默认配置（无文件）
# ============================================================


def test_scenario1_default_when_no_config_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No ``XCLI_CONFIG`` + no default config.yaml → all hardcoded defaults.

    Mirrors BDD scenario 1: the first launch on a fresh machine
    silently uses every hardcoded default and never complains.
    """
    _isolate_env(monkeypatch, tmp_path)

    # Sanity: xcli_config_path() exists, but its file does not.
    assert xcli_config_path() == tmp_path / "x-cli" / "config.yaml"
    assert not xcli_config_path().is_file()

    cfg = AppConfig.from_env_and_default()

    assert cfg.todo_dir == xcli_todo_dir()
    assert cfg.secrets_path == xcli_secrets_path()
    assert cfg.log_level == "WARNING"
    assert cfg.log_path == xcli_log_path()


def test_appconfig_default_factory_returns_hardcoded_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``AppConfig.default()`` mirrors ``cls()`` and resolves via ``core.paths``."""
    _isolate_env(monkeypatch, tmp_path)

    cfg = AppConfig.default()

    assert cfg.todo_dir == xcli_todo_dir()
    assert cfg.secrets_path == xcli_secrets_path()
    assert cfg.log_level == "WARNING"
    assert cfg.log_path == xcli_log_path()


# ============================================================
#  Scenario 2: 首次写默认配置文件（to_yaml）
# ============================================================


def test_scenario2_to_yaml_produces_init_file_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``to_yaml()`` output is suitable for ``x --config init``.

    Per BDD scenario 2, the init command writes the resolved defaults
    to ``<xcli_data_dir>/config.yaml``. The loader's ``to_yaml()``
    helper is what produces that content.
    """
    _isolate_env(monkeypatch, tmp_path)
    cfg = AppConfig.default()

    text = cfg.to_yaml()

    # All four fields present (order matters per BDD schema example)
    assert "todo_dir:" in text
    assert "secrets_path:" in text
    assert "log_level: WARNING" in text
    assert "log_path:" in text
    # Header comment for traceability
    assert "x-cli configuration" in text
    assert text.startswith("#")


def test_to_yaml_round_trips_through_from_yaml_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``from_yaml_file(to_yaml())`` yields an equivalent :class:`AppConfig`.

    Catches quoting bugs — if ``to_yaml`` emits an unquoted Windows path
    the parser will misread it as a nested mapping, and the round-trip
    breaks.
    """
    _isolate_env(monkeypatch, tmp_path)
    original = AppConfig.default()

    text = original.to_yaml()
    target = tmp_path / "round-trip.yaml"
    target.write_text(text, encoding="utf-8")

    loaded = AppConfig.from_yaml_file(target)
    assert loaded == original


# ============================================================
#  Scenario 3 + 4: XCLI_CONFIG / --config <path>
# ============================================================


def test_scenario3_xcli_config_env_overrides_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``XCLI_CONFIG`` env var wins over the default config file."""
    _isolate_env(monkeypatch, tmp_path)

    custom_dir = tmp_path / "my-tasks"
    custom_cfg = tmp_path / "my-config.yaml"
    custom_cfg.write_text(
        f"todo_dir: {custom_dir}\nlog_level: DEBUG\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("XCLI_CONFIG", str(custom_cfg))

    cfg = AppConfig.from_env_and_default()

    assert cfg.todo_dir == custom_dir
    assert cfg.log_level == "DEBUG"
    # secrets_path / log_path still fall through to defaults because
    # the custom file did not specify them.
    assert cfg.secrets_path == xcli_secrets_path()
    assert cfg.log_path == xcli_log_path()


def test_scenario3_env_with_partial_config_keeps_defaults_for_missing_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A custom config that omits ``secrets_path`` still honours the default."""
    _isolate_env(monkeypatch, tmp_path)

    cfg_file = tmp_path / "partial.yaml"
    cfg_file.write_text("log_level: INFO\n", encoding="utf-8")
    monkeypatch.setenv("XCLI_CONFIG", str(cfg_file))

    cfg = AppConfig.from_env_and_default()

    assert cfg.log_level == "INFO"
    assert cfg.todo_dir == xcli_todo_dir()
    assert cfg.secrets_path == xcli_secrets_path()
    assert cfg.log_path == xcli_log_path()


def test_scenario4_from_yaml_file_is_path_equivalent_to_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Explicit ``--config <path>`` is a direct ``from_yaml_file`` call."""
    _isolate_env(monkeypatch, tmp_path)

    custom_dir = tmp_path / "alt-tasks"
    cfg_file = tmp_path / "alt-config.yaml"
    cfg_file.write_text(
        f"todo_dir: {custom_dir}\n", encoding="utf-8"
    )

    cfg = AppConfig.from_yaml_file(cfg_file)
    assert cfg.todo_dir == custom_dir


# ============================================================
#  Scenario 5: 配置文件不存在 → 报错
# ============================================================


def test_scenario5_missing_file_in_env_raises_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``XCLI_CONFIG`` pointing at a missing file → :class:`ConfigError`."""
    _isolate_env(monkeypatch, tmp_path)
    monkeypatch.setenv("XCLI_CONFIG", str(tmp_path / "does-not-exist.yaml"))

    with pytest.raises(ConfigError, match="配置文件不存在"):
        AppConfig.from_env_and_default()


def test_scenario5_missing_file_via_from_yaml_file_raises(
    tmp_path: Path,
) -> None:
    """``from_yaml_file`` with a missing path → :class:`ConfigError`."""
    with pytest.raises(ConfigError, match="配置文件不存在"):
        AppConfig.from_yaml_file(tmp_path / "missing.yaml")


# ============================================================
#  Scenario 6: YAML 解析失败
# ============================================================


def test_scenario6_invalid_yaml_raises_config_error(tmp_path: Path) -> None:
    """Garbage YAML triggers ``ConfigError`` (does **not** silently fall back).

    We pick an input the hand-written parser actually rejects: a block
    mapping followed by an inconsistent list (the parser raises
    ``ValueError("dict entry in non-dict container ...")`` when it
    sees a sibling ``key: value`` inside what should be a list).
    """
    bad = tmp_path / "bad.yaml"
    # ``a:\n  - 1`` opens a block-list; ``b: 2`` at indent 1 then has
    # nowhere to attach → parser raises.
    bad.write_text("a:\n  - 1\n b: 2\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="配置文件解析失败"):
        AppConfig.from_yaml_file(bad)


def test_scenario6_yaml_top_level_not_mapping_raises(tmp_path: Path) -> None:
    """A YAML list at top level is not a config — must error.

    The parser raises ``ValueError("unexpected list item at indent 0")``
    on a top-level sequence; the loader wraps that in
    :class:`ConfigError`.
    """
    bad = tmp_path / "list.yaml"
    bad.write_text("- a\n- b\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="配置文件解析失败"):
        AppConfig.from_yaml_file(bad)


# ============================================================
#  Scenario 7 + 8 + 9: log_level / log_path
# ============================================================


@pytest.mark.parametrize(
    "raw,canonical",
    [
        ("DEBUG", "DEBUG"),
        ("debug", "DEBUG"),
        ("Debug", "DEBUG"),
        ("INFO", "INFO"),
        ("WARNING", "WARNING"),
        ("warn", "WARNING"),
        ("ERROR", "ERROR"),
        ("critical", "CRITICAL"),
        ("FATAL", "CRITICAL"),
    ],
)
def test_log_level_accepts_case_insensitive_and_aliases(
    tmp_path: Path, raw: str, canonical: str
) -> None:
    """Any casing or alias maps to the canonical name (uppercase)."""
    cfg_file = tmp_path / "log-level.yaml"
    cfg_file.write_text(f"log_level: {raw}\n", encoding="utf-8")

    cfg = AppConfig.from_yaml_file(cfg_file)
    assert cfg.log_level == canonical
    # And the stdlib parser agrees.
    assert parse_level(cfg.log_level) == parse_level(canonical)


def test_log_level_unknown_raises_config_error(tmp_path: Path) -> None:
    """Garbage log level → clear error listing valid options."""
    cfg_file = tmp_path / "bad-level.yaml"
    cfg_file.write_text("log_level: TRACE\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="未知 log_level"):
        AppConfig.from_yaml_file(cfg_file)


def test_scenario8_log_path_default_when_not_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Omitting ``log_path`` → :func:`xcli_log_path`."""
    _isolate_env(monkeypatch, tmp_path)

    cfg = AppConfig.default()
    assert cfg.log_path == xcli_log_path()


def test_scenario9_log_path_null_disables_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``log_path: null`` → :attr:`log_path` is ``None``."""
    _isolate_env(monkeypatch, tmp_path)

    cfg_file = tmp_path / "no-log.yaml"
    cfg_file.write_text("log_path: null\n", encoding="utf-8")
    monkeypatch.setenv("XCLI_CONFIG", str(cfg_file))

    cfg = AppConfig.from_env_and_default()
    assert cfg.log_path is None


def test_scenario9_log_path_empty_string_disables_file(tmp_path: Path) -> None:
    """``log_path: ""`` is also "no file" per BDD scenario 9."""
    cfg_file = tmp_path / "empty-log.yaml"
    cfg_file.write_text('log_path: ""\n', encoding="utf-8")

    cfg = AppConfig.from_yaml_file(cfg_file)
    assert cfg.log_path is None


# ============================================================
#  Scenario 10: 向后兼容（不破坏现有行为）
# ============================================================


def test_scenario10_default_config_is_indistinguishable_from_hardcoded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no config file anywhere, the resolved config == hardcoded defaults.

    Existing ``x todo list`` callers (no flags) must keep working.
    """
    _isolate_env(monkeypatch, tmp_path)

    cfg = AppConfig.from_env_and_default()

    # Every field is the exact value ``core.paths`` would return.
    assert cfg.todo_dir == xcli_todo_dir()
    assert cfg.secrets_path == xcli_secrets_path()
    assert cfg.log_path == xcli_log_path()
    assert cfg.log_level == "WARNING"


def test_frozen_dataclass_prevents_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``AppConfig`` is frozen — assigning a new attribute raises."""
    _isolate_env(monkeypatch, tmp_path)

    cfg = AppConfig.default()
    with pytest.raises(Exception):
        cfg.log_level = "DEBUG"  # type: ignore[misc]


# ============================================================
#  Robustness: comments / quoting / unknown keys
# ============================================================


def test_yaml_with_comments_and_unknown_keys_loads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Full BDD example: comments, quoted Windows path, unknown ``proxy`` key."""
    _isolate_env(monkeypatch, tmp_path)

    custom_dir = tmp_path / "tasks"
    cfg_file = tmp_path / "full.yaml"
    cfg_file.write_text(
        "# x-cli configuration\n"
        "\n"
        f'todo_dir: "{custom_dir}"\n'
        'secrets_path: "C:\\Users\\X\\AppData\\Local\\x-cli\\secrets.json"\n'
        "log_level: WARNING\n"
        'log_path: "C:\\Users\\X\\AppData\\Local\\x-cli\\x.log"\n'
        "\n"
        "# Future fields (v0.5+):\n"
        "proxy: http://example.invalid\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("XCLI_CONFIG", str(cfg_file))

    cfg = AppConfig.from_env_and_default()

    assert cfg.todo_dir == custom_dir
    # Windows path survives the round-trip (no backslash escaping issue)
    assert cfg.secrets_path == Path(
        "C:\\Users\\X\\AppData\\Local\\x-cli\\secrets.json"
    )
    assert cfg.log_path == Path("C:\\Users\\X\\AppData\\Local\\x-cli\\x.log")
    assert cfg.log_level == "WARNING"
    # Unknown keys do not surface as attributes (silently dropped)


def test_quoted_unquoted_and_null_values_all_supported(tmp_path: Path) -> None:
    """Three equivalent spellings of a path: quoted, unquoted, null."""
    quoted = tmp_path / "q.yaml"
    quoted.write_text('todo_dir: "/tmp/a"\n', encoding="utf-8")
    unquoted = tmp_path / "u.yaml"
    unquoted.write_text("todo_dir: /tmp/a\n", encoding="utf-8")
    none_set = tmp_path / "n.yaml"
    none_set.write_text("todo_dir: null\n", encoding="utf-8")

    # Quoted / unquoted both produce the same path.
    assert AppConfig.from_yaml_file(quoted).todo_dir == Path("/tmp/a")
    assert AppConfig.from_yaml_file(unquoted).todo_dir == Path("/tmp/a")
    # But null for a required field is an error.
    with pytest.raises(ConfigError, match="todo_dir 不能为空"):
        AppConfig.from_yaml_file(none_set)


def test_unknown_keys_silently_ignored(tmp_path: Path) -> None:
    """A config with a typo / future field loads cleanly (no validation)."""
    cfg_file = tmp_path / "future.yaml"
    cfg_file.write_text(
        "log_level: INFO\n"
        "proxy: http://example.invalid\n"
        "api_endpoints:\n"
        "  openai: https://api.example.com\n",
        encoding="utf-8",
    )

    cfg = AppConfig.from_yaml_file(cfg_file)
    assert cfg.log_level == "INFO"
    # No attribute for unknown keys exists / is silently dropped.
    assert not hasattr(cfg, "proxy")
    assert not hasattr(cfg, "api_endpoints")


def test_effective_noop_when_defaults_already_resolved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``effective()`` returns an equal config when defaults are already filled."""
    _isolate_env(monkeypatch, tmp_path)

    cfg = AppConfig.default()
    effective = cfg.effective()

    assert effective == cfg


# ============================================================
#  Priority chain (XCLI_CONFIG > default file > hardcoded)
# ============================================================


def test_priority_xcli_config_beats_default_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Both ``XCLI_CONFIG`` and the default config.yaml present → env wins."""
    _isolate_env(monkeypatch, tmp_path)

    # Default file says log_level=INFO
    default_file = xcli_config_path()
    default_file.write_text("log_level: INFO\n", encoding="utf-8")

    # Env override says DEBUG
    override_file = tmp_path / "override.yaml"
    override_file.write_text("log_level: DEBUG\n", encoding="utf-8")
    monkeypatch.setenv("XCLI_CONFIG", str(override_file))

    cfg = AppConfig.from_env_and_default()
    assert cfg.log_level == "DEBUG"


def test_priority_default_file_beats_hardcoded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Default ``config.yaml`` exists + no env → file wins over hardcoded."""
    _isolate_env(monkeypatch, tmp_path)

    default_file = xcli_config_path()
    default_file.write_text("log_level: ERROR\n", encoding="utf-8")

    cfg = AppConfig.from_env_and_default()
    assert cfg.log_level == "ERROR"


# ============================================================
#  xcli_config_path / xcli_log_path helpers
# ============================================================


def test_xcli_config_path_lives_under_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``xcli_config_path()`` resolves to ``<data_dir>/config.yaml``."""
    _isolate_env(monkeypatch, tmp_path)

    assert xcli_config_path() == xcli_data_dir() / "config.yaml"


def test_xcli_log_path_lives_under_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``xcli_log_path()`` resolves to ``<data_dir>/x.log``."""
    _isolate_env(monkeypatch, tmp_path)

    assert xcli_log_path() == xcli_data_dir() / "x.log"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))