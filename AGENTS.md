# AGENTS.md

> **目标读者**：任何接续开发 x-cli 的 AI agent（不是人）
> **必读**：**任何任务开始前必须先读完相关文档，再动手**

---

## 0. 开工前必读（按顺序）

1. **本文件 (AGENTS.md)** — 项目规约
2. **[COMMANDS.md](COMMANDS.md)** — **用户编辑的命令清单（spec 单一来源）**
3. **[README.md](README.md)** — 项目主文档 + 快速开始
4. **[docs/architecture.md](docs/architecture.md)** — 架构设计
5. **[docs/commands.md](docs/commands.md)** — 完整命令参考
6. **[docs/behaviors/](docs/behaviors/)** — BDD 行为规格（按命令名组织）
7. 按任务类型读 docs/ 子文档：
   - 打包相关 → `docs/release.md`（**未创建**）
   - 测试相关 → `docs/testing.md`（**未创建**）
   - 插件开发 → `docs/plugin-dev.md`（**未创建**）

**未读完直接动手 = 失败率高。** 文档里没写的 → **先问用户**，不要猜测。

---

## 1. 项目概述

| 项 | 值 |
|---|---|
| 名称 | **x-cli** |
| 性质 | **个人使用**（非团队、非商业）|
| 核心 | personal CLI toolset的统一 CLI 入口 |
| 目标用户 | x-cli (pen name)（开发者本人）|
| 平台 | Win10+ / macOS / Linux |
| 当前阶段 | **Phase 1 MVP 已完成**（v0.2.0） |

**这不是**通用 CLI 框架，**是**针对个人使用场景定制的工具集。**别**套用通用 CLI 工具的设计模式。

### 1.1 命令清单驱动开发（Command-List-Driven）

**核心工作流**（2026-06-21 引入）：

```
[用户]  编辑 COMMANDS.md
   ↓
   在 ⏳ 区添加新命令，标 P0/P1/P2/P3
   ↓
[AI]    读 COMMANDS.md
   ↓
   按 BDD + TDD 流程实现（docs/behaviors/ + tests/）
   ↓
   实现完把 ⏳ 改成 ✅
   ↓
[用户]  review git diff
```

**COMMANDS.md 的地位**：
- **唯一**spec 来源（user-edited）
- AI 不擅自添加命令 — 必须用户在 COMMANDS.md 列出
- AI 不擅自删除/废弃命令 — 移到 ❌ 区
- 实现完改 ✅，让用户 review 改 diff

**禁区**：
- ❌ AI 不在 COMMANDS.md 加命令（这是 user-only 文件）
- ❌ AI 不实现 COMMANDS.md ❌ 区的命令
- ❌ AI 跳过 COMMANDS.md 凭空加功能

---

## 2. 目录结构（重要 — 实际布局）

```
x-cli/
├── AGENTS.md          ← 你正在读
├── COMMANDS.md        ← **用户编辑的命令清单（spec 唯一来源）**
├── README.md          ← 项目主文档 + 快速开始
├── CHANGELOG.md       ← 版本历史
├── .gitignore
├── pyproject.toml     ← Python 项目配置（setuptools + pytest）
├── x.py               ← 主入口 + 5 个 x todo action（inline，731 行）
├── core/              ← 核心逻辑（被 x.py 引用）
│   ├── __init__.py
│   ├── models.py      ← 数据模型（Task / TaskStatus / Priority / ArchiveReason）
│   ├── parser.py      ← YAML frontmatter 解析/序列化（手写，stdlib-only）
│   ├── slug.py        ← 中英文 slug 生成（stdlib-only，硬编码拼音表 + unicodedata）
│   └── storage.py     ← 文件系统 CRUD（list/add/update/archive/stats + inventory 维护）
├── plugins/           ← 子命令插件（**MVP 阶段为空 package**，待 Phase 4 拆出）
│   └── __init__.py
├── tests/             ← pytest 测试（13 个文件，336 用例，覆盖率 93%，含 `test_e2e_todo.py` + `test_e2e_secret.py` 子进程测试）
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_parser.py
│   ├── test_storage.py
│   ├── test_x.py
│   ├── test_todo_add.py
│   ├── test_todo_list.py
│   ├── test_todo_update.py
│   ├── test_todo_archive.py
│   └── test_todo_stats.py
├── docs/              ← 详细文档
│   ├── architecture.md   ← 架构设计
│   ├── commands.md       ← 命令参考
│   └── behaviors/        ← BDD 行为规格（Given-When-Then）
│       ├── todo-add-behavior.md
│       ├── todo-list-behavior.md
│       ├── todo-update-behavior.md
│       ├── todo-archive-behavior.md
│       └── todo-stats-behavior.md
├── release/           ← 打包脚本（**目录已建但暂未实现**）
└── .mavis/            ← mavis 团队计划状态（不入 git，见 .gitignore）
```

**关键约束**：
- `plugins/` MVP 阶段只放占位 `__init__.py`，**所有 todo action 都在 x.py 里**
- `core/` 只能放核心逻辑代码（可被多个命令共享）
- `tests/` 只能放测试代码
- `docs/behaviors/` 只能放 BDD 行为规格（Given-When-Then 格式）
- **不要**混

---

## 3. 技术栈（已定）

| 组件 | 技术 | 备注 |
|---|---|---|
| CLI 框架 | `argparse`（stdlib，支持子命令） | 不用 click（避免过度依赖）|
| 插件机制 | `importlib` 动态加载 | **MVP 阶段未启用**（todo inline 在 x.py，SUBCOMMAND_HANDLERS 字典分发）|
| 数据格式 | **YAML frontmatter**（兼容现有） | **手写 parser**（不引 PyYAML；未知字段 round-trip 不丢）|
| 数据存储 | 文件系统（同现有：`<xcli_todo_dir>/`） | 不引入 DB |
| Slug 生成 | `unicodedata` + 硬编码拼音表 | **MVP 阶段不引 pypinyin/jieba**（保持 stdlib-only）|
| 配置 | `<xcli_config_path>` | **MVP 阶段未实现**（`XCLI_TODO_DIR` 环境变量作为临时覆盖）|
| 测试 | `pytest` + `pytest-cov` | 覆盖率当前 93%（含 E2E 子进程层 + secret 子系统）|
| 打包 | PyInstaller --onefile | **未实现**（见 release/）|
| 日志 | `logging`（stdlib） | **MVP 阶段未实现**（只用 print 到 stdout/stderr）|

**选型原则**：
- **能少即少** — 已有库能解决就不引新的（`pyproject.toml dependencies = []`）
- **能标准即标准** — 优先 Python stdlib，第三方库谨慎
- **跨平台** — CLI 必须 Win10+ / macOS / Linux 兼容

---

## 4. 开发规范

### 4.1 代码风格

- 遵循 PEP 8（Python 官方风格指南）
- 用 `black` 格式化（如果引入）
- 类型注解：可选，但公共 API 必须有

### 4.2 提交规范

- 用 Conventional Commits 格式：
  ```
  feat(todo): 实现 x todo add 命令
  
  - 支持 --priority / --deadline / --tags 参数
  - 自动生成任务 ID（kebab-case + 数字后缀）
  - 创建任务文件夹和 TODO.md
  
  Closes #12
  ```

### 4.3 测试规范

- 每个核心功能必须有单元测试 **+ 行为规格**
- 测试文件命名：`test_<module>.py` 或 `test_<command>_<action>.py`
- 行为规格文件命名：`<command>-behavior.md`（存放在 `docs/behaviors/`）
- 覆盖率目标：≥ 80%
- **BDD+TDD 强制要求**：见 §5

---

## 5. 开发方法论（BDD + TDD）

> **核心理念**：行为规格驱动测试，测试驱动实现

### 5.1 开发流程（强制）

```
┌─────────────────┐
│ 1. BDD 阶段     │ ← 写行为规格（Given-When-Then）
│   （行为描述）    │    
└────────┬────────┘
         ↓
┌─────────────────┐
│ 2. TDD 阶段     │ ← 写测试用例（Red）
│   （测试先行）    │ ← 运行测试，确认失败（Red）
└────────┬────────┘
         ↓
┌─────────────────┐
│ 3. 实现阶段     │ ← 写最小实现（Green）
│   （代码实现）    │ ← 重构（Refactor）
└────────┬────────┘
         ↓
┌─────────────────┐
│ 4. 验证阶段     │ ← 所有测试通过
│   （提交前检查）  │ ← 行为规格覆盖完整
└─────────────────┘
```

**禁止**：
- ❌ 跳过 BDD 阶段直接写测试
- ❌ 跳过 TDD 阶段直接写实现
- ❌ 行为规格和实现不一致

### 5.2 BDD 行为规格格式

**文件位置**：`docs/behaviors/<command>-behavior.md`

**格式**（Given-When-Then）：

```markdown
# <命令名> 行为规格

## 场景：<场景描述>

**Given**（前置条件）：
- <条件 1>
- <条件 2>

**When**（触发动作）：
- <动作描述>

**Then**（预期结果）：
- <结果 1>
- <结果 2>
```

### 5.3 TDD 测试格式

**文件位置**：`tests/test_<module>.py` 或 `tests/test_<command>_<action>.py`

**格式**（对应 BDD 场景）：

```python
import pytest
from core.models import Task

def test_add_task_success():
    """对应 BDD 场景：成功添加任务"""
    # Given: 准备测试环境
    task_name = "科目一模拟考"
    priority = "high"
    deadline = "2026-08-31"
    
    # When: 执行 x todo add 命令
    result = add_task(name=task_name, priority=priority, deadline=deadline)
    
    # Then: 验证结果
    assert result.exit_code == 0
    assert "✅ 任务已创建" in result.output
    assert Task.exists("kemu1")
    assert Task.load("kemu1").status == "pending"
```

### 5.4 开发顺序（实际案例）

**任务**：实现 `x todo add` 命令（已完成，见 commit `eab6dac`）

1. **BDD 阶段**：
   - 创建 `docs/behaviors/todo-add-behavior.md`
   - 写 8 个场景：成功 / 默认值 / 重复名 / 非法 priority / 非法 deadline / tags / 不写未指定字段 / 无任务名
   - 提交：`docs(behaviors): 新增 5 个 x todo BDD 行为规格（39 场景）`

2. **TDD 阶段**：
   - 创建 `tests/test_todo_add.py`
   - 写 8 个测试用例（对应 8 个场景）
   - 提交：`test: 新增 x todo add 测试用例（Red）`

3. **实现阶段**：
   - 在 `x.py` 里加 `_todo_add` handler（MVP 阶段 inline）
   - 跑测试 → 全部通过（Green）
   - 提交：`feat(x.py): 实现 5 个 todo action`

4. **验证阶段**：
    - 跑 `pytest`（全量 336 tests）→ 通过
   - 检查行为规格覆盖率
   - 提交：`chore: x todo add 开发完成`

---

## 6. 命令设计规范

### 6.1 总入口：`x`

**格式**：`x <子命令> [选项]`

**示例**：
```bash
x todo list              # 列出 TODO 任务
x todo add "任务名"      # 添加任务
x skill list            # 列出技能（未来）
x system backup        # 系统备份（未来）
```

**实际全局选项**（MVP）：
- `-v, --version` — 显示版本号（已实现）
- `-h, --help` — 显示帮助（argparse 默认）
- `--config <路径>` / `--log-level <级别>` — **未实现**（docs 列了，实现没收）

### 6.2 子命令分发（MVP 实现）

**主入口 `x.py`** 维护 `SUBCOMMAND_HANDLERS` 字典（MVP 阶段）：

```python
SUBCOMMAND_HANDLERS: dict[str, Callable[[Sequence[str]], int]] = {
    "todo": _todo_run,
}
```

**未来 Phase 4** 才改用 importlib 动态加载：

```python
# 伪代码（Phase 4 实现后）
import importlib
handler = importlib.import_module(f"plugins.{subcommand}").run
```

### 6.3 MVP 阶段 inline 实现

**当前阶段**（Phase 1 / v0.2.0）：5 个 x todo action 全部 inline 在 x.py：
- `x todo list` — 列表（带过滤）
- `x todo add` — 添加
- `x todo update` — 更新（status/priority/deadline/tags）
- `x todo archive` — 归档（带 reason）
- `x todo stats` — 统计

**后期扩展**（Phase 4）：拆分插件机制
- 主入口：`x.py`（只负责解析子命令 + 字典分发 → 改为 importlib 动态加载）
- 插件：`plugins/todo.py`（5 个 action 全部搬出）
- `x skill` / `x system` 插件按需新增

### 6.4 退出码约定

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 通用错误（未知子命令） |
| 2 | 参数错误（非法 status/priority/reason/deadline 格式、缺必填参数、缺 --xxx） |
| 3 | 任务不存在 |
| 4 | 任务已归档（重复 archive / 不可 update） |
| 5 | 数据完整性问题（YAML 解析失败 / 归档碰撞） |

---

## 7. 开发最佳实践

> **参考文档**: [开发最佳实践指南](file:///C:/Users/Chatx-cli/Desktop/开发最佳实践指南.md)

### 7.1 强制要求

- ✅ **BDD + TDD 先行**（详见 §5）
  - 先写行为规格（`docs/behaviors/<command>-behavior.md`）
  - 再写测试用例（`tests/test_<module>.py`）
  - 最后写实现代码
- ✅ **文档同步更新**
  - 代码变更后，同步更新 `AGENTS.md` / `README.md` / `docs/*.md`
  - 文档更新和代码变更放在**同一个提交**
- ✅ **AI 自动 Git 管理**
  - 每个完整功能完成后自动提交（Conventional Commits 格式）
  - 功能分支开发（`feature/<功能名>`）

### 7.2 推荐工作流

```
1. 搜索现有项目（GitHub `gh search repos "<功能> cli" --sort stars`）
2. 写 BDD 行为规格（Given-When-Then）
3. 写 TDD 测试用例（Red → Green → Refactor）
4. 实现代码（最小实现）
5. AI 自动提交（`feat/fix/test/docs` 前缀）
6. 更新文档（同步代码变更）
```

---

## 8. 关键决策记录

### 2026-06-21：项目启动 + MVP 完成

- ✅ 创建 `x-cli` 项目（替代 `x-cli (project)`）
- ✅ 定义统一入口 `x`（x-cli 总控）
- ✅ 定义开发方法论（BDD + TDD，文档先行）
- ✅ 定义技术栈（Python + argparse + stdlib-only）
- ✅ MVP 完成（v0.2.0）：
  - core 库（parser/models/storage/slug）手写 stdlib-only
  - 5 个 x todo action 全部实现（list / add / update / archive / stats）
  - 336 tests pass，覆盖率 93%
  - v0.3.0 新增 `x secret` 子系统（独立 JSON DB，8 子命令）
  - 与 `<legacy-credentials-dir>/` 隔离（不依赖 legacy TODO system）
  - 与 `<xcli_todo_dir>/` 真实数据 round-trip byte-identical（SHA-256 验证）
  - 5 个 BDD 行为规格（39 场景）覆盖所有 action
  - **E2E 子进程测试**（`tests/test_e2e_todo.py`，22 用例）— 真正启动 `x.exe` 跑 `subprocess.run`，盖住 `pyproject.toml` 脚本入口 + 环境变量路由

**venv 强制**（2026-06-21 加的决策）：
- 系统 Python 3.14.2 被 `hydra-core` 拉入的 `antlr4` 污染，pytest 跑不起来
- **必须**用 venv：`.venv\Scripts\python.exe -m pytest` / `pip install -e ".[dev]"`
- venv Scripts 加到用户 PATH（一次性，README 有命令）
- 详见 README "故障排查"

**`x secret` 独立 DB**（2026-06-21 加的决策）：
- x-cli's secret 功能**不**读 `<legacy-credentials-dir>/` 作为主存储
- 自管 JSON DB：`%LOCALAPPDATA%\x-cli\secrets.json`（Windows）/ `~/.local/share/x-cli/secrets.json`（Unix）
- 原因：x-cli 是**通用** CLI 工具，不应该耦合 legacy TODO system的特定目录布局
- migration 命令 (`x secret import --from`) 是单向辅助，不双向同步
- 用户从 legacy TODO system迁过来 → x-cli 后，x-cli 那边不删，可手动核对

**踩坑教训**（写在这里给后续 agent 看）：
1. **Phase 3 拆太多并行 task** — 5 个 worker 同时改 x.py 容易 merge 冲突，每个都要 cold-start + verify。**1 个 task 搞定**省 4 个 cold-start + 4 个 verify
2. **worker 引入第三方依赖**（pypinyin/jieba）违反"能少即少"原则 → **owner 是最后一道关卡**，必须 override。手动 revert + stdlib 重写
3. **manual_retry 时机** — 必须在 verifier PASS 前提交才有 retry 效果

### 决策记录

- ✅ **不引 PyYAML** — 手写 parser，未知字段 round-trip 保留（用户字段如 `paused_at` / `description` / `pause_reason` 不丢）
- ✅ **不引 pypinyin/jieba** — 硬编码 50+ 常用汉字拼音表 + `unicodedata` 处理非汉字，stdlib-only
- ✅ **不引 click** — argparse 够用，避免依赖
- ✅ **MVP 阶段 SUBCOMMAND_HANDLERS 字典分发** — 推迟 importlib 动态加载到 Phase 4
- ✅ **`x secret` 独立 DB（v0.3.0）** — 跟 legacy TODO system完全解耦，详见 [docs/architecture.md §11](docs/architecture.md) 和上方的 "`x secret` 独立 DB" 决策块
- ✅ **`x todo` 独立 DB（v0.4.0 规划中）** — 跟 `x secret` 对齐，从 `<xcli_todo_dir>/` 迁到 `%LOCALAPPDATA%\x-cli\todo\` (Win) / `~/.local/share/x-cli/todo/` (Unix)。**不再读写 legacy TODO system的 TODO 目录**（除非用户显式 `--from` 走 import）。`XCLI_TODO_DIR` 环境变量保留作为向后兼容。
- ❌ **不支持子命令缩写**（`x t l` = `x todo list`）— argparse 不原生支持，argcomplete 补全更直接
- ❌ **不引入交互式 TUI**（rich）— 个人使用 + 表格 + 颜色 emoji 已够用

### 待决策

- [ ] `x todo restore`（从归档还原到 active）— 用户场景不明，等用户提
- [ ] `x todo init`（首次初始化 `<xcli_todo_dir>/`）— 等用户提
- [ ] `x --config` / `--log-level` 全局选项优先级（用户没提过）
- [ ] PyInstaller 打包优先级（用户没提过）

---

## 9. 禁忌

- ❌ 不要引入不必要的依赖（"能少即少"原则）— 当前 `dependencies = []`
- ❌ 不要修改现有 YAML frontmatter 格式（兼容性原则）
- ❌ 不要创建同名的空目录
- ❌ **不要在 x.py 单文件里无限堆代码** — MVP 阶段已超 500 行（实际 731 行），Phase 4 拆 `plugins/todo.py` 时必须迁出 5 个 `_todo_*` handler
- ❌ 不要在没有单元测试和行为规格的情况下提交核心逻辑代码
- ❌ 不要跳过 BDD 阶段直接写测试
- ❌ 不要跳过 TDD 阶段直接写实现
- ❌ 不要在 commit 里引入 pypinyin / jieba / PyYAML / click / rich（已确认不需要）

---

## 10. 参考资料

| 文件 | 路径 | 说明 |
|------|------|------|
| 开发最佳实践指南 | `C:\Users\Chatx-cli\Desktop\开发最佳实践指南.md` | 完整开发方法论 |
| x-cli 计划书 | `C:\Users\Chatx-cli\Desktop\x-cli-计划书.md` | 完整设计文档 |
| 现有 TODO 规范 | `C:\Users\Chatx-cli\.x-cli\TODO\00-TODO-SPEC.md` | v1.3（已过时）|
| 现有总索引 | `C:\Users\Chatx-cli\.x-cli\TODO\TODO.md` | v1.6（自动生成）|
| x-cli-c2 AGENTS.md | `D:\code\windows\x-cli-c2\AGENTS.md` | 项目规约参考 |

---

*本文件是活文档，随项目进展更新。Phase 1 完成时间：2026-06-21。*
