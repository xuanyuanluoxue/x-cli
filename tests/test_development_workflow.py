"""Repository-level contracts for the single-mainline development workflow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_contributor_docs_use_main_as_the_only_long_lived_branch() -> None:
    agents = _read("AGENTS.md")
    contributing = _read("CONTRIBUTING.md")

    assert "`main` 是唯一长期分支" in agents
    assert "PR 目标为 `main`" in agents
    assert "Long-lived `dev` and release branches are not used." in contributing
    assert "base branch to `dev`" not in contributing
    assert "upstream/dev" not in contributing


def test_ci_runs_full_tests_and_reproduces_web_artifacts() -> None:
    workflow = _read(".github/workflows/ci.yml")

    assert "pull_request:" in workflow
    assert "branches:\n      - main" in workflow
    assert r".\.venv\Scripts\python.exe -m pytest -q" in workflow
    assert "run: npm ci" in workflow
    assert "run: npm run build" in workflow
    assert "git status --porcelain -- core/web/static" in workflow


def test_release_tags_must_point_to_main() -> None:
    workflow = _read(".github/workflows/release.yml")

    assert "fetch-depth: 0" in workflow
    assert "git merge-base --is-ancestor $env:GITHUB_SHA origin/main" in workflow
    assert "does not point to a commit on main" in workflow


def test_line_endings_are_repository_controlled() -> None:
    attributes = _read(".gitattributes")

    assert "* text=auto" in attributes
    assert "*.py text eol=lf" in attributes
    assert "*.ps1 text eol=crlf" in attributes
    assert "core/web/static/** text eol=lf" in attributes
