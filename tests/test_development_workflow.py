"""Repository-level contracts for the single-mainline development workflow."""

from pathlib import Path

from core.version import __version__


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
    assert workflow.count("actions/checkout@v7") == 3
    assert workflow.count("actions/setup-python@v7") == 2
    assert workflow.count("actions/setup-node@v7") == 1
    for version in ("3.10", "3.12", "3.14"):
        assert version in workflow
    assert "windows-latest" in workflow
    assert "ubuntu-latest" in workflow
    assert "--cov-fail-under=80" in workflow
    assert "precision = 2" in _read("pyproject.toml")
    assert "python -m ruff check core plugins x.py scripts tests" in workflow
    assert 'select = ["F"]' in _read("pyproject.toml")
    assert "run: npm ci" in workflow
    assert 'node-version: "22.12"' in workflow
    assert "npm audit --audit-level=high" in workflow
    assert "run: npm run build" in workflow
    assert "git status --porcelain -- core/web/static" in workflow


def test_release_tags_must_point_to_main() -> None:
    workflow = _read(".github/workflows/release.yml")

    assert "actions/checkout@v7" in workflow
    assert "actions/setup-python@v7" in workflow
    assert "fetch-depth: 0" in workflow
    assert "git merge-base --is-ancestor $env:GITHUB_SHA origin/main" in workflow
    assert "does not point to a commit on main" in workflow


def test_line_endings_are_repository_controlled() -> None:
    attributes = _read(".gitattributes")

    assert "* text=auto" in attributes
    assert "*.py text eol=lf" in attributes
    assert "*.ps1 text eol=crlf" in attributes
    assert "core/web/static/** text eol=lf" in attributes


def test_docs_track_current_version_repo_and_implemented_behaviors() -> None:
    commands = _read("docs/commands.md")
    changelog = _read("CHANGELOG.md")

    assert f"v{__version__} 实际实现" in commands
    assert "github.com/x-cli/x-cli" not in changelog
    assert "github.com/xuanyuanluoxue/x-cli" in changelog

    implemented_specs = (
        "config-behavior.md",
        "todo-done-behavior.md",
        "todo-import-behavior.md",
        "todo-init-behavior.md",
        "todo-restore-behavior.md",
        "todo-search-behavior.md",
        "todo-storage-behavior.md",
    )
    for filename in implemented_specs:
        text = _read(f"docs/behaviors/{filename}")
        assert "✅ 已实现" in text
        assert "🚧" not in text


def test_tests_do_not_depend_on_personal_absolute_paths() -> None:
    tests_root = ROOT / "tests"
    private_prefix = "C:" + "\\Users\\" + "Chatxavier"

    for path in tests_root.rglob("*.py"):
        assert private_prefix not in path.read_text(encoding="utf-8"), path
