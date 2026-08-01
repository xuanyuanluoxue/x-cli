# x-cli

> 用一个本地 `x` 命令管理任务、凭证、日记、笔记和浏览器界面。
> Python 3.10+，零运行时依赖，提供 Windows 独立 EXE。

[![CI](https://github.com/xuanyuanluoxue/x-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/xuanyuanluoxue/x-cli/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/xuanyuanluoxue/x-cli)](https://github.com/xuanyuanluoxue/x-cli/releases/latest)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

[English](README.md)

## 发布状态

**v0.8.0 已正式发布：** [查看说明与下载](https://github.com/xuanyuanluoxue/x-cli/releases/tag/v0.8.0)。

WinGet 清单正在接受
[Microsoft 审核](https://github.com/microsoft/winget-pkgs/pull/403912)。
只有在清单合并并确认进入默认源后，这里才会公布可直接执行的一键安装命令。

Windows 用户目前可以从 v0.8.0 Release 下载 `x-windows-x86_64.exe`。
它是无需 Python 的独立便携程序。Release 同时提供 SHA-256、wheel、源码包和
已验证的 WinGet 清单。

## 能做什么

| 命令 | 用途 | 存储 |
|---|---|---|
| `x todo` | 任务生命周期、筛选、提醒、重复、模板、依赖、批量操作、回收站和导出 | Markdown + YAML frontmatter |
| `x secret` | 本地多字段凭证、剪贴板读取、导入和导出 | JSON |
| `x diary` | 追加每日记录、列出最近日期 | Markdown |
| `x note` | 创建、列出、查看和搜索带标签的主题笔记 | Markdown + YAML frontmatter |
| `x web` | 任务和凭证的本地浏览器界面 | 使用同一份本地数据 |

x-cli 面向单用户、单机器，不做云同步、遥测、团队空间，也不增加第三方运行依赖。

## 与 x-cmd 的关系

x-cli 与 [x-cmd](https://x-cmd.com) 都以 `x` 开头。x-cmd 是一个 POSIX shell
工具包（"Shell Superpowers for AI Agents"），提供 300+ 模块和 600+ 按需加载的
包。两个项目都选择了 `x` 作为简短快速的命令名，且 x-cmd 的设计——"Shell 版的
Python 标准库"、POSIX 优先、按需加载——也影响了 x-cli 零依赖、纯文本工具集的
理念。

- **使用方式可能冲突，功能没有冲突。** 同时安装两个项目会在同一台机器上出现
  两个 `x` 命令——shell 会解析 `PATH` 中靠前的那个（x-cmd 安装时还会移除已有
  的 `x` 别名）。功能上互补：x-cmd 负责 POSIX shell 与 agent 生态，x-cli 负责
  Windows 原生个人数据（todo / secret / diary / note + Web UI）。
- **环境变量不冲突。** x-cmd 使用 `___X_CMD_*` 命名空间，x-cli 使用 `XCLI_*`；
  数据根目录各自独立（`$___X_CMD_ROOT_DATA` vs `%LOCALAPPDATA%\x-cli\` /
  `$XDG_DATA_HOME/x-cli/`）。
- **合作进行中。** 密钥库设计和 `todo` 模块已向上游提出
  （[讨论 #455](https://github.com/x-cmd/x-cmd/discussions/455)、
  [PR #456](https://github.com/x-cmd/x-cmd/pull/456)）。若上游模块成熟，两个
  项目可能合并或并存：x-cmd 模块服务 POSIX 与 agent，x-cli 保留 Windows 原生
  体验，长期来看两者可能共享统一的数据格式。

## 快速体验

```powershell
x --version

x todo add "准备科目一" --priority high --deadline 2026-08-31 --tags 驾照,暑假
x todo list
x todo done <任务 ID>

x diary "完成今天的复习"
x note add "API 配置" --body "配置记录" --tags API

x secret set example --value "replace-me" --category demo
x secret list

x web
```

使用 `x --help` 或 `x <子命令> --help` 查看当前版本的真实命令。
[COMMANDS.md](COMMANDS.md) 是用户维护的命令清单，
[docs/commands.md](docs/commands.md) 提供详细参考。

## 开发安装

使用虚拟环境，避免系统 Python 中无关的 pytest 插件污染项目：

```powershell
git clone https://github.com/xuanyuanluoxue/x-cli.git
cd x-cli
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"

x --version
```

Linux / macOS 请把 `.venv\Scripts\python.exe` 换成 `.venv/bin/python`。

## 数据与安全边界

| 平台 | 默认数据根目录 |
|---|---|
| Windows | `%LOCALAPPDATA%\x-cli\` |
| Linux / macOS | `$XDG_DATA_HOME/x-cli/` 或 `~/.local/share/x-cli/` |

任务、凭证、日记和笔记在根目录下分别存放。升级程序不会覆盖用户数据。

必须明确的边界：

- `x secret list` 和 `x secret search` 永不输出字段值。
- 凭证仍以明文 JSON 存储；浏览器里的掩码不等于静态加密。
- POSIX 上凭证库使用 `0600`；Windows 上继承当前用户目录 ACL。
- 导入是单向操作，不修改源数据。
- 任务的未知 frontmatter 字段和 Markdown 正文会原样保留。

迁移或批量修改前，请先备份本地数据。

## 本地 Web UI

```powershell
x web
x web --no-browser
x web --token "choose-a-token"
```

服务默认只绑定 `127.0.0.1:8421`。回环访问时认证为可选，可通过 `--token`
或 `web_auth: true` 开启。如果主动绑定非回环地址，应保持认证开启。

前端源码位于 `web/`，构建产物位于 `core/web/static/` 并提交进仓库，因此正式
安装包无需 Node.js 也能运行 Web UI。

## 文档

| 文档 | 用途 |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | 包含 v0.8.0 的版本历史 |
| [COMMANDS.md](COMMANDS.md) | 用户维护的功能清单 |
| [docs/commands.md](docs/commands.md) | 完整命令参考 |
| [docs/TODO-SPEC.md](docs/TODO-SPEC.md) | 任务磁盘格式 |
| [docs/architecture.md](docs/architecture.md) | 架构和硬性约束 |
| [docs/releasing.md](docs/releasing.md) | Windows、GitHub Release 和 WinGet 手册 |
| [docs/behaviors/](docs/behaviors/) | Given-When-Then 行为规格 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 开发与 PR 流程 |

## 开发

```powershell
$env:TMP = "D:\Temp\pytest_tmp"
$env:TEMP = "D:\Temp\pytest_tmp"

.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m pytest --cov=core --cov=plugins --cov=x --cov-fail-under=80
.venv\Scripts\python.exe -m ruff check core plugins x.py scripts tests
```

运行代码继续保持标准库实现。新命令放在 `plugins/`，共享逻辑放在 `core/`，
`x.py` 只负责入口。风险分级开发流程和必跑检查见 [AGENTS.md](AGENTS.md)。

## 许可证

MIT，详见 [LICENSE](LICENSE)。
