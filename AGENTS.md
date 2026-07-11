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

Use four-space indentation, type hints, descriptive `snake_case` names, and `PascalCase` for classes. Keep runtime dependencies empty: do not add Click, Typer, Rich, PyYAML, or similar packages. Preserve unknown YAML frontmatter fields through `Task.extra`; never replace the handwritten parser casually. Core modules and plugins must not import `x`, which would create circular imports. Register every new plugin explicitly in `x.py:SUBCOMMAND_HANDLERS`.

## Testing Guidelines

Use pytest and follow `test_<feature>.py` / `test_<behavior>` naming. Write or update a BDD document first, add a failing test, then implement the change. Run focused tests during development and the complete suite before handoff. Changes to `core/parser.py`, `core/models.py`, or command dispatch require their corresponding focused tests plus the full suite.

## Commit & Pull Request Guidelines

Use Conventional Commits, for example `feat(todo): add export filtering` or `fix(web): reject invalid token`. Keep each commit focused. Develop from `dev` on `feature/<name>` or `fix/<name>` branches; do not push directly to `main` or `dev`. PRs should target `dev`, explain behavior changes, reference the relevant specification or issue, and include test and coverage results. Do not commit, push, amend commits, or bypass hooks unless the user explicitly authorizes it.

## Security & Configuration

Never expose secret values in list or search output. Keep the web server bound to `127.0.0.1` by default and preserve `X-Web-Token` authentication. Do not commit local data, credentials, generated logs, or environment-specific configuration.
