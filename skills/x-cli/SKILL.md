---
name: x-cli
description: Use when an agent needs to operate the x-cli personal CLI toolset on behalf of the user — running `x todo` to manage tasks (add/list/update/archive/restore/search/done/stats/init/import) or `x secret` to manage credentials (list/get/set/update/rm/search/import/export), installing x-cli on a new machine, troubleshooting a failed x-cli command, interpreting x-cli output (CJK task names, exit codes, auto-archive summaries), or migrating data from the user's legacy TODO / 密钥 Markdown directory. Skip for: x-cli development tasks (use AGENTS.md instead).
---

# x-cli — Personal CLI Toolset

## Overview

x-cli is a small personal CLI built around two subsystems. Zero third-party deps, stdlib only.

- **`x todo`** — task tracking backed by YAML-frontmatter Markdown files (CJK task names supported)
- **`x secret`** — local credential store backed by a single JSON file (POSIX mode 600)

Both subsystems store data **independently** under per-user data directories. No cloud sync, no telemetry, no encryption (yet). Designed for one user (xavier), one machine.

## When to Use This Skill

Load this skill when:

- The user says "x todo …" / "x secret …" / "x --version" / "用 x …"
- The user asks to add a task, list pending work, archive a finished task, search tasks, mark something done
- The user wants a credential value (will auto-copy to clipboard)
- The user wants to migrate from the legacy TODO system or legacy 密钥 Markdown directory
- An x-cli command failed and you need to interpret the exit code or error message
- The user asks to install x-cli on a new machine (venv, PATH)

Do **not** load for: x-cli development tasks (modifying code, adding commands, BDD specs). For development, read `AGENTS.md` and `COMMANDS.md` instead.

## Quick Start

### Install on a new machine

```bash
git clone https://github.com/xavier-pen/x-cli
cd x-cli
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"          # Windows
.venv/bin/pip install -e ".[dev]"              # Unix
```

**Why a venv (Windows + Python 3.14):** the system Python on xavier's machine gets `hydra-core` / `antlr4` auto-loaded as pytest plugins, which breaks the test suite. The venv is clean.

**PATH gotcha (Windows):** the venv installs `x.exe` at `.venv\Scripts\x.exe`. If `x` is not found, either:

- Add `.venv\Scripts` to user PATH, **or**
- Create a wrapper at `C:\Users\x-cli\.local\bin\x.bat` that forwards to the venv exe.

### Verify + first commands

```bash
x --version               # → x 0.6.0
x                         # prints top-level help
x help                    # alias for `x --help`
x todo list               # active tasks (empty repo prints 📭)
x secret list             # lists names + categories only — NEVER values
```

## Core Commands

### `x todo` — task management

```bash
# Lifecycle
x todo add "科目一模拟考" --priority high --deadline 2026-08-31 --tags 驾照,暑假
x todo list                                              # active only
x todo list --all                                        # active + archived
x todo list --status in_progress --priority high         # filters (AND)
x todo list --tag 驾照                                   # tag filter
x todo update <id> --status in_progress                  # need ≥1 --xxx
x todo update <id> --priority high --deadline 2026-07-01
x todo update <id> --tags 驾照,考试                      # REPLACE, not merge
x todo update <id> --deadline ""                         # clear deadline
x todo archive <id> --reason done                        # soft-delete
x todo archive <id> --reason cancelled|expired|failed    # English enum only
x todo done <id>                                         # shortcut: archive --reason done
x todo restore <id>                                      # archive → active

# Search + stats
x todo search "keyword"                                  # name + note + tags
x todo search "keyword" --active-only
x todo search "keyword" --archived-only --status in_progress
x todo stats                                             # by status/priority/due-soon

# Setup
x todo init --dir /path/to/seed                          # bootstrap a store
x todo import --from /path/to/legacy --dry-run           # one-way, source preserved
x todo import --from /path/to/legacy --to /path/to/x-cli-store
```

**ID rules:**
- Chinese name → pinyin first letters + numeric suffix (e.g. `科目一模拟考` → `kemu1`)
- English name → kebab-case (e.g. `Setup Blog` → `setup-blog`)
- Collision → auto-suffix `-2`, `-3`, …

**Status values:** `pending` / `in_progress` / `blocked` / `waiting` / `archived`
**Priority values:** `high` / `medium` / `low`
**Archive reasons:** `done` / `cancelled` / `expired` / `failed` (English only — `--reason "已完成"` will be rejected)

### `x secret` — credential store

```bash
x secret list                              # names + categories only (NEVER values)
x secret list --category 接口密钥          # filter (case-insensitive)
x secret get <name>                        # clipboard + stdout + stderr warning
x secret get <name> --no-stdout            # clipboard only
x secret get <name> --no-clipboard         # stdout only
x secret set <name> --value <v> [--category <c>] [--note <n>]
x secret update <name> --value|--note|--category   # at least one
x secret rm <name>
x secret search <keyword>                  # name + note only (NEVER value)
x secret import --from <dir>               # from .md files, source preserved
x secret export --to <path>                # JSON backup
```

**Hard invariants** (do not violate when scripting around x-cli):

- `x secret list` NEVER shows values. (Don't `> log.txt` it expecting values — they aren't there.)
- `x secret get` ALWAYS writes a stderr warning before stdout. (This is intentional. If you need the value silently, use `--no-stdout` to skip the stdout echo and rely on clipboard.)
- `x secret search` NEVER matches against the `value` field.
- `x secret import` is read-only — source files are never modified.

### Global flags

```bash
x --version                  # print version, exit 0
x --config /path/to/config.yaml     # load YAML config (priority over env)
x --log-level DEBUG          # override log level for one invocation
x --config-init              # write default config to <xcli_data_dir>/config.yaml
x help                       # alias for `x --help`
x <sub> help                 # alias for `x <sub> --help`
```

## Storage Layout

| Subsystem | Windows | Unix | Env override |
|---|---|---|---|
| TODO | `%LOCALAPPDATA%\x-cli\todo\` | `~/.local/share/x-cli/todo/` | `XCLI_TODO_DIR` |
| Secret | `%LOCALAPPDATA%\x-cli\secrets.json` | `~/.local/share/x-cli/secrets.json` | `XCLI_SECRETS_DIR` |
| Config | `%LOCALAPPDATA%\x-cli\config.yaml` | `~/.local/share/x-cli/config.yaml` | `XCLI_CONFIG` |
| Log | `%LOCALAPPDATA%\x-cli\x.log` | `~/.local/share/x-cli/x.log` | (config: `log.path`) |

Config priority chain: `CLI --config` > `XCLI_CONFIG` env > `<xcli_data_dir>/config.yaml` > hardcoded defaults.

**On-disk structure (TODO):**

```
<xcli_todo_dir>/
├── 任务/<name>/TODO.md                # active task (CJK folder names OK)
└── 归档/<YYYYMMDD>-<name>/TODO.md     # archived task (date prefix = archive date)
```

Each `TODO.md` is YAML frontmatter + free-form Markdown body. The body is preserved verbatim — use it as the user's notebook.

**On-disk structure (Secret):** single JSON file (`{"version": "1.0", "secrets": [...]}`). Mode 0600 on POSIX.

**Auto-archive (opt-in):** set `todo.auto_archive: true` in config or `XCLI_TODO_AUTO_ARCHIVE=1`. On `list` / `stats` / `search`, any active task with `deadline < today()` is auto-archived (`reason=expired`) before the query runs. A summary line `⏰ 自动归档 N 个逾期任务：id1 / id2 / ...` prints to stdout top when N>0. Search auto-suppresses just-archived tasks from the default results unless `--archived-only` is passed (search-leak protection).

## Exit Codes

| Code | Meaning | Typical trigger |
|---|---|---|
| 0 | Success | (also: empty repo / no match) |
| 1 | Generic / unknown subcommand | `x foo`; placeholder action |
| 2 | Arg error | bad status/priority/reason/deadline; missing required `--xxx`; `secret update` without `--value/--note/--category` |
| 3 | Not found | `update/archive/restore/get/rm` with unknown id |
| 4 | Already in state | double `archive`; `update` on archived task; `set` on existing name |
| 5 | Data integrity | YAML parse failure; archive target collision; broken JSON; import source missing |
| 6 | Logging init failure | `setup_logging` raised |

When scripting: treat 0 as success, 2 as "fix the call", 3/4/5 as "user input or data issue, surface the message", 6 as "infra issue, check log path perms".

## Migration from Legacy Systems

The user has an older TODO + 密钥 Markdown system (`<legacy-config-dir>/TODO/`, `<legacy-credentials-dir>/`). One-way import is available:

```bash
# Preview first — never write until --dry-run looks right
x todo import --from "<legacy-config-dir>/TODO" --dry-run
x todo import --from "<legacy-config-dir>/TODO" --to "<xcli_todo_dir>"

x secret import --from "<legacy-credentials-dir>" --dry-run
x secret import --from "<legacy-credentials-dir>"
```

**Both importers are read-only on the source.** The user keeps the old data untouched. After import, the user can verify with `x todo list --all` / `x secret list` and manually delete the legacy tree once satisfied.

## Running and Debugging

### Where's my data?

```bash
# Windows
explorer "$env:LOCALAPPDATA\x-cli\"
# Unix
ls -la ~/.local/share/x-cli/
```

### Tail the log

```bash
# PowerShell
Get-Content "$env:LOCALAPPDATA\x-cli\x.log" -Tail 50 -Wait
# Unix
tail -F ~/.local/share/x-cli/x.log
```

### Reset to a clean state (last resort)

```bash
# Windows — DESTRUCTIVE: deletes all tasks, secrets, config, log
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\x-cli\"
# Confirm with user before running.
```

Never run this without explicit user confirmation.

### Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `x` command not found | venv `Scripts/` not on PATH | add `.venv\Scripts` to user PATH, or create `x.bat` wrapper |
| `ModuleNotFoundError: x` / `plugins` / `core` | ran from wrong dir or venv not activated | `cd x-cli && .venv\Scripts\activate` (Win) / `source .venv/bin/activate` (Unix) |
| `❌ 配置已存在：...` from `x --config-init` | file already there | delete it, or wait for `--force` (P1 backlog) |
| `❌ 任务不存在：kemu99` | typo / wrong id | `x todo list` to see valid ids |
| `❌ 非法 priority: urgent` | `urgent` not yet supported | use `high` (current options); `urgent` is on the v0.5 P2 backlog |
| `x secret get` prints to terminal unexpectedly | by design | `get` always warns + echoes to stdout; use `--no-stdout` to suppress echo |
| `x secret list` output has no `value` column | by design | values are NEVER shown by `list`; use `x secret get <name>` to retrieve |
| Task created with wrong tags | `x todo update --tags` REPLACES, doesn't merge | re-run with all desired tags: `--tags 驾照,考试,2026` |
| Search returns nothing but task exists | search is fuzzy over name+note+tags only | check exact spelling; or use `x todo list --all` and grep |
| `⏰ 自动归档 N 个逾期任务：...` appears unexpectedly | `auto_archive` opt-in is on, deadline passed | expected behavior; pass `XCLI_TODO_AUTO_ARCHIVE=0` for the call to suppress |

### Windows `TMP/TEMP` note (only relevant if user runs the dev test suite)

The pytest suite can fail with `PermissionError: [WinError 5]` on `C:\Users\...\AppData\Local\Temp\pytest-of-...\pytest-current`. Workaround: `$env:TMP = "D:\Temp\pytest_tmp"; $env:TEMP = "D:\Temp\pytest_tmp"`. **This does not affect `x` itself — only the dev test suite.** If the user reports an error from `x` (not pytest), this is not the cause.

## Output Format Notes

- Success messages start with `✅`; errors with `❌`; warnings with `⏰` / `💡`.
- Tables are tab-separated with CJK-aware column padding (no garbled alignment for `归档` etc.).
- CJK task names flow through unchanged in `list` output, file paths, and IDs (IDs use pinyin first letters, e.g. `kemu1`).
- Archive status appears as `archived (done)` / `archived (cancelled)` etc. in the Status column.
- `x secret get` writes in this order: stderr warning line → stdout value → done. If you capture stdout programmatically, the stderr warning is a separate stream.

## Related

| Doc | Purpose |
|---|---|
| [`README.md`](../../README.md) | Project overview + install (English) |
| [`README.zh.md`](../../README.zh.md) | Project overview (Chinese) |
| [`COMMANDS.md`](../../COMMANDS.md) | Canonical command inventory — `✅` implemented, `⏳` backlog, `❌` not wanted |
| [`docs/commands.md`](../../docs/commands.md) | Full command reference with exit-code detail |
| [`docs/behaviors/`](../../docs/behaviors/) | BDD Given-When-Then specs (64 scenarios) — reference for edge cases |
| [`docs/TODO-SPEC.md`](../../docs/TODO-SPEC.md) | On-disk format for `x todo` (YAML frontmatter + body) |

For x-cli **development** (modifying code, adding commands), read `AGENTS.md` instead — this skill is for usage only.

---

*Last synced with v0.6.0 source (2026-06-21). When COMMANDS.md changes (new `✅` row), update §Core Commands and §Storage Layout here too.*
