# x-cli

> 个人 CLI 工具集：任务、凭证、日记、主题笔记和本地 Web UI。
> 一个 `x` 命令，五个子系统，**零运行时依赖**。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-brightgreen.svg)](tests/)
[![Coverage: 93%](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)](tests/)

> English version: [README.md](README.md)

## 这是什么？

一个 `x` 命令，背后五个专注的子系统：

- **`x todo`** — 个人 TODO 管理，后端是 YAML frontmatter 的 Markdown 文件。
  全生命周期：add / list / update / archive / restore / search / done / stats / init / import。
  CJK 友好（支持中文任务名）。归档留痕（archive 任务永不被删除）。
- **`x secret`** — 本地凭证存储，后端是单一 JSON 文件（POSIX mode 600）。
  list / get / set / update / rm / search / import / export。默认复制到剪贴板。
- **`x diary`** — 本地每日 Markdown 日记，可追加内容或列出最近的日记日期。
- **`x note`** — 带标签和本地搜索的主题型 Markdown 笔记。
- **`x web`** — 本地 Web UI，用于访问 todo 和 secret 数据；Token 认证按需开启。

数据子系统彼此**独立存储**在每用户数据目录下：

| 平台 | TODO | 密钥 | 日记 | 主题笔记 |
|---|---|---|---|---|
| Windows | `%LOCALAPPDATA%\x-cli\todo\` | `%LOCALAPPDATA%\x-cli\secrets.json` | `%LOCALAPPDATA%\x-cli\diary\` | `%LOCALAPPDATA%\x-cli\notes\` |
| Unix | `$XDG_DATA_HOME/x-cli/todo/` | `$XDG_DATA_HOME/x-cli/secrets.json` | `$XDG_DATA_HOME/x-cli/diary/` | `$XDG_DATA_HOME/x-cli/notes/` |

无云同步、无遥测、无加密（暂未做）。为单用户、单机器设计。

## 安装

### WinGet（计划中的公开主渠道）

> **当前状态：尚未进入 WinGet 默认源。** 本地清单和发行流水线已经完成，
> 但首次 GitHub Release 和 `microsoft/winget-pkgs` 提交尚未执行。

微软接受清单后，Windows 用户不需要安装 Python，直接运行：

```powershell
winget install --id XuanyuanLuoxue.XCLI -e
winget upgrade --id XuanyuanLuoxue.XCLI -e
```

便携 EXE 的用户数据仍保存在 `%LOCALAPPDATA%\x-cli\`；升级程序不会覆盖
todo、secret、diary 或 note 数据。

### 开发安装

```bash
git clone https://github.com/xuanyuanluoxue/x-cli.git
cd x-cli
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # Unix
.venv\Scripts\pip install -e ".[dev]"  # Windows

x --version
x todo --help
x todo add "驾照考取" --priority high --deadline 2026-08-31
x diary "开始使用 x diary"
x note add "MiniMax API 配置" --body "这里是正文" --tags AI,API
```

顶层帮助和子命令帮助已经分开：`x --help`、`x todo --help`、
`x secret --help`、`x diary --help`、`x note --help`、`x web --help`
都会显示对应范围的帮助。

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

### `x diary` — 本地每日记录

```bash
x diary "完成 x diary P0 开发"  # 追加到今天的 Markdown 文件
x diary list                    # 最近 7 个有日记的日期
x diary list --limit 3          # 自定义数量
```

日记文件位于 `<xcli_data_dir>/diary/YYYY-MM-DD.md`。可通过
`XCLI_DIARY_DIR` 切换目录。P0 只列日期，不提供编辑、删除、搜索或同步。

### `x note` — 主题笔记

```bash
x note add "MiniMax API 配置" --body "这里是正文" --tags AI,API
x note list --tag AI --limit 10
x note show n-20260717-143012
x note search minimax --limit 5
```

每篇笔记保存到 `<xcli_data_dir>/notes/<id>.md`，使用 YAML frontmatter
保存元数据，正文保持 Markdown。可通过 `XCLI_NOTES_DIR` 切换目录。
P0 只做创建、列表、显示和搜索；编辑与删除留到后续版本。

### `x web` — 本地浏览器界面

```bash
x web                       # 默认 127.0.0.1:8421，不再要求输入 Token
x web --no-browser          # 启动但不自动打开浏览器
x web --token my-token      # 本次运行显式开启认证
```

默认配置为 `web_auth: false`，浏览器会直接进入控制台。如需重新开启随机
Token 认证，编辑 `<xcli_data_dir>/config.yaml`（Windows：
`%LOCALAPPDATA%\x-cli\config.yaml`）：

```yaml
web_auth: true
```

如果把 host 绑定到非本机回环地址，建议开启认证；否则能访问该地址的设备都能
读取和修改任务、密钥数据。

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
| [docs/releasing.md](docs/releasing.md) | Windows 构建、GitHub Release 和 WinGet 提交手册 |
| [docs/commands.md](docs/commands.md) | 完整命令参考 |
| [docs/behaviors/](docs/behaviors/) | 永久 BDD 行为规格（Given-When-Then） |
| [AGENTS.md](AGENTS.md) | 接续 x-cli 的 AI agent 必读 |

## 开发

```bash
# 跑测试
.venv/bin/pytest                                   # Unix
.venv\Scripts\python.exe -m pytest                 # Windows
.venv\Scripts\python.exe -m pytest --cov=core --cov=x  # 带覆盖率

# 按风险分级的开发流
# 小改动：不写计划；行为变化时补回归测试；只跑 focused tests
# 中等改动：简短计划；用户行为写 BDD；TDD；交付前全量测试一次
# 高风险改动：完整计划 + 必要 ADR；全量测试 + 对应发行/安全验证
```

准确的分级标准和必跑检查见 [AGENTS.md](AGENTS.md)。`COMMANDS.md` 仍是用户拥有的功能规格。

## Roadmap

**当前本地 v0.7.0 已完成：**
- TODO 全生命周期、时间精度、子任务、提醒字段、重复规则、批量操作、模板、依赖、回收站删除和 JSON/CSV/Markdown 导出
- Secret 本地存储、列表/搜索隐私保护和剪贴板集成
- 本地日记、主题笔记和可选认证的 Web UI
- CLI、Python 元数据、EXE 和 WinGet 清单共用一个版本来源
- Windows x64 单文件 EXE，内含 Web 静态资源，无需预装 Python
- 自动生成 SHA-256 和 WinGet 1.12.0 portable 清单
- GitHub Actions 自动构建，并阻止错误版本 tag 发布

**候选**（未承诺）：
- 静态加密的密钥存储（目前是明文 JSON）
- 基于 Git 的 TODO 目录版本控制（`git init` + 自动 commit hooks）
- 可选常驻后台进程（提醒和 AI 本地工作流）

**不做**（设计决定）：
- 云同步、多设备
- 团队 / 多用户
- 交互式 TUI（plain stdout + 表格已经够用）

## 许可证

MIT。详见 [LICENSE](LICENSE)。Copyright (c) 2026 Xavier。

## 贡献

工具小巧个人用。Bug 报告和 PR 欢迎 — 非平凡改动请先开 issue 讨论设计再写代码。读这个仓库的 AI agent **必须**先读 [AGENTS.md](AGENTS.md)。
