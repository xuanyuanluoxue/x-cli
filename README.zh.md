# x-cli

> 个人 CLI 工具集：**任务管理** + **凭证存储**。
> 一个 `x` 命令，两个子系统，**零第三方依赖**。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests: 526](https://img.shields.io/badge/tests-526%20passing-brightgreen.svg)](tests/)
[![Coverage: 93%](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)](tests/)

> English version: [README.md](README.md)

## 这是什么？

一个 `x` 命令，背后两个专注的子系统：

- **`x todo`** — 个人 TODO 管理，后端是 YAML frontmatter 的 Markdown 文件。
  全生命周期：add / list / update / archive / restore / search / done / stats / init / import。
  CJK 友好（支持中文任务名）。归档留痕（archive 任务永不被删除）。
- **`x secret`** — 本地凭证存储，后端是单一 JSON 文件（POSIX mode 600）。
  list / get / set / update / rm / search / import / export。默认复制到剪贴板。

两个子系统的数据**独立存储**在每用户数据目录下：

| 平台 | TODO | 密钥 |
|---|---|---|
| Windows | `%LOCALAPPDATA%\x-cli\todo\` | `%LOCALAPPDATA%\x-cli\secrets.json` |
| Unix | `$XDG_DATA_HOME/x-cli/todo/` | `$XDG_DATA_HOME/x-cli/secrets.json` |

无云同步、无遥测、无加密（暂未做）。为单用户、单机器设计。

## 快速开始

```bash
# 克隆并安装（editable 模式，源码改动即时生效）
git clone https://github.com/xavier-pen/x-cli
cd x-cli

# 用 venv 隔离（Python 3.14 系统包会被 hydra-core / antlr4 污染，
# 这俩会被 pytest 自动加载，可能导致 pytest 起不来）
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # Unix
.venv\Scripts\pip install -e ".[dev]"  # Windows

# 验证
x --version
x todo --help        # 注意 — 见下方"已知怪癖"

# 试一试
x todo add "驾照考取" --priority high --deadline 2026-08-31
x todo list
x todo stats
```

### 已知怪癖

- **`x --help` 和 `x todo --help` 返回同样的顶层帮助。** 顶层 argparse 在 dispatch 到子命令之前就把 `--help` 吃掉了。要看子命令的 action 列表，用 `x todo`（无参数）/ `x secret`（无参数）。见 [docs/behaviors/e2e-cli-behavior.md](docs/behaviors/e2e-cli-behavior.md)。
- **`x` 必须在 PATH 上。** Windows 上，venv 装的 `x.exe` 在 `.venv\Scripts\x.exe`。如果该目录不在 PATH，需要加进去（或者用 `C:\Users\X\.local\bin\x.bat` 包一层）。

## 用法

### `x todo` — 任务管理

```bash
# 生命周期
x todo add "科目一模拟考" --priority high --deadline 2026-08-31 --tags 驾照,暑假
x todo list                                            # 只列 active
x todo list --all                                      # active + archived
x todo list --status in_progress --priority high       # 组合过滤
x todo update kemu1 --status in_progress
x todo archive kemu1 --reason done                     # 软删除到归档
x todo done kemu1                                      # 快捷方式: archive --reason done
x todo restore kemu1                                   # 归档 → active
x todo search 暑假                                      # name + note + tags
x todo stats                                           # 按 status / priority / due-soon 统计
x todo init --dir /path/to/seed                        # 引导一个存储
x todo import --from /path/to/legacy --dry-run         # 单向迁移
```

每个任务独占一个文件夹：

```
<xcli_todo_dir>/
├── 任务/<name>/TODO.md              # active 任务（一个 .md 一个任务）
└── 归档/<YYYYMMDD>-<name>/TODO.md   # archived 任务（日期前缀 = 归档日）
```

Markdown body（YAML frontmatter 之后的部分）原样保留 — 当笔记本用。未知的 frontmatter 字段 round-trip 保存。完整格式见 [docs/TODO-SPEC.md](docs/TODO-SPEC.md)。

### `x secret` — 凭证存储

```bash
x secret list                                         # 只列 name + category（**永不**显示 value）
x secret get minimax                                  # value 写到剪贴板 + stdout + stderr 警告
x secret set minimax --value sk-xxx --category 接口密钥
x secret update minimax --value sk-new --note "rotated 2026-06"
x secret rm oldkey                                    # 删除
x secret search api                                   # name + note，**永不**搜 value
x secret import --from /path/to/legacy-markdown-dir   # 单向迁移，源保留
x secret export                                       # JSON 备份
```

**硬性约束**（CLI 强制，破坏会立即坏测试）：

- `x secret list` **永不**显示 value。测试：`test_e2e_list_never_shows_value`。
- `x secret get` **永远**在 stdout 之前写 stderr 警告。测试：`test_e2e_get_returns_value`。
- `x secret search` **永不**匹配 value 字段。测试：`test_e2e_search_does_not_match_value`。
- `x secret import` 只读 — 源文件永不被修改。

JSON DB 在 POSIX 上文件 mode `0600`。Windows 上 ACL 继承自用户 profile（除了这之外无额外加固）。如需静态加密，见 [Roadmap](#roadmap)。

### 全局 flag

```bash
x --version                  # 显示版本并退出
x --config /path/to/config.yaml     # 加载 YAML 配置（优先级高于 env var）
x --log-level DEBUG          # 单次调用覆盖日志级别
x --config-init              # 写默认配置到 <xcli_data_dir>/config.yaml
```

配置优先级链：`CLI --config > XCLI_CONFIG env > <xcli_data_dir>/config.yaml > 硬编码默认值`。

## 为什么造这个轮子？

需要一个能一次性干下面三件事的命令：

1. 管理个人 TODO 列表，支持 CJK 任务名、截止日期、标签，归档留痕（archive 的任务不删）。
2. 本地存 API key，能 `x secret get foo` 直接进剪贴板。
3. 不打扰我（无云、无遥测、无三方依赖）。

从一套老旧的 TODO + 密钥 Markdown 系统（需要手动 regen 索引）演化而来。迁移路径用 `x todo import --from <dir>` 和 `x secret import --from <dir>`，都是单向、只读。

## 文档

| 文档 | 用途 |
|---|---|
| [COMMANDS.md](COMMANDS.md) | 命令清单（用户编辑的 spec 源） |
| [docs/TODO-SPEC.md](docs/TODO-SPEC.md) | `x todo` 磁盘格式规范 |
| [docs/architecture.md](docs/architecture.md) | 设计决策、存储层、硬性约束 |
| [docs/commands.md](docs/commands.md) | 完整命令参考 |
| [docs/behaviors/](docs/behaviors/) | BDD 行为规格（Given-When-Then）— 14 个文件、100+ 场景 |
| [AGENTS.md](AGENTS.md) | 接续 x-cli 的 AI agent 必读 |

## 开发

```bash
# 跑测试
.venv/bin/pytest                                   # Unix
.venv\Scripts\python.exe -m pytest                 # Windows
.venv\Scripts\python.exe -m pytest --cov=core --cov=x  # 带覆盖率

# BDD 先行的开发流
# (1) 改 COMMANDS.md，把要做的命令加到 ⏳ 区或 backlog
# (2) 在 docs/behaviors/<command>-behavior.md 写 BDD 规格
# (3) 提交规格（单独的 doc commit）
# (4) 在 tests/test_<command>.py 写测试          → 跑测试，看 Red
# (5) 在 x.py 或 core/*.py 写实现                 → 跑测试，看 Green
# (6) 提交实现 + 测试
```

完整开发规约（含"COMMANDS.md 是 spec 源"的硬规则）见 [AGENTS.md](AGENTS.md)。

## Roadmap

**已完成**（v0.4.y，当前）：
- 21 个命令（`x todo` 10 + `x secret` 8 + 3 个全局 flag）
- 526 测试通过，4 个平台条件跳过，93% 覆盖率
- CJK 任务名 + 输出图标
- `x secret get` 剪贴板集成
- 可配置日志级别 + 日志路径
- 从老旧 TODO 目录 / 密钥 Markdown 目录的单向 import

**候选**（未承诺）：
- 静态加密的密钥存储（目前是明文 JSON）
- 基于 Git 的 TODO 目录版本控制（`git init` + 自动 commit hooks）
- 插件拆分（`plugins/todo.py` 从 `x.py` 拆出）
- PyInstaller 单文件二进制分发

**不做**（设计决定）：
- 云同步、多设备
- 团队 / 多用户
- 交互式 TUI（plain stdout + 表格已经够用）

## 许可证

MIT。详见 [LICENSE](LICENSE)。Copyright (c) 2026 Xavier。

## 贡献

工具小巧个人用。Bug 报告和 PR 欢迎 — 非平凡改动请先开 issue 讨论设计再写代码。读这个仓库的 AI agent **必须**先读 [AGENTS.md](AGENTS.md)。