# x-cli

> A small personal CLI toolset for tasks, credentials, daily records, topic notes, and a local web UI.
> One `x` command, five subsystems, zero runtime dependencies.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](tests/)
[![Coverage: 93%](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)](tests/)

## What is x-cli?

A single binary `x` that ships five focused subsystems:

- **`x todo`** — Personal TODO management backed by YAML-frontmatter Markdown files.
  Full lifecycle: add, list, update, archive, restore, search, done, stats, init, import.
  CJK-friendly (中文 task names supported). Audit trail (archived tasks are never deleted).
- **`x secret`** — Local credential store backed by a single JSON file (POSIX mode 600).
  list / get / set / update / rm / search / import / export. Auto-copies to clipboard.
- **`x diary`** — Local daily Markdown notes. Append an entry or list recent diary dates.
- **`x note`** — Topic-oriented Markdown notes with tags and local search.
- **`x web`** — Authenticated local web UI for the todo and secret data.

The data subsystems store data **independently** under per-user data directories:

| Platform | TODO | Secrets | Diary | Notes |
|---|---|---|---|---|
| Windows | `%LOCALAPPDATA%\x-cli\todo\` | `%LOCALAPPDATA%\x-cli\secrets.json` | `%LOCALAPPDATA%\x-cli\diary\` | `%LOCALAPPDATA%\x-cli\notes\` |
| Unix | `$XDG_DATA_HOME/x-cli/todo/` | `$XDG_DATA_HOME/x-cli/secrets.json` | `$XDG_DATA_HOME/x-cli/diary/` | `$XDG_DATA_HOME/x-cli/notes/` |

No cloud sync, no telemetry, no encryption (yet). Designed for one user, one machine.

## Install

### WinGet (planned public channel)

> **Status:** x-cli is not yet available in the default WinGet source. The
> manifest and release pipeline are ready locally, but the first public GitHub
> Release and `microsoft/winget-pkgs` submission have not been made yet.

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
.venv\Scripts\python.exe -m pytest --cov=core --cov=x  # with coverage

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

## Roadmap

**Done in the current local v0.7.0 tree:**
- TODO lifecycle, time precision, subtasks, reminders, repeat rules, batch operations, templates, dependencies, recycle-bin removal, and JSON/CSV/Markdown export
- Secret storage with protected list/search output and clipboard integration
- Local diary entries, topic notes, and the authenticated Web UI
- Single-source version shared by CLI, Python metadata, EXE, and WinGet manifest
- PyInstaller Windows x64 portable EXE with packaged Web assets
- Reproducible SHA-256 and WinGet 1.12.0 manifest generation
- GitHub Actions build/release workflow with tag-version protection

**Next** (post-v0.7 candidates, not committed):
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

为确保代码质量和项目管理规范，所有协作者必须遵守以下规则：

### 🔒 分支权限规则

1. **禁止直接提交到 main 分支**
   - 所有协作者禁止直接向 `main` 主分支提交代码
   - 禁止向 `main` 分支发起合并请求（Pull Request）
   - `main` 分支仅用于正式版本发布

2. **基于 dev 分支开发**
   - 所有功能开发、问题修复，必须基于公共 `dev` 分支创建个人功能分支
   - 分支命名规范：`feature/功能描述` 或 `fix/问题描述`
   - 示例：`feature/add-note-parameter`、`fix/secret-list-bug`

3. **禁止直接推送到 dev 分支**
   - 开发完成后，仅允许向公共 `dev` 分支提交 Pull Request (PR)
   - 禁止以任何方式直接推送代码到 `dev` 分支
   - 所有 PR 必须经过代码审查流程

4. **PR 审查规则**
   - 所有合入 `dev` 分支的 PR，必须经仓库管理员审核通过后方可合并
   - 至少 1 名管理员 Approve 才能合并
   - PR 必须关联相关的 Issue（如适用）

5. **main 分支发布规则**
   - `main` 分支仅用于正式版本发布
   - 由管理员统一从验证通过的 `dev` 分支合入
   - 普通协作者无操作权限

### 📋 开发流程

1. **Fork 仓库**（如适用）
   - Fork 整个仓库到个人账号
   - 设置个人仓库的默认分支为 `dev`

2. **创建功能分支**
   ```bash
   git clone https://github.com/YOUR_USERNAME/x-cli.git
   cd x-cli
   git checkout dev
   git pull upstream dev
   git checkout -b feature/your-feature-name
   ```

3. **开发和提交**
   - 遵循现有代码规范
   - 为新功能添加测试
   - 更新相关文档
   - 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范

4. **提交 PR**
   - 推送到个人 Fork 的 `dev` 分支
   - 创建 PR，目标分支设置为上游仓库的 `dev`
   - 填写完整的 PR 描述
   - 等待管理员审查

### ⚠️ 违规处理

- 违反上述规则的 PR 将被直接关闭
- 多次违规的协作者可能被限制仓库访问权限
- 如有特殊需求，请先与管理员沟通

---

**管理员联系方式**：[xavier.pen@example.com](mailto:xavier.pen@example.com)

感谢您的配合！🙏
