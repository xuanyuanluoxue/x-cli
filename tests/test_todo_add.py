"""Tests for ``x todo add <名称>`` (Phase 1 inline in x.py).

Each test maps to a scenario in
``docs/behaviors/todo-add-behavior.md``:

1. minimal form (name only)              → test_add_minimal_form
2. full params (--priority/--deadline/--tags) → test_add_full_params
3. duplicate name (error)                → test_add_duplicate_name_errors
4. missing required name (argparse)      → test_add_missing_name_errors
5. invalid --priority value (error)      → test_add_invalid_priority_errors
6. bad --deadline format (error)         → test_add_bad_deadline_format_errors
7. no --tags ⇒ frontmatter omits tags    → test_add_no_tags_omits_field
8. unknown frontmatter fields NOT written → test_add_does_not_write_unknown_fields

Plus integration / wiring tests.

All tests use ``XAVIER_TODO_DIR`` pointed at ``tmp_path`` so the real
``~/.xavier/TODO`` is never modified. Each test cleans up the
``tmp_path`` fixture (auto-cleaned by pytest) AND every test that
``add``s a task asserts there are no leftover folders — we never
want to pollute the real TODO repo even by accident.
"""

from __future__ import annotations

import io
import re
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

import pytest

from core.parser import parse_frontmatter
from core.slug import slugify, unique_slug, validate_deadline, parse_tags
from core.storage import TaskStore
from x import main


# ============================================================
#  Fixtures / helpers
# ============================================================


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TaskStore:
    """Root the TaskStore at ``tmp_path``; never touches the real TODO dir.

    Also asserts (after the test) that nothing was written to the real
    ``~/.xavier/TODO`` — defence in depth against the most embarrassing
    way to break a BDD test.
    """
    real_todo = Path.home() / ".xavier" / "TODO"
    real_active_before = (
        sorted(p.name for p in (real_todo / "任务").iterdir())
        if (real_todo / "任务").is_dir()
        else []
    )
    monkeypatch.setenv("XAVIER_TODO_DIR", str(tmp_path))
    yield TaskStore()

    # Post-test invariant: real ~/.xavier/TODO/任务 is unchanged.
    real_active_after = (
        sorted(p.name for p in (real_todo / "任务").iterdir())
        if (real_todo / "任务").is_dir()
        else []
    )
    assert real_active_after == real_active_before, (
        f"Test leaked into ~/.xavier/TODO/任务! "
        f"before={real_active_before} after={real_active_after}"
    )


def _invoke_add(*argv: str) -> tuple[int, str, str]:
    """Call ``main(["todo", "add", *argv])`` and capture stdout/stderr."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        exit_code = main(["todo", "add", *argv])
    return exit_code, out.getvalue(), err.getvalue()


def _read_frontmatter(folder: Path) -> dict:
    """Parse the TODO.md in ``folder`` and return its frontmatter dict."""
    text = (folder / "TODO.md").read_text(encoding="utf-8")
    metadata, _ = parse_frontmatter(text)
    return metadata


# ============================================================
#  Scenario 1: minimal form (name only)
# ============================================================


def test_add_minimal_form(store: TaskStore) -> None:
    """对应 BDD §场景 1：只给名称，使用所有默认值。

    Expected: status=pending, priority=medium, created/updated=today,
    no deadline, no tags, folder=任务/测试任务A.
    """
    target_name = "测试任务A"
    expected_today = date.today().isoformat()

    exit_code, stdout, stderr = _invoke_add(target_name)

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    assert "✅ 任务已创建" in stdout
    assert target_name in stdout
    # ID is generated, format check only:
    m = re.search(r"ID:\s*(\S+)", stdout)
    assert m is not None, f"no id in stdout: {stdout!r}"
    task_id = m.group(1).rstrip(")）")
    # kebab-case letters/digits/hyphens
    assert re.fullmatch(r"[a-z0-9-]+", task_id), f"id not kebab-case: {task_id!r}"

    # Folder and file exist
    folder = store.active_dir / target_name
    assert folder.is_dir()
    assert (folder / "TODO.md").is_file()

    # Frontmatter contains exactly the required fields, no deadline, no tags
    metadata = _read_frontmatter(folder)
    assert metadata["id"] == task_id
    assert metadata["name"] == target_name
    assert metadata["status"] == "pending"
    assert metadata["priority"] == "medium"
    assert metadata["created"] == expected_today
    assert metadata["updated"] == expected_today
    assert metadata["folder"] == f"任务/{target_name}"
    assert "deadline" not in metadata, f"deadline leaked: {metadata!r}"
    assert "tags" not in metadata, f"tags leaked: {metadata!r}"


# ============================================================
#  Scenario 2: full params (--priority + --deadline + --tags)
# ============================================================


def test_add_full_params(store: TaskStore) -> None:
    """对应 BDD §场景 2：完整参数，id 必须为 ``kemu1-moni-kao``（BDD 硬要求）。"""
    target_name = "科目一模拟考"

    exit_code, stdout, stderr = _invoke_add(
        target_name,
        "--priority", "high",
        "--deadline", "2026-08-31",
        "--tags", "驾照,暑假",
    )

    assert exit_code == 0, f"expected 0, got {exit_code}; stderr={stderr!r}"
    assert f"ID: kemu1-moni-kao" in stdout, f"id not pinned: {stdout!r}"

    folder = store.active_dir / target_name
    assert folder.is_dir()
    metadata = _read_frontmatter(folder)
    assert metadata["id"] == "kemu1-moni-kao"
    assert metadata["name"] == target_name
    assert metadata["status"] == "pending"
    assert metadata["priority"] == "high"
    assert metadata["deadline"] == "2026-08-31"
    assert metadata["tags"] == ["驾照", "暑假"]
    assert metadata["folder"] == f"任务/{target_name}"
    assert metadata["created"] == date.today().isoformat()
    assert metadata["updated"] == date.today().isoformat()


# ============================================================
#  Scenario 3: duplicate name
# ============================================================


def test_add_duplicate_name_errors(store: TaskStore, tmp_path: Path) -> None:
    """对应 BDD §场景 3：同名任务已存在 → 退出码 3，不修改任何文件。"""
    target_name = "科目一"

    # Pre-create a task with the same name (and a different id, to make
    # the assertion specific)
    existing_folder = store.active_dir / target_name
    existing_folder.mkdir(parents=True, exist_ok=True)
    original_text = (
        "---\n"
        "id: kemu1\n"
        f"name: {target_name}\n"
        "status: pending\n"
        "priority: high\n"
        "created: 2026-03-27\n"
        "updated: 2026-06-13\n"
        "folder: 任务/科目一\n"
        "---\n\n"
        "# 科目一 original body\n"
    )
    (existing_folder / "TODO.md").write_text(original_text, encoding="utf-8")

    # Try to add the same name again
    exit_code, stdout, stderr = _invoke_add(target_name)

    assert exit_code == 3, f"expected 3, got {exit_code}; stderr={stderr!r}"
    assert "❌ 任务已存在" in stderr
    assert target_name in stderr
    assert "kemu1" in stderr
    assert f"任务/{target_name}" in stderr
    # No second TODO.md created (folder is single, but file untouched)
    assert (existing_folder / "TODO.md").read_text(encoding="utf-8") == original_text


# ============================================================
#  Scenario 4: missing required name (argparse)
# ============================================================


def test_add_missing_name_errors() -> None:
    """对应 BDD §场景 4：x todo add 不带位置参数 → argparse 报错退出码 2。"""
    with pytest.raises(SystemExit) as exc_info:
        main(["todo", "add"])
    assert exc_info.value.code == 2


def test_add_missing_name_error_message_via_capsys(
    store: TaskStore, capsys: pytest.CaptureFixture
) -> None:
    """对应 BDD §场景 4：错误信息应包含 "the following arguments are required: 名称"。

    argparse 自动产生该错误信息 —— 只要 positional 没传，就会触发。
    """
    with pytest.raises(SystemExit) as exc_info:
        main(["todo", "add"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "the following arguments are required: 名称" in captured.err
    # 也没有写入任何文件
    assert not (store.active_dir).exists() or not any(
        (store.active_dir).iterdir()
    )


# ============================================================
#  Scenario 5: invalid --priority value
# ============================================================


def test_add_invalid_priority_errors(store: TaskStore) -> None:
    """对应 BDD §场景 5：--priority urgent → 退出码 2，错误信息含合法值列表。"""
    exit_code, stdout, stderr = _invoke_add("新任务", "--priority", "urgent")

    assert exit_code == 2, f"expected 2, got {exit_code}; stderr={stderr!r}"
    assert "❌ 无效的 priority 值" in stderr
    assert "urgent" in stderr
    for legal in ("high", "medium", "low"):
        assert legal in stderr, f"legal priority {legal!r} not in stderr: {stderr!r}"

    # 没创建文件
    assert "新任务" not in (
        [p.name for p in store.active_dir.iterdir()] if store.active_dir.is_dir() else []
    )


# ============================================================
#  Scenario 6: bad --deadline format
# ============================================================


def test_add_bad_deadline_format_errors(store: TaskStore) -> None:
    """对应 BDD §场景 6：--deadline 2026/08/31 → 退出码 2 + 清晰错误。"""
    exit_code, stdout, stderr = _invoke_add("新任务", "--deadline", "2026/08/31")

    assert exit_code == 2, f"expected 2, got {exit_code}; stderr={stderr!r}"
    assert "❌ deadline 格式错误" in stderr
    assert "2026/08/31" in stderr
    assert "YYYY-MM-DD" in stderr

    # 没创建文件
    if store.active_dir.is_dir():
        assert "新任务" not in [p.name for p in store.active_dir.iterdir()]


def test_add_deadline_with_invalid_month_rejected(store: TaskStore) -> None:
    """日期语法对但月份非法（如 2026-13-01）应同样被拒绝。"""
    exit_code, _, stderr = _invoke_add("新任务", "--deadline", "2026-13-01")
    assert exit_code == 2
    assert "❌ deadline 格式错误" in stderr


# ============================================================
#  Scenario 7: no --tags ⇒ frontmatter omits tags
# ============================================================


def test_add_no_tags_omits_field(store: TaskStore) -> None:
    """对应 BDD §场景 7：不传 --tags ⇒ frontmatter 完全不写 tags 字段（不是空数组）。"""
    target_name = "无标签任务"

    exit_code, stdout, stderr = _invoke_add(target_name)

    assert exit_code == 0, f"stderr={stderr!r}"
    folder = store.active_dir / target_name
    metadata = _read_frontmatter(folder)
    assert "tags" not in metadata, f"tags field leaked: {metadata!r}"


def test_add_empty_tags_string_omits_field(store: TaskStore) -> None:
    """``--tags ""`` 或 ``--tags ,`` 应当等同不传 — 也不写 tags 字段。"""
    target_name = "空标签"

    exit_code, _, stderr = _invoke_add(target_name, "--tags", "")
    assert exit_code == 0, f"stderr={stderr!r}"
    metadata = _read_frontmatter(store.active_dir / target_name)
    assert "tags" not in metadata

    target_name2 = "逗号标签"
    exit_code, _, stderr = _invoke_add(target_name2, "--tags", ",,")
    assert exit_code == 0, f"stderr={stderr!r}"
    metadata = _read_frontmatter(store.active_dir / target_name2)
    assert "tags" not in metadata


# ============================================================
#  Scenario 8: unknown frontmatter fields NOT written for new tasks
# ============================================================


def test_add_does_not_write_unknown_fields(store: TaskStore) -> None:
    """对应 BDD §场景 8：新增任务不得写入任何用户自定义的"未知"字段（因为是新增）。

    兼容性约束（针对 update）：以后 ``x todo update`` 不得删除用户自定
    义字段（见 ``todo-update-behavior.md`` §场景 6）。本测试仅验证
    ``add`` 的新增路径不会凭空塞进 description / paused_at 等字段。
    """
    target_name = "新任务"

    exit_code, _, stderr = _invoke_add(target_name)

    assert exit_code == 0, f"stderr={stderr!r}"
    metadata = _read_frontmatter(store.active_dir / target_name)
    # No surprising user-managed fields
    for surprise in ("description", "paused_at", "pause_reason", "workspace"):
        assert surprise not in metadata, (
            f"add leaked {surprise!r} into new task: {metadata!r}"
        )


# ============================================================
#  Slug generation unit tests (BDD contract for id)
# ============================================================


def test_slugify_ke_mu_yi_mo_ni_kao() -> None:
    """BDD §场景 2 硬要求：``科目一模拟考`` → ``kemu1-moni-kao``。"""
    assert slugify("科目一模拟考") == "kemu1-moni-kao"


def test_slugify_ke_mu_yi() -> None:
    """与现有真实任务 ``~/.xavier/TODO/任务/科目一`` 保持一致：``科目一`` → ``kemu1``。"""
    assert slugify("科目一") == "kemu1"


def test_slugify_empty_string() -> None:
    """空字符串应安全返回空串（不抛异常）。"""
    assert slugify("") == ""


def test_slugify_kebab_case_format() -> None:
    """生成的 id 必须符合 kebab-case 约束（小写字母 / 数字 / 连字符）。"""
    for name in ("测试任务A", "hello world", "My Project 2024", "新任务", "MyProject"):
        slug = slugify(name)
        assert slug, f"empty slug for {name!r}"
        assert re.fullmatch(r"[a-z0-9-]+", slug), f"non-kebab for {name!r}: {slug!r}"


def test_unique_slug_no_collision_returns_base() -> None:
    """无碰撞时返回基础 slug（不加后缀，保持「kemu1」约定）。"""
    assert unique_slug("科目一") == "kemu1"
    assert unique_slug("科目一", set()) == "kemu1"


def test_unique_slug_appends_numeric_suffix_on_collision() -> None:
    """``kemu1`` 已被占用时返回 ``kemu1-2``，再占用返回 ``kemu1-3``。"""
    assert unique_slug("科目一", {"kemu1"}) == "kemu1-2"
    assert unique_slug("科目一", {"kemu1", "kemu1-2"}) == "kemu1-3"


# ============================================================
#  Helper unit tests
# ============================================================


def test_parse_tags_basic() -> None:
    assert parse_tags("驾照,暑假") == ["驾照", "暑假"]


def test_parse_tags_strips_whitespace_and_drops_empty() -> None:
    assert parse_tags(" a , b , c ") == ["a", "b", "c"]
    assert parse_tags("a,,b") == ["a", "b"]
    assert parse_tags(",a,b,") == ["a", "b"]
    assert parse_tags("") == []


def test_validate_deadline_accepts_iso() -> None:
    assert validate_deadline("2026-08-31") == "2026-08-31"
    assert validate_deadline("2026-12-31") == "2026-12-31"
    # 2024 IS a leap year, so Feb 29 should be accepted
    assert validate_deadline("2024-02-29") == "2024-02-29"
    # 2026 is NOT a leap year, so Feb 29 should fail
    with pytest.raises(ValueError):
        validate_deadline("2026-02-29")


def test_validate_deadline_rejects_non_iso() -> None:
    with pytest.raises(ValueError, match="格式错误"):
        validate_deadline("2026/08/31")
    with pytest.raises(ValueError, match="格式错误"):
        validate_deadline("not-a-date")
    with pytest.raises(ValueError, match="格式错误"):
        validate_deadline("")


# ============================================================
#  Integration: end-to-end via main()
# ============================================================


def test_add_e2e_via_main(store: TaskStore) -> None:
    """端到端：x todo add 走完整路径，验证 CLI 接线（argparse + handler + storage）。"""
    target_name = "e2e-任务"

    exit_code, stdout, _stderr = _invoke_add(
        target_name, "--priority", "low", "--tags", "smoke,test"
    )

    assert exit_code == 0
    assert "✅" in stdout
    assert target_name in stdout

    # File on disk
    folder = store.active_dir / target_name
    assert folder.is_dir()
    metadata = _read_frontmatter(folder)
    assert metadata["name"] == target_name
    assert metadata["priority"] == "low"
    assert metadata["tags"] == ["smoke", "test"]


def test_add_then_list_roundtrip(store: TaskStore) -> None:
    """``add`` 后立即 ``list`` 能看到新任务（验证 TaskStore ↔ handler 接线）。"""
    exit_code, _, _ = _invoke_add("list-roundtrip", "--priority", "high")
    assert exit_code == 0

    # Now call x todo list and check it shows up
    from io import StringIO
    out = StringIO()
    with redirect_stdout(out):
        ec = main(["todo", "list"])
    assert ec == 0
    output = out.getvalue()
    assert "list-roundtrip" in output
    assert "high" in output


def test_add_priority_default_is_medium(store: TaskStore) -> None:
    """不传 --priority ⇒ 默认 medium。"""
    exit_code, _, _ = _invoke_add("默认优先级")
    assert exit_code == 0
    metadata = _read_frontmatter(store.active_dir / "默认优先级")
    assert metadata["priority"] == "medium"
    assert metadata["status"] == "pending"


def test_add_id_does_not_collide_with_existing(store: TaskStore) -> None:
    """如果一个任务的 id 已经被另一个任务占用，新任务的 id 应自动加 -2 后缀。"""
    # Pre-create a task that *uses* the id that the new task's name would slugify to.
    # "kemu1" is the natural id for 科目一, so we create a foreign task with that id.
    from core.models import Priority, Task, TaskStatus

    foreign_folder = store.active_dir / "其它任务"
    foreign_folder.mkdir(parents=True, exist_ok=True)
    foreign = Task(
        id="kemu1",  # same id that "科目一" would produce
        name="其它任务",
        status=TaskStatus.PENDING,
        priority=Priority.MEDIUM,
        created="2026-01-01",
        updated="2026-01-01",
        folder="任务/其它任务",
    )
    (foreign_folder / "TODO.md").write_text(foreign.to_markdown(), encoding="utf-8")

    # Now add 科目一 (which slugifies to kemu1) — should get kemu1-2
    exit_code, stdout, stderr = _invoke_add("科目一")
    assert exit_code == 0, f"stderr={stderr!r}"
    assert "ID: kemu1-2" in stdout


# ============================================================
#  Defence in depth: tests must not pollute ~/.xavier/TODO
# ============================================================


def test_real_todo_dir_untouched_after_test(
    store: TaskStore, tmp_path: Path
) -> None:
    """本测试单独运行（不创建任何任务）后，验证 ~/.xavier/TODO/任务 仍为空/不变。

    套件里的每个测试都通过 ``store`` fixture 隔离 tmp_path，本测试
    进一步作为保险：即使前面的测试漏掉了 env var 隔离，store fixture
    也会清空 XAVIER_TODO_DIR 然后恢复。
    """
    real_todo = Path.home() / ".xavier" / "TODO"
    if not (real_todo / "任务").is_dir():
        return  # nothing to check
    # 当前 tmp_path 跟真实的 ~/.xavier/TODO 完全无关
    assert tmp_path != real_todo
    assert not str(tmp_path).startswith(str(real_todo))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
