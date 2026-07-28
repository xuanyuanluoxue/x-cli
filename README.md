# x-cli

> A small personal CLI toolset for tasks, credentials, daily records, topic notes, and a local web UI.
> One `x` command, five subsystems, zero runtime dependencies.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](tests/)
[![Coverage: 80%+](https://img.shields.io/badge/coverage-80%25%2B-brightgreen.svg)](tests/)

## What is x-cli?

A single binary `x` that ships five focused subsystems:

- **`x todo`** — Personal TODO management backed by YAML-frontmatter Markdown files.
  Full lifecycle: add, list, update, archive, restore, search, done, stats, init, import.
  CJK-friendly (中文 task names supported). Audit trail (archived tasks are never deleted).
- **`x secret`** — Local multi-field credential store backed by one JSON file (POSIX mode 600).
  Keep URLs, account names, and masked secret fields together; the CLI auto-copies the selected field.
- **`x diary`** — Local daily Markdown notes. Append an entry or list recent diary dates.
- **`x note`** — Topic-oriented Markdown notes with tags and local search.
- **`x web`** — Local web UI for todo and secret data; Token auth is opt-in.

The data subsystems store data **independently** under per-user data directories:

| Platform | TODO | Secrets | Diary | Notes |
|---|---|---|---|---|
| Windows | `%LOCALAPPDATA%\x-cli\todo\` | `%LOCALAPPDATA%\x-cli\secrets.json` | `%LOCALAPPDATA%\x-cli\diary\` | `%LOCALAPPDATA%\x-cli\notes\` |
| Unix | `$XDG_DATA_HOME/x-cli/todo/` | `$XDG_DATA_HOME/x-cli/secrets.json` | `$XDG_DATA_HOME/x-cli/diary/` | `$XDG_DATA_HOME/x-cli/notes/` |

No cloud sync, no telemetry, no encryption (yet). Designed for one user, one machine.

## Install

### WinGet (planned public channel)

> **Status:** x-cli is not yet available in the default WinGet source. The
> The public [v0.7.0 GitHub Release](https://github.com/xuanyuanluoxue/x-cli/releases/tag/v0.7.0)
> is available. Submission to the default WinGet source is still pending.

After Microsoft accepts the package, Windows users will install and upgrade it
without installing Python:

```powershell
winget install --id XuanyuanLuoxue.XCLI -e
winget upgrade --id XuanyuanLuoxue.XCLI -e
```

The portable EXE stores user data under `%LOCALAPPDATA%\x-cli\`; upgrading the
program does not replace todo, secret, diary, or note data.

### Development install

```bash
git clone https://github.com/xuanyuanluoxue/x-cli.git
cd x-cli
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # Unix
.venv\Scripts\pip install -e ".[dev]"  # Windows

x --version
x todo --help
x todo add "驾照考取" --priority high --deadline 2026-08-31
x diary "Started using x diary"
x note add "MiniMax API setup" --body "Configuration details" --tags AI,API
```

Top-level and subcommand help are separate: `x --help`, `x todo --help`,
`x secret --help`, `x diary --help`, `x note --help`, and `x web --help` all
show the relevant command scope.

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
x secret get minimax                                  # primary secret → clipboard + stdout + stderr warning
x secret get webdav --field URL                       # retrieve a named text/secret field
x secret set minimax --value sk-xxx --category 接口密钥
x secret update minimax --value sk-new --note "rotated 2026-06"  # updates the primary secret
x secret rm oldkey                                     # delete
x secret search api                                    # name + note, NEVER value
x secret import --from /path/to/legacy-markdown-dir   # one-way, source preserved
x secret export                                        # JSON backup
```

**Hard invariants** (enforced by the CLI, do not violate):

- `x secret list` NEVER shows any field value. Test: `test_e2e_list_never_shows_value`.
- `x secret get` ALWAYS writes a stderr warning before stdout. Test: `test_e2e_get_returns_value`.
- `x secret search` NEVER matches against field values. Test: `test_e2e_search_does_not_match_value`.
- `x secret import` is read-only — source files are never modified.

The Web UI can add, remove, reorder, and replace 1–50 named fields. Each field is
either plain text or a masked secret, and exactly one secret field is the primary
CLI value. Legacy schema 1.0 files remain readable; the first write creates a
timestamped backup before upgrading the database to schema 1.1. Values are still
stored as plaintext JSON—the mask only controls browser display.

The JSON DB has file mode `0600` on POSIX. On Windows the ACL is inherited
from the user's profile (no special hardening beyond that). For encryption
at rest, see [Roadmap](#roadmap).

### `x diary` — local daily notes

```bash
x diary "Finished the x diary P0 implementation"  # append to today's Markdown file
x diary list                                       # latest 7 diary dates
x diary list --limit 3                             # custom result count
```

Diary files live under `<xcli_data_dir>/diary/YYYY-MM-DD.md`. Set
`XCLI_DIARY_DIR` to use a different directory. P0 lists dates only; it does
not edit, delete, search, or sync entries.

### `x note` — topic notes

```bash
x note add "MiniMax API setup" --body "Configuration details" --tags AI,API
x note list --tag AI --limit 10
x note show n-20260717-143012
x note search minimax --limit 5
```

Each note is stored at `<xcli_data_dir>/notes/<id>.md` with YAML frontmatter
and a Markdown body. Set `XCLI_NOTES_DIR` to use a different directory.
P0 is read-mostly: create, list, show, and search; editing and deletion are
left for a later version.

### `x web` — local browser UI

```bash
x web                       # default: 127.0.0.1:8421, no Token prompt
x web --no-browser          # start without opening the browser
x web --token my-token      # explicitly enable auth for this run
```

The default config keeps `web_auth: false`, so the loopback-only browser UI
opens directly. To require a random startup Token, edit
`<xcli_data_dir>/config.yaml` (Windows: `%LOCALAPPDATA%\x-cli\config.yaml`):

```yaml
web_auth: true
```

Keep authentication enabled when binding to a non-loopback host; otherwise
any device that can reach the server can read and modify todo and secret data.

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
| [docs/releasing.md](docs/releasing.md) | Windows build, GitHub Release, and WinGet submission runbook |
| [docs/commands.md](docs/commands.md) | Full command reference (mirror of `COMMANDS.md`) |
| [docs/behaviors/](docs/behaviors/) | Durable BDD specs (Given-When-Then) |
| [AGENTS.md](AGENTS.md) | Rules for AI agents working on x-cli |

## Development

```bash
# Tests
.venv/bin/pytest                                   # Unix
.venv\Scripts\python.exe -m pytest                 # Windows
.venv\Scripts\python.exe -m pytest --cov=core --cov=plugins --cov=x --cov-fail-under=80
.venv\Scripts\python.exe -m ruff check core plugins x.py scripts tests

# ⚠️ Windows pytest tmpdir workaround (2026-06-30):
# If pytest fails with `PermissionError: [WinError 5]` on
# `C:\Users\...\AppData\Local\Temp\pytest-of-...\pytest-current`,
# override TMP/TEMP to a writable path:
$env:TMP = "D:\Temp\pytest_tmp"
$env:TEMP = "D:\Temp\pytest_tmp"
# (root cause: some process holds the default tmp dir open,
#  suppressing the actual test failure detail with a cleanup traceback.)

# Risk-based workflow
# Small: no plan; focused regression test when behavior changes
# Medium: short plan; BDD for user behavior; TDD; full suite once at handoff
# High-risk: full plan + ADR when needed; full suite + relevant release/security checks
```

See [AGENTS.md](AGENTS.md) for the exact classification and mandatory checks.
`COMMANDS.md` remains the user-owned feature specification.

### Web frontend (Vue 3 + Vite)

The browser UI is a Vue 3 SPA. Its **source** lives in [`web/`](web/) and its
**build artifacts** are emitted into `core/web/static/` (served by the Python
HTTP server). Python runtime stays stdlib-only — Node is a *dev-time* tool only.

```bash
cd web
npm ci             # install exactly from package-lock.json
npm run dev        # Vite dev server (proxies /api → 127.0.0.1:8421, run `x web` first)
npm run build      # → outputs to ../core/web/static
```

Build artifacts are **committed to git** so `pip install` works without Node.
After changing anything under `web/src/`, re-run `npm run build` before tests
or packaging. See [ADR-0002](docs/architecture-decisions/0002-web-frontend-vue-vite.md).

## Roadmap

**Done in the current v0.8.0 development tree:**
- TODO lifecycle, time precision, subtasks, reminders, repeat rules, batch operations, templates, dependencies, recycle-bin removal, and JSON/CSV/Markdown export
- Secret storage with protected list/search output and clipboard integration
- Local diary entries, topic notes, and the optional-auth Web UI
- Single-source version shared by CLI, Python metadata, EXE, and WinGet manifest
- PyInstaller Windows x64 portable EXE with packaged Web assets
- Reproducible SHA-256 and WinGet 1.12.0 manifest generation
- GitHub Actions build/release workflow with tag-version protection

**Next** (post-v0.8 candidates, not committed):
- Encrypted-at-rest secret store (currently plain JSON)
- Git-based version control of the TODO directory (`git init` + auto-commit hooks)
- Optional background daemon for reminders and AI-assisted local workflows

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

---

## 协作开发规范

项目采用 `main` 单主干开发：

1. `main` 是唯一长期分支，始终保持测试通过和可发布；禁止直接推送。
2. 从最新 `origin/main` 创建短期 `feature/<name>` 或 `fix/<name>` 分支。
3. PR 统一以 `main` 为目标，检查通过并审查后默认 squash merge。
4. 合并后删除短期分支，不再维护长期 `dev` 或 release 分支。
5. 提交信息使用中文 `类型(模块): 描述`。

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/your-feature-name
```

Web 前端只修改 `web/` 源码，并使用 `npm ci && npm run build` 生成需要一同
提交的 `core/web/static/`。CI 会运行全量 Python 测试，并重新构建 Web 检查
源码、锁文件和静态产物是否一致。

完整流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，持久决策见
[ADR 0006](docs/architecture-decisions/0006-mainline-development-and-reproducible-web-builds.md)。

感谢您的配合！🙏
