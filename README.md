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

# ⚠️ Windows pytest tmpdir workaround (2026-06-30):
# If pytest fails with `PermissionError: [WinError 5]` on
# `C:\Users\...\AppData\Local\Temp\pytest-of-...\pytest-current`,
# override TMP/TEMP to a writable path:
$env:TMP = "D:\Temp\pytest_tmp"
$env:TEMP = "D:\Temp\pytest_tmp"
# (root cause: some process holds the default tmp dir open,
#  suppressing the actual test failure detail with a cleanup traceback.)

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

**Done** (v0.5.0 partial — Phase A & B landed):
- P0 time precision: `--time HH:MM` / `--end-time HH:MM` / `--duration 90|90m|1.5h`
- P1 subtasks: `--parent <id>` (2 levels) with cascade archive
- 607 tests passing, 1 platform-conditional skip, see [PLAN-v0.5.md](PLAN-v0.5.md) for remaining scope

**Done** (v0.4.y):
- 21 commands across `x todo` (10) and `x secret` (8) plus 3 global flags
- 526 tests passing, 4 platform-conditional skips, 93% coverage
- CJK task names + icons in output
- Clipboard integration on `x secret get`
- Configurable log level + log path
- One-way import from a legacy TODO directory / 密钥 Markdown directory

**Next** (v0.5.0 remaining — Phase C/D/E):
- P1 reminders (read-only in v0.5; daemon in v0.6+ after exe packaging)
- P2 recurring tasks (`--repeat` + explicit `repeat-fire`), batch ops, list sorting, `urgent` priority with ANSI red highlight, recycle bin
- P3 templates, task dependencies, JSON/CSV/MD export
- See [PLAN-v0.5.md](PLAN-v0.5.md) §5 implementation phases

**Next** (v0.6+ candidates, not committed):
- Encrypted-at-rest secret store (currently plain JSON)
- Git-based version control of the TODO directory (`git init` + auto-commit hooks)
- PyInstaller single-file binary distribution (pre-req for reminder daemon)

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
