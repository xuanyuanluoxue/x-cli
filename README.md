# x-cli

> **Xavier 个人工具集的统一 CLI 入口**  
> 一个 `x` 命令，管理所有个人工具

---

## 🚀 快速开始

### 安装（待实现）

```bash
# 从 GitHub Release 下载二进制
curl -L https://github.com/xavier/x-cli/releases/latest/download/x.exe -o x.exe

# 或从源码安装
python setup.py install
```

### 基本用法

```bash
# TODO 管理
x todo list                 # 列出所有任务
x todo add "科目一模拟考" --priority high --deadline 2026-08-31
x todo update kemu1 --status archived --reason done
x todo stats                # 查看统计

# 未来扩展（示例）
x skill list               # 列出技能
x system backup           # 系统备份
```

---

## 📚 文档

| 文档 | 路径 | 说明 |
|------|------|------|
| **项目规约** | [AGENTS.md](AGENTS.md) | AI agent 必读 |
| **架构设计** | [docs/architecture.md](docs/architecture.md) | 架构设计（待创建）|
| **命令参考** | [docs/commands.md](docs/commands.md) | 完整命令参考（待创建）|
| **行为规格** | [docs/behaviors/](docs/behaviors/) | BDD 行为规格（Given-When-Then）|

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

---

## 🔧 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.8+ |
| CLI 框架 | `argparse`（stdlib，支持子命令）|
| 插件机制 | `importlib` 动态加载 |
| 数据格式 | YAML frontmatter（兼容现有 TODO 系统）|
| 数据存储 | 文件系统（`~/.xavier/TODO/`）|
| 配置 | `~/.xavier/config.yaml` |
| 测试 | `pytest` + `pytest-cov` |
| 打包 | PyInstaller --onefile |

---

## 📊 当前状态

### ✅ 已完成

- ✅ 项目结构定义（标准目录结构）
- ✅ 开发方法论定义（BDD + TDD，文档先行）
- ✅ 技术栈选型（Python + argparse + importlib）
- ✅ 命令设计规范（统一入口 `x` + 插件机制）

### ⏳ 进行中

- 📋 Phase 1: MVP（实现 `x todo` 基础命令）

### ⏳ 待开始

- ⏳ Phase 2: 完整功能（`x todo` 剩余命令 + 配置管理）
- ⏳ Phase 3: 打包发布（PyInstaller 单文件）
- ⏳ Phase 4: 高级功能（插件扩展 + 交互式 TUI）

---

## 🤝 贡献

本项目是**个人使用**工具，不接受外部贡献。

AI agent 接续开发前**必须先读 AGENTS.md**。

---

## 📝 许可证

MIT License（待定）

---

## 📋 Roadmap

### Phase 1: MVP（最小可行产品）

**目标**: 实现 `x todo` 基础命令

| 功能 | 状态 |
|------|------|
| `x todo list` | 📋 计划中 |
| `x todo add` | 📋 计划中 |
| `x todo update` | 📋 计划中 |
| `x todo archive` | 📋 计划中 |
| `x todo stats` | 📋 计划中 |

**交付物**:
- ✅ `x todo list` 能列出所有任务
- ✅ `x todo add` 能添加任务（兼容现有 YAML frontmatter）
- ✅ 测试覆盖率 ≥ 80%
- ✅ 文档完整（AGENTS.md + README.md + docs/）

### Phase 2: 完整功能

**目标**: 实现 `x todo` 全部命令 + 配置管理

| 功能 | 状态 |
|------|------|
| `x todo init` | ⏳ 待开始 |
| `x config` | ⏳ 待开始（管理配置文件）|
| `x --version` | ⏳ 待开始 |
| `x --help` | ⏳ 待开始 |

### Phase 3: 打包发布

**目标**: 打包为单文件可执行

| 功能 | 状态 |
|------|------|
| PyInstaller 打包 | ⏳ 待开始 |
| GitHub Release | ⏳ 待开始 |
| 安装脚本 | ⏳ 待开始 |

### Phase 4: 高级功能（可选）

**目标**: 扩展插件 + 高级特性

| 功能 | 状态 |
|------|------|
| `x skill` 插件 | ⏳ 可选 |
| `x system` 插件 | ⏳ 可选 |
| 交互式 TUI | ⏳ 可选 |
| Git 自动提交 | ⏳ 可选 |
| 提醒功能 | ⏳ 可选 |

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

**A**: 能。`x todo` 命令完全兼容现有 YAML frontmatter 格式。

---

*最后更新：2026-06-21*
