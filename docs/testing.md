# Testing Guide（v0.6.0 现状）

> **目标读者**：任何想改 x-cli 代码的人（人或 AI agent）
> **状态**：✅ 597 用例（详见 §2），全量运行 < 30 秒
> **配套**：[AGENTS.md §5 开发方法论（BDD + TDD）](../AGENTS.md)、[docs/behaviors/](behaviors/) 行为规格

---

## 1. 测试分层

x-cli 的测试分 3 层，每层定位不同：

### 1.1 单元测试（in-process）

- **位置**：`tests/test_<module>.py` 或 `tests/test_<command>_<action>.py`
- **方式**：直接 import + 调函数，**不启动子进程**
- **覆盖**：核心模块（models / parser / storage / secrets / config / logging / paths / slug / formatting）、CLI handler（_todo_add / _todo_tag / _secret_get 等）
- **速度**：极快（10ms/test）
- **数量**：约 480 个

### 1.2 BDD 行为规格（in-process）

- **位置**：`docs/behaviors/<command>-<action>-behavior.md`（**先于**测试写）
- **对应测试**：`tests/test_<command>_<action>.py`（每个 Scenario 至少 1 个 test）
- **方式**：**先写 BDD（Given-When-Then），再写 test，再写实现**
- **数量**：8 份 BDD，~50 个 Scenario（见 §2.3）

### 1.3 端到端测试（subprocess）

- **位置**：`tests/test_e2e_<command>.py`
- **方式**：`subprocess.run([x_exe, ...args])` 真启动 `x.exe`，断言 exit code / stdout / stderr
- **覆盖**：
  - `pyproject.toml` `[project.scripts] x = "x:main"` 入口接线
  - `XCLI_TODO_DIR` / `XCLI_CONFIG_PATH` 等环境变量路由
  - `x` → `x.main` → `SUBCOMMAND_HANDLERS` → `plugins/<name>.run` 全链路
  - setuptools 生成的 `x.exe` wrapper（Windows）
- **速度**：慢（~100ms/test，因为要启子进程）
- **数量**：约 80 个（todo 70 + secret 22 + config 12）

**关键约束**：e2e 跑的是 venv `Scripts/x.exe`（setuptools 装出来的）。**先** `pip install -e ".[dev]"`，否则 e2e test 会 `pytest.skip()`。

---

## 2. 测试分布（v0.6.0）

### 2.1 按文件统计（20 个文件，597 用例）

| 文件 | 主题 | 数量（估计）|
|---|---|---|
| `test_models.py` | `core/models.py` — Task / TaskStatus / Priority / ArchiveReason 数据类 | ~25 |
| `test_parser.py` | `core/parser.py` — YAML frontmatter 手写 parser（round-trip）| ~75 |
| `test_storage.py` | `core/storage.py` — 文件系统 CRUD（list/add/update/archive/stats）| ~75 |
| `test_paths.py` | `core/paths.py` — 跨平台路径（XDG / AppData）| ~7 |
| `test_secrets.py` | `core/secrets.py` — JSON DB 读写 + 脱敏 | ~50 |
| `test_config.py` | `core/config.py` — YAML 配置 + 优先级链 | ~34 |
| `test_logging.py` | `core/logging.py` — logging level + 文件输出 | ~40 |
| `test_x.py` | `x.py` 主入口 — argparse + SUBCOMMAND_HANDLERS 分发 | ~12 |
| `test_todo_add.py` | `x todo add` | ~26 |
| `test_todo_list.py` | `x todo list` | ~16 |
| `test_todo_update.py` | `x todo update` | ~12 |
| `test_todo_archive.py` | `x todo archive` | ~16 |
| `test_todo_restore.py` | `x todo restore` | ~14 |
| `test_todo_search.py` | `x todo search` | ~15 |
| `test_todo_stats.py` | `x todo stats` | ~26 |
| `test_todo_done.py` | `x todo done` | ~8 |
| `test_todo_tag.py` | `x todo tag`（v0.6.0 P1）| ~14 |
| `test_todo_auto_archive.py` | v0.6.0 auto-archive on query | ~8 |
| `test_e2e_todo.py` | e2e — `x todo *` | ~70 |
| `test_e2e_secret.py` | e2e — `x secret *` | ~22 |
| `test_e2e_config.py` | e2e — `x --config` / `x --log-level` | ~12 |
| **合计** | | **~597** |

### 2.2 按子系统统计

| 子系统 | 用例数（估计）|
|---|---|
| `core/` 库 | ~340（58%）|
| `x.py` 主入口 | ~12（2%）|
| `x todo` CLI | ~135（22%）|
| `x secret` CLI | ~50（8%）|
| `x web` API | ~25（4%）|
| 配置 + 日志 | ~75（13%）|
| e2e（跨子系统）| ~80（13%）|

### 2.3 BDD 行为规格（8 份）

| 文件 | 场景数 |
|---|---|
| `todo-add-behavior.md` | 8 |
| `todo-list-behavior.md` | 6 |
| `todo-update-behavior.md` | 6 |
| `todo-archive-behavior.md` | 6 |
| `todo-stats-behavior.md` | 5 |
| `secret-behavior.md` | 15 |
| `config-behavior.md` | 30+ |
| `web-api-behavior.md` | ~15 |
| `e2e-cli-behavior.md` | 10 |
| `todo-tag-behavior.md`（v0.6.0 P1）| 17 |
| **合计** | **~118** |

---

## 3. 运行命令

### 3.1 全量

```bash
.venv\Scripts\python.exe -m pytest
```

输出形如（v0.6.0 实测）：

```
collected 597 items

tests\test_config.py ..................................                  [  6%]
tests\test_logging.py .......................................            [ 14%]
... (中间省略)
tests\test_e2e_todo.py ...................x.....................        [100%]

PermissionError: [WinError 5] ... pytest-of-Chatxavier\pytest-current
```

> ⚠️ **Windows 上 pytest 在 teardown 阶段清理 tmpdir 会触发 `PermissionError [WinError 5]`**（文件锁/杀软扫描）。**这是项目级问题，不影响测试结果** —— 全部用例都跑完且 pass，traceback 是 cleanup 失败。
> 
> 解决方案：CI 用 `pytest --override-ini="addopts="` 或 `pytest -p no:cacheprovider`（不影响结果）。
> 详见 [README.md "故障排查" §Windows pytest 临时目录问题](../README.md)。

### 3.2 跑单个文件

```bash
.venv\Scripts\python.exe -m pytest tests/test_todo_tag.py -v
```

### 3.3 跑单个测试

```bash
.venv\Scripts\python.exe -m pytest tests/test_todo_tag.py::test_tag_adds_single_tag -v
```

### 3.4 按关键字过滤

```bash
.venv\Scripts\python.exe -m pytest -k "tag and not e2e" -v
```

### 3.5 覆盖率报告

```bash
.venv\Scripts\python.exe -m pytest --cov=core --cov=plugins --cov-report=term-missing
```

v0.6.0 覆盖率：**~95%**（按 line 计，e2e 覆盖路径不计）。

### 3.6 跳过 e2e（快速跑单测）

```bash
.venv\Scripts\python.exe -m pytest --ignore=tests/test_e2e_todo.py --ignore=tests/test_e2e_secret.py --ignore=tests/test_e2e_config.py
```

---

## 4. e2e 模式（子进程测试）

e2e test 走的是"真用户在 PowerShell 跑 `x todo add foo`"的全链路。模式如下：

```python
# tests/test_e2e_todo.py 模式（节选）
import os
import subprocess
import sysconfig
from pathlib import Path


def _x_executable() -> str:
    """找到 setuptools 装出来的 x.exe（或 x）。"""
    scripts_dir = Path(sysconfig.get_path("scripts"))
    name = "x.exe" if os.name == "nt" else "x"
    return str(scripts_dir / name)


def _run_x(x_path: str, args, todo_dir: Path, *, timeout: float = 30.0):
    """跑 ``x <args>``，返回 (returncode, stdout, stderr)。"""
    env = os.environ.copy()
    env["XCLI_TODO_DIR"] = str(todo_dir)  # 隔离真实 TODO dir
    proc = subprocess.run(
        [x_path, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


@pytest.fixture
def x_path():
    p = _x_executable()
    if not Path(p).exists():
        pytest.skip(f"x not installed at {p}; run `pip install -e .` in venv")
    return p
```

**关键点**：

1. **隔离**：`monkeypatch.setenv("XCLI_TODO_DIR", str(tmp_path))` 让 e2e 不污染真实 TODO dir
2. **真子进程**：用 `subprocess.run` 而不是 `main()` —— 这才能覆盖 `pyproject.toml` 的 `[project.scripts] x = "x:main"` 入口
3. **找 x.exe**：用 `sysconfig.get_path("scripts")` 找 venv 装出来的可执行文件
4. **失败 fallback**：如果 venv 没装（开发环境未 `pip install -e .`），用 `pytest.skip()` 跳过

### 4.1 e2e test 模板（建议）

```python
def test_e2e_<action>_<scenario>(x_path: str, todo_dir: Path):
    """BDD §<behavior> <N>: <一句话描述>。"""
    # Arrange：用真子进程铺好前置状态
    _run_x(x_path, ["todo", "add", "kemu1"], todo_dir)
    
    # Act：跑被测命令
    code, out, err = _run_x(x_path, ["todo", "tag", "kemu1", "冲刺"], todo_dir)
    
    # Assert：精确断言 exit code + stdout + stderr
    assert code == 0, f"expected 0, got {code}; stderr={err!r}"
    assert "✅" in out
    assert "冲刺" in out
    
    # 可选：读磁盘上的真实文件验证（用于"看 frontmatter 真改了"场景）
    todo_md = (todo_dir / "任务" / "kemu1" / "TODO.md").read_text(encoding="utf-8")
    assert "tags: [冲刺]" in todo_md
```

---

## 5. 跨平台陷阱

| 陷阱 | 解决 |
|---|---|
| Windows `x.exe` vs POSIX `x` | 用 `sysconfig.get_path("scripts")` + `os.name == "nt"` |
| Windows 路径分隔符 | 永远用 `pathlib.Path`，**不要**用 `os.path.join` |
| CJK 文件名 | 测试 fixture 用中文（如 `科目一模拟考`），不强制 ASCII（**不**用 slug 化）|
| pytest tmpdir 锁 | `--override-ini="addopts="` 或 `-p no:cacheprovider` |
| subprocess 启动慢 | 默认 `timeout=30.0`，**不**用更小 |
| 环境变量隔离 | `env = os.environ.copy()` + `env["XCLI_TODO_DIR"] = tmp` 覆盖 |

---

## 6. 写新测试的 checklist

> **AGENTS.md §5 强制 BDD + TDD**，所有新功能必须按这个流程：

- [ ] **Step 1（BDD）**：写 `docs/behaviors/<feature>-behavior.md`，每个 Scenario 用 Given-When-Then
- [ ] **Step 2（TDD Red）**：写 `tests/test_<feature>.py`，每个 Scenario 至少 1 个 test，**确认全红**
- [ ] **Step 3（TDD Green）**：写实现，让 test 全过
- [ ] **Step 4（Refactor）**：重构实现 + 测试（如果需要）
- [ ] **Step 5（E2E）**：写 `tests/test_e2e_<feature>.py`，**真子进程**跑关键 5-10 个场景
- [ ] **Step 6（Commit）**：每个 step 一个 commit，conventional commit 格式

**不要**：
- ❌ 跳过 BDD 直接写 test（违反 §5.1）
- ❌ 跳过 TDD Red 直接写实现（违反 §5.1）
- ❌ BDD 写完没对应 test（spec 漂移）
- ❌ test 写完没对应实现（dead test）
- ❌ e2e test 用 `main()`（不是真子进程，破坏 e2e 价值）

---

## 7. 当前已知问题

| 问题 | 等级 | 状态 |
|---|---|---|
| Windows pytest tmpdir PermissionError | 低 | 不影响测试结果，仅 cleanup 失败。CI 用 `--override-ini="addopts="` |
| e2e 慢（~100ms/test）| 低 | 接受（80 用例 = 8 秒）|
| macOS 上 x.exe 测试覆盖率可能低 | 低 | 跨平台 run CI 再补 |
| 暂无 mutation testing | 极低 | 个人用，不引第三方 mutation lib |

---

*Last updated: 2026-06-28*
