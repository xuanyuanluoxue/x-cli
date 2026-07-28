# Contributing to x-cli

Thank you for contributing to x-cli. This repository uses a single-mainline
workflow: `main` is the only long-lived branch and must remain releasable.

## Branch strategy

| Branch | Purpose | Lifetime |
|--------|---------|----------|
| `main` | Protected integration and release branch | Permanent |
| `feature/<name>` | User-visible feature or coordinated improvement | Delete after merge |
| `fix/<name>` | Bug fix | Delete after merge |

Do not push directly to `main`. Create every working branch from the latest
`origin/main`, open a PR back to `main`, and use squash merge by default.
Long-lived `dev` and release branches are not used.

## Set up a fork

```bash
git clone https://github.com/YOUR_USERNAME/x-cli.git
cd x-cli
git remote add upstream https://github.com/xuanyuanluoxue/x-cli.git
git fetch upstream
git switch main
git merge --ff-only upstream/main
```

Keep your fork's `main` as a clean mirror of upstream. Do development on a
short-lived branch:

```bash
git switch main
git fetch upstream
git merge --ff-only upstream/main
git switch -c feature/your-feature-name
```

Use `fix/your-fix-name` for a bug fix.

## Choose the smallest safe workflow

| Change | Required workflow |
|--------|-------------------|
| Small docs/help/local fix | No plan; BDD optional; focused tests |
| User-visible feature or multi-module change | Short temporary plan; BDD for new behavior; TDD; focused tests; one full-suite run |
| Architecture, data, security, background process, packaging, CI, or release | Full temporary plan; ADR when architectural; BDD/TDD as applicable; full suite and relevant build/security checks |

Temporary plans belong in `docs/plans/` and are removed after acceptance.
Permanent decisions belong in behavior specifications, ADRs, architecture
documentation, or the changelog. See [AGENTS.md](AGENTS.md) for the complete
development rules.

## Web frontend changes

Edit frontend source only under `web/`. The files in `core/web/static/` are
committed Vite output used by Python packages and the Windows executable.

```bash
cd web
npm ci
npm run build
cd ..
git status --short -- core/web/static
```

Commit the source and regenerated artifacts together. Do not hand-edit files
under `core/web/static/`; CI rebuilds them from the lock file and rejects stale
or extra assets.

## Test changes

Use an isolated virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest --cov=core --cov=plugins --cov=x --cov-fail-under=80
.\.venv\Scripts\python.exe -m ruff check core plugins x.py scripts tests
```

Run focused tests while iterating and the full suite once at the required
handoff boundary. On Windows, set `TMP` and `TEMP` to a writable directory if
pytest reports temporary-directory permission errors.

CI runs the full suite on Windows with Python 3.10, 3.12, and 3.14, repeats
the suite with coverage on Linux, enforces an 80% floor, and rejects all
Pyflakes (`F`) errors.

## Commit and open a PR

Commit messages use Chinese descriptions:

```text
类型(模块): 描述
```

Examples:

```text
feat(todo): 新增导出过滤功能
fix(web): 修复令牌验证失败
docs(dev): 统一主干开发流程
```

Keep commits focused. Push the working branch to your fork and open a PR with
`main` as the base branch:

```bash
git push -u origin feature/your-feature-name
```

The PR must describe behavior changes, reference the relevant specification or
issue when applicable, and report tests and coverage. At least one maintainer
approval and all required CI checks are expected before squash merge. Delete
the working branch after merge.

## Issues and feature requests

- Report bugs with reproduction steps, expected behavior, actual behavior,
  operating system, and Python version.
- Open an issue before implementing a non-trivial feature so scope and behavior
  can be agreed first.

Contributions are licensed under the repository's [MIT License](LICENSE).
