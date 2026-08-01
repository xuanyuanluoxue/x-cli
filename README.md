# x-cli

> One local `x` command for tasks, credentials, diaries, notes, and a browser UI.
> Python 3.10+, zero runtime dependencies, Windows standalone EXE available.

[![CI](https://github.com/xuanyuanluoxue/x-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/xuanyuanluoxue/x-cli/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/xuanyuanluoxue/x-cli)](https://github.com/xuanyuanluoxue/x-cli/releases/latest)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

[中文说明](README.zh.md)

## Release status

**v0.8.0 is available now:** [release notes and downloads](https://github.com/xuanyuanluoxue/x-cli/releases/tag/v0.8.0).

The WinGet submission is [under Microsoft review](https://github.com/microsoft/winget-pkgs/pull/403912).
The public install command will be added here only after the package is merged
and confirmed in the default WinGet source.

Windows users can currently download `x-windows-x86_64.exe` from the v0.8.0
release. It is a self-contained portable executable and does not require Python.
The release also includes its SHA-256 file, wheel, source archive, and validated
WinGet manifest set.

## What it does

| Command | Purpose | Storage |
|---|---|---|
| `x todo` | Task lifecycle, filters, reminders, repeats, templates, dependencies, batch operations, recycle bin, and export | Markdown + YAML frontmatter |
| `x secret` | Local multi-field credential records, clipboard access, import, and export | JSON |
| `x diary` | Append daily entries and list recent dates | Markdown |
| `x note` | Create, list, show, and search tagged topic notes | Markdown + YAML frontmatter |
| `x web` | Local browser UI for tasks and credentials | Same local data |

The CLI is designed for one user on one machine. It has no cloud sync, telemetry,
team workspace, or third-party runtime dependency.

## Relationship with x-cmd

x-cli shares the `x` prefix with [x-cmd](https://x-cmd.com), a POSIX shell
toolkit ("Shell Superpowers for AI Agents") with 300+ modules and 600+ on-demand
packages. Both projects chose `x` as a short, fast command, and x-cmd's
design — a "standard library for shell", POSIX-first, on-demand loading — has
influenced x-cli's own philosophy of zero-dependency, plain-text tooling.

- **Usage may conflict; functionality does not.** Installing both puts two `x`
  commands on the same machine — the shell resolves whichever comes first in
  `PATH` (x-cmd also removes an existing `x` alias during installation). The
  feature sets are complementary: x-cmd owns the POSIX shell/agent ecosystem,
  x-cli owns native Windows personal data (todo / secret / diary / note + web UI).
- **Environment variables do not collide.** x-cmd uses the `___X_CMD_*`
  namespace; x-cli uses `XCLI_*`. Data roots are separate
  (`$___X_CMD_ROOT_DATA` vs `%LOCALAPPDATA%\x-cli\` / `$XDG_DATA_HOME/x-cli/`).
- **Cooperation in progress.** A secret-vault design and a `todo` module have
  been proposed upstream ([discussion #455](https://github.com/x-cmd/x-cmd/discussions/455),
  [PR #456](https://github.com/x-cmd/x-cmd/pull/456)). If those modules mature,
  the projects may merge or co-exist: x-cmd modules serve POSIX and agents,
  while x-cli keeps the native Windows experience, with a possible shared data
  format between them in the long term.

## Quick tour

```powershell
x --version

x todo add "Prepare driving test" --priority high --deadline 2026-08-31 --tags study,summer
x todo list
x todo done prepare-driving-test

x diary "Finished today's review"
x note add "API setup" --body "Configuration notes" --tags API

x secret set example --value "replace-me" --category demo
x secret list

x web
```

Run `x --help` or `x <subcommand> --help` for the live command surface. The
canonical inventory is [COMMANDS.md](COMMANDS.md), with detailed reference in
[docs/commands.md](docs/commands.md).

## Install for development

Use a virtual environment so unrelated system Python plugins cannot affect the
project:

```powershell
git clone https://github.com/xuanyuanluoxue/x-cli.git
cd x-cli
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"

x --version
```

On Unix-like systems, replace `.venv\Scripts\python.exe` with
`.venv/bin/python`.

## Data and security

| Platform | Default data root |
|---|---|
| Windows | `%LOCALAPPDATA%\x-cli\` |
| Linux / macOS | `$XDG_DATA_HOME/x-cli/` or `~/.local/share/x-cli/` |

Within that root, tasks, credentials, diaries, and notes use separate paths.
Upgrading the program does not replace user data.

Important boundaries:

- Secret list and search output never includes field values.
- Secret values are still stored as plaintext JSON. Browser masking is not
  encryption at rest.
- On POSIX, the secrets database is written with mode `0600`; on Windows it
  inherits the current user's profile ACL.
- Import operations are one-way and do not modify their source data.
- Unknown task frontmatter fields and Markdown bodies are preserved.

Back up local data before migrations or bulk changes.

## Local Web UI

```powershell
x web
x web --no-browser
x web --token "choose-a-token"
```

The server binds to `127.0.0.1:8421` by default. Authentication is opt-in for
loopback use through `--token` or `web_auth: true`. Keep authentication enabled
if you intentionally bind to a non-loopback address.

The frontend source is under `web/`; built assets under `core/web/static/` are
committed so installed packages can serve the UI without Node.js.

## Documentation

| Document | Purpose |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | Version history, including v0.8.0 |
| [COMMANDS.md](COMMANDS.md) | User-owned feature inventory |
| [docs/commands.md](docs/commands.md) | Full command reference |
| [docs/TODO-SPEC.md](docs/TODO-SPEC.md) | Task storage format |
| [docs/architecture.md](docs/architecture.md) | Architecture and invariants |
| [docs/releasing.md](docs/releasing.md) | Windows, GitHub Release, and WinGet runbook |
| [docs/behaviors/](docs/behaviors/) | Given-When-Then behavior specifications |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development and pull-request workflow |

## Development

```powershell
$env:TMP = "D:\Temp\pytest_tmp"
$env:TEMP = "D:\Temp\pytest_tmp"

.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m pytest --cov=core --cov=plugins --cov=x --cov-fail-under=80
.venv\Scripts\python.exe -m ruff check core plugins x.py scripts tests
```

Runtime code remains standard-library only. New commands belong in `plugins/`,
shared logic belongs in `core/`, and `x.py` remains the lightweight entry point.
See [AGENTS.md](AGENTS.md) for the risk-based workflow and mandatory checks.

## License

MIT. See [LICENSE](LICENSE).
