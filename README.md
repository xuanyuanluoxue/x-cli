# x-cli

> **Xavier 个人工具集的统一 CLI 入口**  
> 一个 `x` 命令，管理所有个人工具

---

## 🚀 快速开始

### 安装（Windows / Python 3.14.2）

**当前阶段**（v0.2.0）：源码 + venv，**PyInstaller 打包未做**。

```powershell
# 1. 克隆并进入项目
git clone <repo-url> x-cli
cd x-cli

# 2. 建 venv（隔离 hydra-core / antlr4 等环境污染）
py -3.14 -m venv .venv

# 3. 安装（editable 模式，源码改动即时生效）
.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 4. 把 venv Scripts 加到用户 PATH（一次性）
$env:Path = "$env:Path;$pwd\.venv\Scripts"
[Environment]::SetEnvironmentVariable("Path", $env:Path, "User")

# 5. 重开 PowerShell，验证
x --version        # x 0.2.0
x todo list        # 列出 ~/.xavier/TODO/任务/ 下的任务
x todo stats       # 📊 统计信息
```

**未来**（Phase 3）：从 GitHub Release 下载单文件二进制（`x.exe` ~10MB，PyInstaller --onefile）。

### 故障排查

| 问题 | 解决 |
|------|------|
| `x` 不是 cmdlet | 重开 PowerShell（PATH 改了，进程内不刷新）|
| `ModuleNotFoundError: antlr4` | 系统 Python 被 hydra-core 污染，必须用 venv |
| `pytest` 报 `PluggyTeardownRaisedWarning` | 同上，用 `.venv\Scripts\python.exe -m pytest` |

### 基本用法

```bash
# TODO 管理（5 个 action 全部可用）
x --version                              # 看版本
x todo list                              # 列出任务
x todo list --status in_progress         # 按状态过滤
x todo list --priority high --tag 驾照   # 组合过滤
x todo add "科目一模拟考" --priority high --deadline 2026-08-31 --tags 驾照,暑假
x todo update kemu1 --status in_progress
x todo archive kemu1 --reason done       # reason: done/cancelled/expired/failed
x todo stats                             # 看统计

# Secret 管理（独立 JSON DB，与 xavier 系统隔离）
x secret list                            # 列出所有密钥（不显示值）
x secret get minimax                     # 取一个（输出 value + 警告）
x secret set minimax --value sk-xxx --category 接口密钥
x secret update minimax --value sk-new   # 改 value
x secret rm minimax                      # 删一个
x secret search api                      # 按 name/note 模糊搜（不搜 value）
x secret import --from C:/path/to/密钥   # 从 .md 批量迁移（旧文件保留）
x secret export                          # 备份到 JSON

# 环境变量
XAVIER_TODO_DIR=/path/to/test python x.py todo list   # 测试时切数据源
XCLI_SECRETS_DIR=/path/to/test python x.py secret list # 测试时切密钥库
```

---

## 📚 文档

| 文档 | 路径 | 说明 |
|------|------|------|
| **项目规约** | [AGENTS.md](AGENTS.md) | AI agent 必读 |
| **架构设计** | [docs/architecture.md](docs/architecture.md) | 架构设计（MVP 实际状态） |
| **命令参考** | [docs/commands.md](docs/commands.md) | 完整命令参考 |
| **行为规格** | [docs/behaviors/](docs/behaviors/) | BDD 行为规格（5 个 action，39 场景） |

---

## 🎯 项目愿景

### 核心理念

**`x` = Xavier 个人工具集的统一入口**

> "一个 `x` 命令，管理所有个人工具"

### 设计目标

| 目标 | 说明 |
|------|------|
| **统一入口** | 所有 Xavier 工具通过 `x <子命令>` 访问 |
| **插件化** | 每个功能模块作为独立插件（`x todo` / `x skill` / `x system`）|
| **跨平台** | Win10+ / macOS / Linux 兼容 |
| **易扩展** | 新功能只需添加新插件，不改主入口 |
| **文档先行** | BDD + TDD 开发模式，保证质量 |
| **stdlib-only** | `dependencies = []`，零第三方依赖 |

---

## 🔧 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| CLI 框架 | `argparse`（stdlib）|
| 数据格式 | YAML frontmatter（手写 parser，**不引 PyYAML**）|
| Slug 生成 | `unicodedata` + 硬编码拼音表（**不引 pypinyin**）|
| 数据存储 | 文件系统（`~/.xavier/TODO/`） |
| 配置 | `~/.xavier/config.yaml`（**MVP 未实现**，暂用 `XAVIER_TODO_DIR` 环境变量） |
| 测试 | `pytest` + `pytest-cov`（**当前 262+ tests / 92% 覆盖**，含 E2E 子进程测试）|
| 打包 | PyInstaller --onefile（**未实现**） |

---

## 📊 当前状态

### ✅ 已完成（Phase 1 MVP，v0.2.0，2026-06-21）

- ✅ 项目结构定义（标准目录结构）
- ✅ 开发方法论定义（BDD + TDD，文档先行）
- ✅ 技术栈选型（Python + argparse + stdlib-only）
- ✅ 命令设计规范（统一入口 `x` + 字典分发）
- ✅ core 库：parser / models / storage / slug（手写 stdlib-only）
- ✅ 5 个 x todo action：list / add / update / archive / stats
- ✅ 5 个 BDD 行为规格（39 场景）
- ✅ 262+ tests pass / 92% 覆盖率
- ✅ 与 `~/.xavier/TODO/` 真实数据 byte-identical round-trip

### ⏳ 进行中

- 无（Phase 1 已完成，等用户提 Phase 2+ 需求）

### ⏳ 待开始

- ⏳ Phase 2: `x todo init` / `x todo restore` / 完整配置管理（`--config` / `--log-level`）
- ⏳ Phase 3: PyInstaller 打包（`x.exe` ~10MB）+ GitHub Release
- ⏳ Phase 4: 拆 `plugins/todo.py`（把 5 个 action 从 x.py 迁出）+ importlib 动态加载
- ⏳ 远期: `x skill` / `x system` 插件（按需）

---

## 🤝 贡献

本项目是**个人使用**工具，不接受外部贡献。

AI agent 接续开发前**必须先读 [AGENTS.md](AGENTS.md)**。

---

## 📝 许可证

MIT License

---

## 📋 Roadmap

### Phase 1: MVP（最小可行产品）— ✅ 完成（v0.2.0）

**目标**: 实现 `x todo` 基础命令

| 功能 | 状态 |
|------|------|
| `x todo list` | ✅ 完成 |
| `x todo add` | ✅ 完成 |
| `x todo update` | ✅ 完成 |
| `x todo archive` | ✅ 完成 |
| `x todo stats` | ✅ 完成 |

**交付物**（已达成）：
- ✅ `x todo list` 能列出所有任务
- ✅ `x todo add` 能添加任务（兼容现有 YAML frontmatter，未知字段 round-trip 保留）
- ✅ 测试覆盖率 92%
- ✅ 文档完整（AGENTS.md + README.md + docs/）

### Phase 2: 完整功能（按需启动）

**目标**: 实现 `x todo` 全部命令 + 配置管理

| 功能 | 状态 |
|------|------|
| `x todo init` | ⏳ 待开始 |
| `x todo restore`（从归档还原） | ⏳ 待开始 |
| `x --config` | ⏳ 待开始 |
| `x --log-level` | ⏳ 待开始 |
| 真实 `~/.xavier/config.yaml` 加载 | ⏳ 待开始（`XAVIER_TODO_DIR` 是临时替代） |

### Phase 3: 打包发布（按需启动）

**目标**: 打包为单文件可执行

| 功能 | 状态 |
|------|------|
| PyInstaller 打包 | ⏳ 待开始 |
| GitHub Release | ⏳ 待开始 |
| 安装脚本 | ⏳ 待开始 |

### Phase 4: 高级功能（可选）

**目标**: 拆插件 + 高级特性

| 功能 | 状态 |
|------|------|
| `plugins/todo.py` 拆分（迁出 x.py） | ⏳ 可选 |
| `x skill` 插件 | ⏳ 可选 |
| `x system` 插件 | ⏳ 可选 |
| 交互式 TUI | ⏳ 可选（无需求） |
| Git 自动提交 | ⏳ 可选（无需求） |
| 提醒功能 | ⏳ 可选（无需求） |

---

## 🔍 现有 TODO 系统分析

### ✅ 优点

- YAML frontmatter 单源真源
- 自动生成总索引（`regen-index.ps1`）
- 规范化程度高

### ❌ 问题

- 维护成本高（规范文档易过时）
- 手动编辑 YAML 易出错
- PowerShell 脚本依赖（不跨平台）
- 无交互式 CLI

---

## 💡 为什么不用现有项目？

### 搜索结果

| 项目 | Star | 说明 |
|------|------|------|
| **[todotxt/todo.txt-cli](https://github.com/todotxt/todo.txt-cli)** | **6,122 ⭐** | 最老牌（2014 年），纯文本格式 |
| [Doist/todoist-cli](https://github.com/Doist/todoist-cli) | 226 ⭐ | Todoist 官方 CLI（需联网）|
| [sioodmy/todo](https://github.com/sioodmy/todo) | 394 ⭐ | 现代风格，单二进制 |

### 决策

- ❌ `todotxt/todo.txt-cli` 用纯文本格式，而 x-cli 需要 YAML frontmatter（兼容现有数据）
- ❌ `Doist/todoist-cli` 绑定 Todoist 服务（需要联网）
- ❌ `sioodmy/todo` 功能不符合 x-cli 的需求（需要 `—priority` / `—deadline` 等参数）
- ✅ 决策：**参考它们的 CLI 设计，但自己实现**

---

## 🤔 常见问题

### Q1: 为什么叫 `x`？

**A**: `x` 是 Xavier 的首字母，也是**最短的命令名**（1 个字符）。

### Q2: 支持子命令缩写吗？

**A**: MVP 阶段不支持缩写（保持简单）。后期可以通过 `aliases=["l"]` 轻松添加缩写支持。

### Q3: 会支持 Tab 补全吗？

**A**: 会（`argparse` 原生支持 Tab 补全，后期添加）。

### Q4: 能兼容现有 TODO 系统吗？

**A**: 能。`x todo` 命令完全兼容现有 YAML frontmatter 格式。**未知字段（如 `paused_at` / `description` / `pause_reason`）会原样保留**。

### Q5: 跟现有 `regen-index.ps1` 脚本冲突吗？

**A**: 不冲突。`x todo archive` / `x todo stats` 会自动维护 `TODO.md` 总索引；你也可以继续用 `regen-index.ps1` 手动重建。

---

*最后更新：2026-06-21（v0.2.0 MVP 完成）*
