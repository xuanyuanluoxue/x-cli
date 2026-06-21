# 架构设计

> **目标读者**：接续开发 x-cli 的 AI agent 或人类开发者
> **必读**：**在写代码前必须先读本文档**
> **状态**：本文档反映 **v0.2.0 MVP 实际架构**（2026-06-21）

---

## 1. 整体架构

### 1.1 MVP 阶段：单文件 + core 库（当前实际）

**MVP 阶段采用「主入口 + 核心库」分层**（不是微内核），原因：todo 5 个 action 加起来不到 500 行逻辑，拆插件的收益不抵成本。

```
x.py  (731 行，单文件)
├── 主入口 (build_parser / main)
├── --version 处理
├── SUBCOMMAND_HANDLERS 字典 → {"todo": _todo_run}
└── _todo_run → 5 个 action handler（inline）
    ├── _todo_list
    ├── _todo_add
    ├── _todo_update
    ├── _todo_archive
    └── _todo_stats

core/  (核心库，被 x.py 引用)
├── models.py    ← Task dataclass + 3 个 enum（TaskStatus/Priority/ArchiveReason）
├── parser.py    ← YAML frontmatter 解析/序列化（手写，stdlib-only）
├── slug.py      ← 中英文 slug 生成（stdlib-only，50+ 硬编码拼音 + unicodedata）
└── storage.py   ← TaskStore：文件系统 CRUD + 统计 + 索引维护
```

**核心理念**：
- **主入口 `x.py`**：解析 + 字典分发，**未启用 importlib**
- **核心库 `core/`**：纯 stdlib，**零第三方依赖**（`pyproject.toml dependencies = []`）
- **数据存储**：直接读 `<xcli_todo_dir>/任务/<name>/TODO.md` 和 `<xcli_todo_dir>/归档/<YYYYMMDD>-<name>/TODO.md`

### 1.2 Phase 4 目标：微内核（未来）

```
x (主入口 — 字典分发 → 改 importlib 动态加载)
├── 插件系统（importlib.import_module）
│   ├── plugins/todo.py    ← 从 x.py 迁出
│   ├── plugins/skill.py   ← 未来
│   ├── plugins/system.py  ← 未来
│   └── ...
├── 配置管理（<xcli_config_path>）— 未实现
├── 日志系统（<xcli_data_dir>/）— 未实现
└── 自动更新（未来）
```

### 1.3 数据流（MVP 实际）

```
用户输入: x todo list --status pending
    ↓
x.py build_parser: 解析 --version / subcommand
    ↓
SUBCOMMAND_HANDLERS["todo"]("list --status pending")
    ↓
_todo_run: argparse 解析 list 的子参数（--status/--priority/--tag/--all）
    ↓
_todo_list: 调 TaskStore().list_tasks() 拿所有 active 任务
    ↓
core/storage.py: glob 任务/<name>/TODO.md → parse_frontmatter → Task
    ↓
core/models.py: Task dataclass（未知字段在 extra，round-trip 不丢）
    ↓
返回 list[Task] → 过滤 → 表格输出到 stdout
    ↓
退出码 0
```

---

## 2. 命令分发机制

### 2.1 MVP 实现：字典分发（实际）

**主入口 `x.py`**（实际代码，不是伪代码）：

```python
SUBCOMMAND_HANDLERS: dict[str, Callable[[Sequence[str]], int]] = {
    "todo": _todo_run,
}

def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parsed, remaining = parser.parse_known_args(argv if argv is not None else None)
    if parsed.version:
        print(f"x {__version__}")
        return 0
    if not parsed.subcommand:
        parser.print_help()
        return 0
    handler = SUBCOMMAND_HANDLERS.get(parsed.subcommand)
    if handler is None:
        print(f"❌ 错误：未知子命令：{parsed.subcommand}", file=sys.stderr)
        return 1
    return handler(remaining)
```

**优点**：简单、可静态分析、IDE 跳转方便
**缺点**：加子命令要改 x.py（不像 importlib 那样纯插件化）

### 2.2 Phase 4 目标：importlib 动态加载

```python
# 伪代码（Phase 4 实现后）
import importlib
handler_module = importlib.import_module(f"plugins.{subcommand}")
return handler_module.run(remaining)
```

### 2.3 todo 子命令分发（inline）

x.py 里 `_todo_run` 解析 todo_action 后按名字分发：

```python
if parsed.todo_action == "list":
    return _todo_list(parsed)
elif parsed.todo_action == "add":
    return _todo_add(parsed)
# ... 5 个 action
```

---

## 3. 配置管理（**未实现**）

### 3.1 计划中的配置文件

**全局配置**：`<xcli_config_path>`（**未实现**）

```yaml
# <xcli_config_path> （计划格式）
todo:
  default_status: pending
  default_priority: medium
  tasks_dir: <xcli_todo_dir>/任务

log:
  level: INFO
  file: <xcli_data_dir>/x.log
```

### 3.2 临时替代：`XCLI_TODO_DIR` 环境变量

**MVP 阶段**没有 config 加载，只支持一个环境变量覆盖 TODO 根目录（主要给测试用）：

```bash
XCLI_TODO_DIR=/tmp/test_todo python x.py todo list
```

代码位置：`core/storage.py:_default_todo_dir()`

### 3.3 计划中的 `core/config.py`（**未实现**）

```python
# 伪代码（未实现）
import yaml
import os

def load_config(config_path=None):
    if config_path is None:
        config_path = os.path.expanduser("<xcli_config_path>")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
```

> 注：即使将来实现，也**不引 PyYAML** — 用 `core/parser.py` 已有的 YAML 解析能力（仅限标量/列表/字典场景）。

---

## 4. 数据存储

### 4.1 数据格式：YAML frontmatter

**手写 parser**（`core/parser.py`），不引 PyYAML。原因：
- 未知字段 round-trip 保留（用户自定义字段如 `paused_at` / `description` 不丢）
- 减少依赖
- 行为完全可控

```markdown
---
id: kemu1
name: 科目一模拟考
status: pending
priority: high
created: 2026-06-21
updated: 2026-06-21
deadline: 2026-08-31
folder: 任务/科目一模拟考
tags: ["驾照", "暑假"]
---

# 科目一模拟考

## 笔记

- 需要刷模拟题
- 预约考试日期
```

**已知字段**（`core/models.py:_KNOWN_FIELDS`）：
`id` / `name` / `status` / `priority` / `created` / `updated` / `deadline` / `folder` / `tags` / `subtasks` / `reason`

**未知字段**：落到 `Task.extra`，dump 时按原顺序写出。

### 4.2 目录结构

```
<xcli_todo_dir>/
├── TODO.md                  # 总索引（自动维护，由 x todo archive/stats 触发）
├── 00-TODO-SPEC.md          # 规范文档（手动维护）
├── 任务/                    # 活动任务
│   ├── 科目一模拟考/
│   │   └── TODO.md
│   └── 自主实习/
│       └── TODO.md
└── 归档/                    # 已归档
    └── 20260615-劳动教育III/
        └── TODO.md
```

### 4.3 存储层入口（`core/storage.py:TaskStore`）

**核心方法**：

| 方法 | 用途 | 退出码关联 |
|------|------|-----------|
| `list_tasks(include_archived)` | 列任务 | — |
| `get_task(name_or_id, include_archived)` | 查单个 | 3（不存在）|
| `add_task(task)` | 加任务 | 3（已存在）|
| `update_task(id, **kwargs)` | 更新 | 3/4 |
| `archive_task(name_or_id, reason)` | 归档（移文件夹）| 4/5 |
| `stats()` | 统计 | 5（YAML 损坏）|
| `update_inventory_on_archive(old_status)` | 维护 TODO.md 索引 | 5 |

**构造方式**：
```python
TaskStore()                              # 用 <legacy-config-dir>/TODO
TaskStore(todo_dir=Path("/tmp/test"))    # 测试用
```

`XCLI_TODO_DIR` 环境变量优先级最高（覆盖构造参数）。

---

## 5. 日志系统（**未实现**）

### 5.1 计划

**日志级别**（从低到高）：`DEBUG` / `INFO` / `WARNING` / `ERROR`

**日志输出**：
- 控制台：≥ `WARNING`（只显示错误和警告）— **未实现**（MVP 用 print）
- 文件：`<xcli_data_dir>/x.log`（≥ `INFO`）— **未实现**

### 5.2 MVP 替代

直接 `print()` 到 `stdout`（成功信息、表格）或 `stderr`（错误信息）。退出码区分成功/失败，不写日志文件。

---

## 6. 错误处理（实际）

### 6.1 退出码（MVP 实际）

| 退出码 | 含义 | 触发场景 |
|--------|------|---------|
| 0 | 成功 | 正常完成 |
| 1 | 通用错误 | 未知子命令（argparse 不识别）/ 占位 action（_todo_not_implemented） |
| 2 | 参数错误 | 非法 status/priority/reason/deadline 格式、缺必填参数、缺 --xxx |
| 3 | 任务不存在 | list / update / archive 找不到任务 |
| 4 | 任务已归档 | 重复 archive / 对已归档任务 update |
| 5 | 数据完整性 | YAML 解析失败（stats 检测到 broken 文件）/ 归档目标碰撞 |

### 6.2 错误消息格式

**成功**（stdout）：
```
✅ 任务已创建：科目一模拟考（ID: kemu1）
```

**业务错误**（stderr）：
```
❌ 任务不存在：kemu99
💡 提示：运行 'x todo list' 查看现有任务 ID
```

**用法错误**（stderr，argparse 风格）：
```
usage: x todo add [-h] [--priority PRIORITY] [--deadline DEADLINE] [--tags TAGS] 名称
x todo add: error: argument --priority: invalid choice: 'urgent' (choose from 'high', 'medium', 'low')
```

---

## 7. 测试策略（实际）

### 7.1 测试层次

| 层次 | 工具 | 当前覆盖 |
|------|------|---------|
| **核心库单元测试** | `pytest` | test_models / test_parser / test_storage（~150 tests）|
| **CLI 集成测试** | `pytest` + 子进程 | test_todo_list / test_todo_add / test_todo_update / test_todo_archive / test_todo_stats（~90 tests）|
| **主入口测试** | `pytest` | test_x（覆盖 argparse / SUBCOMMAND_HANDLERS 分发）|
| **BDD 行为规格** | Given-When-Then 文档 | 5 个文件，39 场景（与测试用例一一对应）|

### 7.2 覆盖率目标

- **核心库**（`core/`）：≥ 90%（**当前 91%+**）
- **CLI handler**（`x.py` 里的 `_todo_*`）：≥ 80%
- **全局**：≥ 80%（**当前 91%**）

### 7.3 测试运行

```bash
pytest                    # 全量
pytest tests/test_parser.py   # 单文件
pytest -k test_add         # 按名字过滤
pytest --cov=core --cov=x  # 带覆盖率
```

---

## 8. 打包与发布（**未实现**）

### 8.1 PyInstaller 打包（计划）

```bash
# release/build.py 未实现
pyinstaller --onefile --name x x.py
```

**产物**：
- Windows: `dist/x.exe`（~10 MB）
- macOS / Linux: `dist/x`（~10 MB）

### 8.2 GitHub Release（计划）

通过 GitHub Actions：
1. 打 tag（`v0.3.0`）
2. 跑 pytest
3. 跑 PyInstaller
4. 上传二进制到 Release

---

## 9. 未来扩展

### 9.1 插件市场（可选，Phase 4+）

- 插件仓库（GitHub）
- 插件元数据（`plugin.yaml`）
- 自动下载 + 安装

### 9.2 交互式 TUI（**无需求**）

> 不计划实现。表格 + emoji 已够用，且 TUI 会增加 `rich` / `textual` 依赖。

### 9.3 Git 自动提交（**无需求**）

> 用户用 `regen-index.ps1` 自己手动管理 .x-cli git，不让 x-cli 抢 Git 控制权。

---

## 10. 关键架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| YAML 解析 | 手写 parser | 未知字段 round-trip；零依赖 |
| 拼音转换 | 硬编码 + unicodedata | 不引 pypinyin（保持 stdlib-only）|
| CLI 框架 | argparse | 够用；不引 click |
| 插件加载 | 字典分发（MVP）→ importlib（Phase 4）| 5 个 action 不值得拆 |
| 数据存储 | 文件系统（todo） + JSON DB（secret） | todo 兼容 `<xcli_todo_dir>/`；secret 用独立 JSON（不与 legacy TODO system耦合）|
| 测试框架 | pytest + pytest-cov | Python 生态标准 |
| 打包 | PyInstaller | 单文件可执行，跨平台 |

---

## 11. x secret 模块设计（2026-06-21 新增）

### 11.1 定位

x-cli 的密钥管理子命令。**不**与 legacy TODO system的 `<legacy-credentials-dir>/` 耦合——x-cli 是通用工具，应有独立数据源。

### 11.2 存储

- **位置**（跨平台）：
  - Windows: `%LOCALAPPDATA%\x-cli\secrets.json`
  - Unix: `$XDG_DATA_HOME/x-cli/secrets.json` → fallback `~/.local/share/x-cli/secrets.json`
- **覆盖**：环境变量 `XCLI_SECRETS_DIR`
- **格式**：JSON（单个 dict，`version: "1.0"` + `secrets: [...]`）
- **权限**：600（Windows 用 ACL）
- **加密**：MVP 不加密（明文 + 文件权限保护；后期加 `--encrypt` flag）

### 11.3 模块结构

```
core/
  paths.py          ← 跨平台路径解析（xcli_data_dir / xcli_secrets_path）
  secrets.py        ← SecretStore 类（CRUD + search + import + export）
  importer.py       ← 从 .md 迁移的解析器（YAML frontmatter + text 代码块）

x.py                ← _secret_run + 8 个 _secret_* handler（inline MVP）

tests/
  test_paths.py     ← 路径解析（跨平台 mock）
  test_secrets.py   ← SecretStore 单元测试
  test_importer.py  ← .md 迁移解析单元测试
  test_e2e_secret.py← E2E 子进程测试
```

### 11.4 关键约束（硬性）

| 约束 | 原因 |
|------|------|
| `list` 永不显示 value | 避免 `> log.txt` 泄露 |
| `get` 永远 stderr 警告 | 提醒用户密钥已离开数据库 |
| `search` 不搜 value | 避免 grep 撞到 |
| 文件权限 600 | OS 级保护 |
| MVP 不引 `cryptography` | 保持 stdlib-only |

### 11.5 迁移策略（`x secret import`）

从 `<legacy-credentials-dir>/*.md` 解析：

| DB 字段 | 来源 |
|---------|------|
| `name` | `.md` 文件的 `## <section>` 标题 |
| `category` | 文件名（去 `.md`）|
| `value` | 整个 `text` 代码块原文（多行 `key:value`）|
| `note` | section 上面的 metadata 表格（如「用途」「状态」）|

**单向**，**不**删除旧文件。详细 BDD 见 `docs/behaviors/secret-behavior.md`（17 场景）。

---

*本文档是活文档，随架构演进更新。MVP 实际状态时间：2026-06-21。*
