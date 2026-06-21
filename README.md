# x-cli

> A small personal CLI toolset for **task tracking** and **credential management**.
> One `x` command, two subsystems, zero third-party dependencies.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests: 526](https://img.shields.io/badge/tests-526%20passing-brightgreen.svg)](tests/)
[![Coverage: 93%](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)](tests/)

## What is x-cli?

A single binary `x` that ships two focused subsystems:

- **`x todo`** — Personal TODO management backed by YAML-frontmatter Markdown files.
  Full lifecycle: add, list, update, archive, restore, search, done, stats, init, import.
  CJK-friendly (中文 task names supported). Audit trail (archived tasks are never deleted).
- **`x secret`** — Local credential store backed by a single JSON file (POSIX mode 600).
  list / get / set / update / rm / search / import / export. Auto-copies to clipboard.

Both subsystems store data **independently** under per-user data directories:

| Platform | TODO | Secrets |
|---|---|---|
| Windows | `%LOCALAPPDATA%\x-cli\todo\` | `%LOCALAPPDATA%\x-cli\secrets.json` |
| Unix | `$XDG_DATA_HOME/x-cli/todo/` | `$XDG_DATA_HOME/x-cli/secrets.json` |

No cloud sync, no telemetry, no encryption (yet). Designed for one user, one machine.

## Quick start

```bash
# Clone and install (editable mode, source changes take effect immediately)
git clone https://github.com/xavier-pen/x-cli
cd x-cli

# Use a virtualenv — Python 3.14 system-wide installs can be polluted by
# hydra-core / antlr4 (auto-loaded as pytest plugins).
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # Unix
.venv\Scripts\pip install -e ".[dev]"  # Windows

# Verify
x --version
x todo --help        # Hmm — see "Known quirks" below

# Try it out
x todo add "驾照考取" --priority high --deadline 2026-08-31
x todo list
x todo stats
```

### Known quirks

- **`x --help` and `x todo --help` return the same top-level help.** The outer
  argparse parser swallows `--help` before the subcommand dispatcher. To see
  the action list for a subcommand, run `x todo` (no args) or `x secret`
  (no args). See [docs/behaviors/e2e-cli-behavior.md](docs/behaviors/e2e-cli-behavior.md).
- **`x` must be on your PATH.** On Windows, the venv-installed `x.exe`
  lives at `.venv\Scripts\x.exe`. If that directory is not on your PATH,
  add it (or wrap it in `C:\Users\X\.local\bin\x.bat`).

## Usage

### `x todo` — task management

```bash
# Lifecycle
x todo add "科目一模拟考" --priority high --deadline 2026-08-31 --tags 驾照,暑假
x todo list                                            # active only
x todo list --all                                      # active + archived
x todo list --status in_progress --priority high       # filters
x todo update kemu1 --status in_progress
x todo archive kemu1 --reason done                     # soft-delete to archive
x todo done kemu1                                      # shortcut: archive --reason done
x todo restore kemu1                                   # archive → active
x todo search 暑假                                      # name + note + tags
x todo stats                                           # by status / priority / due-soon
x todo init --dir /path/to/seed                        # bootstrap a store
x todo import --from /path/to/legacy --dry-run         # one-way migration
```

Each task lives in its own folder:

```
<xcli_todo_dir>/
├── 任务/<name>/TODO.md              # active task (one .md per task)
└── 归档/<YYYYMMDD>-<name>/TODO.md   # archived task (date prefix = archive date)
```

The Markdown body (after the YAML frontmatter) is preserved verbatim — use
it as your notebook. Unknown frontmatter fields round-trip on save. See
[docs/TODO-SPEC.md](docs/TODO-SPEC.md) for the full format.

### `x secret` — credential store

```bash
x secret list                                         # names + categories only (NEVER values)
x secret get minimax                                  # writes value to clipboard + stdout + stderr warning
x secret set minimax --value sk-xxx --category 接口密钥
x secret update minimax --value sk-new --note "rotated 2026-06"
x secret rm oldkey                                     # delete
x secret search api                                    # name + note, NEVER value
x secret import --from /path/to/legacy-markdown-dir   # one-way, source preserved
x secret export                                        # JSON backup
```

**Hard invariants** (enforced by the CLI, do not violate):

- `x secret list` NEVER shows values. Test: `test_e2e_list_never_shows_value`.
- `x secret get` ALWAYS writes a stderr warning before stdout. Test: `test_e2e_get_returns_value`.
- `x secret search` NEVER matches against the `value` field. Test: `test_e2e_search_does_not_match_value`.
- `x secret import` is read-only — source files are never modified.

The JSON DB has file mode `0600` on POSIX. On Windows the ACL is inherited
from the user's profile (no special hardening beyond that). For encryption
at rest, see [Roadmap](#roadmap).

### Global flags

```bash
x --version                  # show version and exit
x --config /path/to/config.yaml     # load YAML config (priority over env vars)
x --log-level DEBUG          # override log level for one invocation
x --config-init              # write default config to <xcli_data_dir>/config.yaml
```

Config priority chain: `CLI --config > XCLI_CONFIG env > <xcli_data_dir>/config.yaml > hardcoded defaults`.

## Why?

This tool exists because I needed a single command that could:

1. Manage a personal TODO list with CJK task names, deadlines, tags, and an audit trail (archived tasks stay around).
2. Store API keys locally with a usable CLI (`x secret get foo` → clipboard).
3. Stay out of my way (no cloud, no telemetry, no third-party deps).

It grew out of a longer-running legacy TODO + 密钥 Markdown system that
required manual index regeneration. The migration path is preserved
via `x todo import --from <dir>` and `x secret import --from <dir>`,
both one-way and read-only.

## Documentation

| Doc | Purpose |
|---|---|
| [COMMANDS.md](COMMANDS.md) | Canonical command inventory (user-edited spec source) |
| [docs/TODO-SPEC.md](docs/TODO-SPEC.md) | On-disk format spec for `x todo` |
| [docs/architecture.md](docs/architecture.md) | Design decisions, storage layers, hard invariants |
| [docs/commands.md](docs/commands.md) | Full command reference (mirror of `COMMANDS.md`) |
| [docs/behaviors/](docs/behaviors/) | BDD specs (Given-When-Then) — 14 files, 100+ scenarios |
| [AGENTS.md](AGENTS.md) | Rules for AI agents working on x-cli |

## Development

```bash
# Tests
.venv/bin/pytest                                   # Unix
.venv\Scripts\python.exe -m pytest                 # Windows
.venv\Scripts\python.exe -m pytest --cov=core --cov=x  # with coverage

# BDD-first, commit-before-code workflow
# (1) Edit COMMANDS.md to add a command to the "⏳ Implemented" or backlog section
# (2) Write BDD spec in docs/behaviors/<command>-behavior.md
# (3) Commit the spec (single doc commit)
# (4) Write tests in tests/test_<command>.py  → run, see Red
# (5) Implement in x.py or core/*.py        → run, see Green
# (6) Commit implementation + tests
```

See [AGENTS.md](AGENTS.md) for the full dev conventions, including the
"COMMANDS.md is the spec source" rule.

## Roadmap

**Done** (v0.4.y, current):
- 21 commands across `x todo` (10) and `x secret` (8) plus 3 global flags
- 526 tests passing, 4 platform-conditional skips, 93% coverage
- CJK task names + icons in output
- Clipboard integration on `x secret get`
- Configurable log level + log path
- One-way import from a legacy TODO directory / 密钥 Markdown directory

**Next** (candidates, not committed):
- Encrypted-at-rest secret store (currently plain JSON)
- Git-based version control of the TODO directory (`git init` + auto-commit hooks)
- Plugin split (`plugins/todo.py` extracted from `x.py`)
- PyInstaller single-file binary distribution

**Won't** (by design):
- Cloud sync, multi-device support
- Team / multi-user features
- Interactive TUI (plain stdout + tables is sufficient)

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Xavier.

## Contributing

This tool is small and personal. Bug reports and PRs are welcome —
please open an issue first if you're planning a non-trivial change so
we can discuss the design before code is written. AI agents reading
this repo **must** start by reading [AGENTS.md](AGENTS.md).