# Repository Guidelines

## Project Structure & Module Organization

`x.py` is the Python 3.10+ entry point and should remain limited to argument parsing, configuration, logging, and plugin dispatch. User-facing commands live in `plugins/` (`todo.py`, `secret.py`, and `web.py`); each plugin exposes `register(parser)` and `run(args)`. Shared stdlib-only logic belongs in `core/`, while the local HTTP server and static assets are under `core/web/`. Tests are in `tests/`, and Given-When-Then specifications are in `docs/behaviors/`. Treat `COMMANDS.md` as the user-owned feature specification; consult `README.md`, `docs/architecture.md`, and `docs/commands.md` for supporting context.

## Build, Test, and Development Commands

Create and use a virtual environment; the system Python may load unrelated pytest plugins.

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m pytest tests/test_parser.py
.venv\Scripts\python.exe -m pytest --cov=core --cov=plugins --cov=x
x --version
x web --port 9000 --no-browser
```

On Windows, set `TMP` and `TEMP` to a writable directory such as `D:\Temp\pytest_tmp` before running the full suite if pytest reports temp-directory permission errors.

## Coding Style & Naming Conventions

Use four-space indentation, type hints, descriptive `snake_case` names, and `PascalCase` for classes. Keep runtime dependencies empty: do not add Click, Typer, Rich, PyYAML, or similar packages. Preserve unknown YAML frontmatter fields through `Task.extra`; never replace the handwritten parser casually. Core modules and plugins must not import `x`, which would create circular imports. Register every new plugin explicitly in `core.dispatch.SUBCOMMAND_MODULES`; `x.py` must not statically import concrete plugins.

## Risk-Based Development Workflow

Use the lightest process that safely matches the change. Escalate to the next level when scope or risk is unclear.

- **Small changes**: documentation, help text, formatting, test-only maintenance, or a local bug with no data/security/architecture impact. Do not create a plan. BDD is optional. Add a regression test when behavior changes, run focused tests, and stop there unless the touched area has a mandatory full-suite rule.
- **Medium changes**: a user-visible feature, a new flag/action, or coordinated edits across several modules. Write a short temporary plan containing goal, scope, tests, risks, and acceptance criteria. Write/update BDD only for new user-visible behavior, then use TDD (Red → Green) and run focused tests during implementation. Run the full suite once before handoff.
- **Large or high-risk changes**: architecture, data format/migration, `core/parser.py`, `core/models.py`, storage semantics, command dispatch, secrets, Web authentication, background processes, packaging, or release automation. Write a full temporary plan; add an ADR for a significant architectural decision; use BDD for behavior changes and TDD for implementation. Run focused tests, the full suite, and only the relevant build/security/release checks.

Do not require BDD for a behavior-preserving internal refactor when existing tests plus an architecture/regression test express the contract clearly. Do not rerun the full suite after every small step; use focused tests during development and one full run at the required boundary. Do not run EXE/WinGet validation unless packaging, dispatch, entry-point, Web assets, or release behavior could be affected.

Temporary plans live in `docs/plans/` and are deleted after all acceptance checks pass; durable decisions belong in BDD documents, ADRs, architecture docs, or the changelog. Pause for user feedback only when a decision changes scope, external effects, data safety, or product behavior—not after an arbitrary number of implementation tasks.

Use pytest and follow `test_<feature>.py` / `test_<behavior>` naming. Changes to `core/parser.py`, `core/models.py`, storage, command dispatch, secrets, or Web authentication require their focused tests plus the full suite.

## Commit & Pull Request Guidelines

提交信息统一使用中文，格式为 `类型(模块): 描述`，例如 `feat(todo): 新增导出过滤功能` 或 `fix(web): 修复令牌验证失败`。每次提交保持聚焦。从 `dev` 拉 `feature/<name>` 或 `fix/<name>` 分支开发；禁止直接推送到 `main` 或 `dev`。PR 目标为 `dev`，需说明行为变更、引用相关规格或 issue，并附带测试和覆盖率结果。未经用户明确授权，禁止提交、推送、amend 或绕过 hooks。

## Security & Configuration

Never expose secret values in list or search output. Keep the web server bound to `127.0.0.1` by default and preserve `X-Web-Token` authentication. Do not commit local data, credentials, generated logs, or environment-specific configuration.
