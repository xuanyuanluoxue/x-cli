# AGENTS.md

> **目标读者**：任何接续开发 x-cli 的 AI agent（不是人）
> **必读**：**任何任务开始前必须先读完相关文档，再动手**

---

## 0. 开工前必读（按顺序）

1. **本文件 (AGENTS.md)** — 项目规约
2. **[README.md](README.md)** — 项目主文档 + 快速开始
3. **[docs/architecture.md](docs/architecture.md)** — 架构设计
4. **[docs/commands.md](docs/commands.md)** — 完整命令参考
5. **[docs/behaviors/](docs/behaviors/)** — BDD 行为规格（按命令名组织）
6. 按任务类型读 docs/ 子文档：
   - 打包相关 → `docs/release.md`
   - 测试相关 → `docs/testing.md`
   - 插件开发 → `docs/plugin-dev.md`

**未读完直接动手 = 失败率高。** 文档里没写的 → **先问用户**，不要猜测。

---

## 1. 项目概述

| 项 | 值 |
|---|---|
| 名称 | **x-cli** |
| 性质 | **个人使用**（非团队、非商业）|
| 核心 | Xavier 个人工具集的统一 CLI 入口 |
| 目标用户 | 陈新捷（开发者本人）|
| 平台 | Win10+ / macOS / Linux |

**这不是**通用 CLI 框架，**是**针对个人使用场景定制的工具集。**别**套用通用 CLI 工具的设计模式。

---

## 2. 目录结构（重要）

```
x-cli/
├── AGENTS.md          ← 你正在读
├── README.md          ← 项目主文档 + 快速开始
├── CHANGELOG.md      ← 版本历史
├── .gitignore
├── pyproject.toml   ← Python 项目配置（待创建）
├── x.py               ← 主入口（MVP 阶段单文件）
├── plugins/           ← 插件目录
│   ├── __init__.py
│   ├── todo.py      ← x todo 插件（MVP）
│   ├── skill.py     ← x skill 插件（未来）
│   └── system.py    ← x system 插件（未来）
├── core/              ← 核心逻辑（后期拆分）
│   ├── __init__.py
│   ├── parser.py      ← YAML frontmatter 解析
│   ├── models.py      ← 数据模型（Task / Subtask）
│   ├── storage.py    ← 文件系统操作
│   └── indexer.py    ← 总索引生成
├── tests/             ← 测试
│   ├── __init__.py
│   ├── test_parser.py
│   └── test_storage.py
├── docs/              ← 详细文档
│   ├── architecture.md   ← 架构设计
│   ├── commands.md       ← 命令参考
│   ├── behaviors/       ← BDD 行为规格
│   │   ├── todo-add-behavior.md
│   │   ├── todo-list-behavior.md
│   │   └── ...
│   └── ...
└── release/           ← 打包脚本
    ├── build.py
    └── README.md
```

**关键约束**：
- `plugins/` 只能放插件代码（每个子命令一个文件）
- `core/` 只能放核心逻辑代码（可被多个插件共享）
- `tests/` 只能放测试代码
- `docs/behaviors/` 只能放 BDD 行为规格（Given-When-Then 格式）
- **不要**混

---

## 3. 技术栈（已定）

| 组件 | 技术 | 备注 |
|---|---|---|
| CLI 框架 | `argparse`（stdlib，支持子命令） | 不用 click（避免过度依赖）|
| 插件机制 | `importlib` 动态加载 | 子命令作为插件（`plugins/<name>.py`）|
| 数据格式 | **YAML frontmatter**（兼容现有） | 不迁移到 JSON/TOML |
| 数据存储 | 文件系统（同现有：`~/.xavier/TODO/`） | 不引入 DB |
| 配置 | `~/.xavier/config.yaml` | 全局配置（替代环境变量）|
| 测试 | `pytest` + `pytest-cov` | 覆盖率目标 ≥ 80% |
| 打包 | PyInstaller --onefile | 产物目标 ~10MB |
| 日志 | `logging`（stdlib） | 输出到 `~/.xavier/logs/` |

**选型原则**：
- **能少即少** — 已有库能解决就不引新的
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
- 测试文件命名：`test_<module>.py`
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

**示例**（`docs/behaviors/todo-add-behavior.md`）：

```markdown
# x todo add 行为规格

## 场景：成功添加任务

**Given**：
- 任务名称：`"科目一模拟考"`
- 优先级：`high`
- 截止日期：`2026-08-31`

**When**：
- 运行 `x todo add "科目一模拟考" --priority high --deadline 2026-08-31`

**Then**：
- 退出码：0（成功）
- 输出消息：`"✅ 任务已创建：科目一模拟考（ID: kemu1）"`
- 文件系统：`~/.xavier/TODO/任务/kemu1/TODO.md` 已创建
- YAML frontmatter：`status: pending`（默认值）
```

### 5.3 TDD 测试格式

**文件位置**：`tests/test_<module>.py`

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

### 5.4 开发顺序（示例）

**任务**：实现 `x todo add` 命令

1. **BDD 阶段**：
   - 创建 `docs/behaviors/todo-add-behavior.md`
   - 写 3 个场景：成功添加 / 缺少必填参数 / 重复任务名
   - 提交：`docs: 新增 x todo add 行为规格`

2. **TDD 阶段**：
   - 创建 `tests/test_todo_add.py`
   - 写 3 个测试用例（对应 3 个场景）
   - 运行 `pytest tests/test_todo_add.py` → **全部失败**（Red）
   - 提交：`test: 新增 x todo add 测试用例（Red）`

3. **实现阶段**：
   - 写 `plugins/todo.py`（最小实现）
   - 运行 `pytest tests/test_todo_add.py` → **全部通过**（Green）
   - 重构（如果有必要）
   - 提交：`feat(todo): 实现 x todo add 命令（Green）`

4. **验证阶段**：
   - 运行 `pytest`（全量测试）→ 通过
   - 检查行为规格覆盖率（`docs/behaviors/todo-add-behavior.md` 所有场景都有测试）
   - 提交：`chore: x todo add 开发完成`

---

## 6. 命令设计规范

### 6.1 总入口：`x`

**格式**：`x <子命令> [选项]`

**示例**：
```bash
x todo list              # 列出 TODO 任务
x todo add "任务名"      # 添加任务
x skill list            # 列出技能
x system backup        # 系统备份
```

### 6.2 子命令插件机制

**目录结构**：
```
x-cli/
├── x.py                 # 主入口（解析子命令）
└── plugins/            # 子命令插件
    ├── __init__.py
    ├── todo.py        # x todo 子命令
    ├── skill.py       # x skill 子命令（未来）
    └── system.py     # x system 子命令（未来）
```

**插件加载逻辑**（伪代码）：
```python
# x.py
import importlib

def main():
    subcommand = sys.argv[1]  # 第一个参数是子命令名
    plugin = importlib.import_module(f"plugins.{subcommand}")
    plugin.run(sys.argv[2:])  # 剩余参数传给插件
```

### 6.3 MVP 阶段简化

**当前阶段**（Phase 1）：只实现 `x todo` 子命令
- 主入口：`x.py`（单文件）
- 插件：`plugins/todo.py`（直接写在主文件，不拆插件）

**后期扩展**（Phase 4）：拆分插件机制
- 主入口：`x.py`（只负责解析子命令）
- 插件：`plugins/*.py`（每个子命令独立文件）

---

## 7. 开发最佳实践

> **参考文档**: [开发最佳实践指南](file:///C:/Users/Chatxavier/Desktop/开发最佳实践指南.md)

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

### 2026-06-21：项目启动

- ✅ 创建 `x-cli` 项目（替代 `xavier-todo`）
- ✅ 定义统一入口 `x`（Xavier CLI 总控）
- ✅ 定义插件机制（`x todo` / `x skill` / `x system`）
- ✅ 定义开发方法论（BDD + TDD，文档先行）
- ✅ 定义技术栈（Python + argparse + importlib）
- ❌ 未开始实现

### 待决策

- [ ] 是否引入 `PyYAML` 依赖？（手写解析器 vs 第三方库）
- [ ] 是否支持子命令缩写？（`x t l` = `x todo list`）
- [ ] 是否需要交互式 TUI？（`rich` 库 + `x todo tui` 命令）

---

## 9. 禁忌

- 不要引入不必要的依赖（"能少即少"原则）
- 不要修改现有 YAML frontmatter 格式（兼容性原则）
- 不要创建同名的空目录
- 不要在 `x.py`（MVP 阶段）里写超过 500 行的代码（拆分到 `plugins/`）
- 不要在没有单元测试和行为规格的情况下提交核心逻辑代码
- 不要跳过 BDD 阶段直接写测试
- 不要跳过 TDD 阶段直接写实现

---

## 10. 参考资料

| 文件 | 路径 | 说明 |
|------|------|------|
| 开发最佳实践指南 | `C:\Users\Chatxavier\Desktop\开发最佳实践指南.md` | 完整开发方法论 |
| x-cli 计划书 | `C:\Users\Chatxavier\Desktop\x-cli-计划书.md` | 完整设计文档 |
| 现有 TODO 规范 | `C:\Users\Chatxavier\.xavier\TODO\00-TODO-SPEC.md` | v1.3（已过时）|
| 现有总索引 | `C:\Users\Chatxavier\.xavier\TODO\TODO.md` | v1.6（自动生成）|
| xavier-c2 AGENTS.md | `D:\code\windows\xavier-c2\AGENTS.md` | 项目规约参考 |

---

*本文件是活文档，随项目进展更新*
