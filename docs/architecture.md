# 架构设计

> **目标读者**：接续开发 x-cli 的 AI agent 或人类开发者
> **必读**：**在写代码前必须先读本文档**
> **状态**：本文档反映 **v0.7.0 实际架构**（2026-07-17）

---

## 1. 整体架构

### 1.1 当前架构：延迟分发的模块化单体（v0.7.x）

**x-cli 5 层架构**（从上到下）：

```
x.py  (entry point only)
├── --version / --config / --log-level / --config-init 全局 flag
├── build_parser() / main()
└── main() → early-exit → 加载 config + log → 请求 core.dispatch 分发

core/dispatch.py  (静态白名单 + 延迟加载)
├── SUBCOMMAND_MODULES: {"todo": "plugins.todo", ...}
└── load_subcommand_handler(name) → importlib → plugin.run

plugins/  (子命令插件与 TODO 内部分层)
├── todo.py              ← x todo parser + dispatcher facade
├── todo_presenters.py   ← 纯展示、过滤与校验 helpers
├── todo_queries.py      ← list / search / stats / export
├── todo_lifecycle.py    ← archive / restore / reminder / repeat / remove
├── todo_mutations.py    ← add / update / init / import / template
├── secret.py  ← x secret 命令族
├── diary.py   ← x diary 写入 + 最近日期列表
├── note.py    ← x note 主题笔记 add/list/show/search
└── web.py     ← x web 本地 HTTP 服务 + 静态前端

core/  (核心库，被 x.py + plugins/ 共享)
├── dispatch.py    ← 内建插件白名单 + 延迟加载
├── models.py      ← Task dataclass + 3 个 enum
├── parser.py      ← YAML frontmatter 解析/序列化（手写，stdlib-only）
├── slug.py        ← 中英文 slug 生成（stdlib-only）
├── paths.py       ← 跨平台路径解析（todo / secret / diary / notes / config / log）
├── formatting.py  ← CJK-aware display helpers（display_width + pad）
├── storage.py     ← TaskStore：文件系统 CRUD + 统计 + 索引维护
├── secrets.py     ← SecretStore：JSON DB CRUD + import + export
├── diary.py       ← DiaryStore：每日 Markdown 追加 + 日期列表
├── note.py        ← NoteStore：主题 Markdown 创建、列表、显示、搜索
├── config.py      ← AppConfig + YAML 解析（v0.4.y）
├── logging.py     ← stdlib logging wrapper（v0.4.y）
└── web/           ← 本地 HTTP API、认证与静态资源

# 第三方依赖：0（dependencies = []）
```

**Plugin 合约**（每个 `plugins/<name>.py` 必须实现）：

```python
def register(parser: argparse.ArgumentParser) -> None:
    """绑子命令 + flags 到 parser"""

def run(args: Sequence[str]) -> int:
    """解析 + 派发，返回 exit code"""
```

**加新子命令的步骤**：
1. 创建 `plugins/<name>.py`，实现 `register` + `run`
2. 在 `core.dispatch:SUBCOMMAND_MODULES` 加 1 行静态映射
3. 用户可见行为发生变化时写 BDD，并按风险分级补测试

**核心理念**：
- **Entry point `x.py` 只做 argparse + config + log + 派发**
- **Plugins `plugins/` 各自独立**，互不依赖
- **核心库 `core/` 纯 stdlib，零三方依赖**（`pyproject.toml dependencies = []`）
- **依赖方向固定**：`x → core.dispatch → selected plugin → core`；`core` 禁止反向导入 `x`
- **插件按需加载**：顶层 version/help/未知命令不导入具体插件
- **数据存储**：x-cli 独立于外部系统（`%LOCALAPPDATA%\x-cli\` Windows / `~/.local/share/x-cli/` Unix）

### 1.2 Phase 4 历史：从单文件到插件（已完成 v0.5.0）

v0.4.y 之前 `x.py` 是 1739 行单文件，所有 18 个 handler inline。Phase 4 拆分：
- v0.2.0-v0.4.y：单文件 + `SUBCOMMAND_HANDLERS` 字典分发（1739 行）
- v0.5.0：拆出 `plugins/todo.py` + `plugins/secret.py`，`x.py` 降到 215 行
- 拆分前后均由完整 pytest 回归保护；具体数量不在架构文档中硬编码

未来可能的扩展（**不**在当前 scope — 见 COMMANDS.md backlog）：
- `plugins/foo.py` 加新子命令（流程见 1.1）
- 可选后台提醒服务复用 core API，不改变 CLI 主进程架构

### 1.3 数据流（MVP 实际）

```
用户输入: x todo list --status pending
    ↓
x.py build_parser: 解析 --version / subcommand
    ↓
core.dispatch.load_subcommand_handler("todo")
    ↓
plugins.todo.run("list --status pending")
    ↓
plugins.todo: argparse 解析 list 的子参数（--status/--priority/--tag/--all）
    ↓
plugins.todo_queries._todo_list: 调 TaskStore().list_tasks() 拿所有 active 任务
    ↓
core/storage.py: glob 任务/<name>/TODO.md → parse_frontmatter → Task
    ↓
core/models.py: Task dataclass（未知字段在 extra，round-trip 不丢）
    ↓
返回 list[Task] → 过滤 → 表格输出到 stdout
    ↓
退出码 0
```

### 1.4 Web 前端架构

自 v0.8.0 起，Web 前端是一个 **Vue 3 SPA**（ADR-0002）。源码集中在仓库根目录的 `web/`
文件夹内（`web/src/**`），用 Vite 构建；构建产物输出到 `core/web/static/`，由
`core/web/server.py` 以 `Cache-Control: no-store` 同源服务。Python 运行时仍保持
stdlib-only——Node/Vite 仅是**开发期**工具链，最终用户无需安装。

- **技术栈**：Vue 3 `<script setup>` SFC + Vue Router 4（hash 模式）+ Pinia。
- **构建**：`cd web && npm run build` → `core/web/static/`（`emptyOutDir`，产物提交进 git，
  保证 `pip install` 后无需 Node 即可 `x web`）。
- **路由**：hash 模式（`#/tasks`、`#/secrets/:name` …），与旧版形态一致，无需服务端
  history fallback。路由守卫先查询 `/api/health`；`auth_required: false` 时直接进入，
  为 `true` 时才启用登录守卫，401 全局跳 `#/login`。
- **服务端**：`core/web/server.py` 仍以 `core/web/static/` 为静态根；`token=None` 表示
  默认直访模式，字符串 Token 表示认证模式。

前端的安全边界：

- 默认配置 `web_auth: false`，依靠 `127.0.0.1` 回环绑定限制访问；配置为 `true` 或
  显式传 `--token` 后恢复 Token 保护。
- 认证模式下 Token 仅存于 `localStorage["x_web_token"]`，每个 API 请求通过
  `X-Web-Token` 传递。
- 密钥列表只请求 summary，不获取或渲染 `value`（`getSecret` 不出现在列表 bundle）。
- 密钥详情页必须先弹出明文警告，用户确认后才请求单条记录。
- 所有静态资源同源本地加载，不连接 CDN 或外部字体服务。

---

## 2. 命令分发机制

### 2.1 静态白名单 + importlib 延迟加载

插件注册表使用完整模块名，不根据用户输入直接拼接路径：

```python
SUBCOMMAND_MODULES = {
    "todo": "plugins.todo",
    "secret": "plugins.secret",
    "diary": "plugins.diary",
    "note": "plugins.note",
    "web": "plugins.web",
}

def load_subcommand_handler(name: str):
    module_name = SUBCOMMAND_MODULES.get(name)
    if module_name is None:
        return None
    module = importlib.import_module(module_name)
    handler = getattr(module, "run", None)
    if not callable(handler):
        raise TypeError(f"plugin {module_name!r} has no callable run")
    return handler
```

`x.py` 先处理 `--version`、顶层 help、配置和未知命令；只有合法子命令真正需要执行时才调用 loader。具体行为见 `docs/behaviors/cli-lazy-dispatch-behavior.md`，决策背景见 ADR-0001。

**优点**：

- version/help 启动路径不加载无关子系统。
- 白名单保留可审计性，不允许任意模块导入。
- `x.py` 不再承担插件私有函数的兼容出口。

**代价**：PyInstaller 无法只靠 AST 发现字符串导入，因此发行 spec 和 EXE 冒烟测试必须覆盖所有内建插件。

### 2.2 插件内部动作分发

每个插件的 `run(args)` 自己构建 argparse 并分发子动作。例如 TODO 插件：

```python
if parsed.todo_action == "list":
    return _todo_list(parsed)
elif parsed.todo_action == "add":
    return _todo_add(parsed)
# ...其余 TODO actions
```

顶层入口不理解 `list/add/archive` 等插件内部动作。

---

## 3. 配置管理（已实现）

`core.config.AppConfig` 管理五个字段：`todo_dir`、`secrets_path`、
`log_level`、`log_path`、`web_auth`。配置仍使用手写 YAML parser，不引入 PyYAML。

默认文件位于 `<xcli_data_dir>/config.yaml`，可用 `x --config-init` 创建。
解析优先级从高到低：

1. CLI `--config <path>`
2. `XCLI_CONFIG` 环境变量
3. 默认 `config.yaml`
4. `core.paths` 提供的跨平台默认值

```yaml
todo_dir: D:/data/x-cli/todo
secrets_path: D:/data/x-cli/secrets.json
log_level: WARNING
log_path: D:/data/x-cli/x.log
web_auth: false
```

`XCLI_TODO_DIR`、`XCLI_SECRETS_DIR`、`XCLI_DIARY_DIR`、`XCLI_NOTES_DIR`
仍可用于单个数据子系统的路径覆盖和测试隔离。未知配置字段被忽略，以保留向前兼容性；显式配置文件不存在或字段非法时返回配置错误。

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

**已知字段**以 `core.models.Task` 为准，包括基础字段以及 `time`、
`end_time`、`duration_min`、`parent`、`remind`、`repeat`、`depends` 和正文。

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
TaskStore()                              # 用 core.paths.xcli_todo_dir()
TaskStore(todo_dir=Path("/tmp/test"))    # 测试用
```

显式 `todo_dir` 构造参数优先；未传入时由 `core.paths.xcli_todo_dir()` 解析环境变量和跨平台默认目录。

---

## 5. 日志系统（已实现）

`core.logging.setup_logging()` 配置 `x` 命名空间 logger，支持
`DEBUG / INFO / WARNING / ERROR / CRITICAL`。默认级别为 `WARNING`；
`--log-level` 可以覆盖配置文件。

- stderr handler 与当前有效级别一致。
- `log_path` 非空时追加 UTF-8 文件日志；父目录自动创建。
- 重复初始化会先移除旧 handler，避免同一条日志重复输出。
- 用户命令的正常结果仍通过 stdout 输出；错误提示和安全警告走 stderr。

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
| **核心库单元测试** | `pytest` | models / parser / storage / secrets / note / diary |
| **CLI 集成测试** | `pytest` + 子进程 | todo / secret / diary / note / help / config |
| **主入口与架构测试** | `pytest` | `test_x.py` + `test_dispatch.py`（argparse、延迟加载、依赖方向）|
| **Web 前端契约** | `pytest`（断言构建产物）+ 本地浏览器 | SPA 入口/hashed assets、相对路径、无 CDN、密钥列表不泄露明文、明文查看需确认、可访问性 |
| **BDD 行为规格** | Given-When-Then 文档 | 只描述需要长期保留的用户行为与关键非功能契约 |

### 7.2 覆盖率目标

- **核心库**（`core/`）：目标 ≥ 90%
- **CLI handler**（`plugins/`）：≥ 80%
- **全局**：目标 ≥ 80%

### 7.3 按风险选择流程

| 改动 | 计划与规格 | 验证边界 |
|------|------------|----------|
| 小型文档/help/局部修复 | 不写计划；BDD 可选 | 行为变化时补回归测试，只跑 focused tests |
| 用户功能或多模块改动 | 简短临时计划；新用户行为写 BDD；TDD | 开发时 focused tests，交付前全量一次 |
| 架构/数据/安全/后台/发行 | 完整临时计划；必要 ADR；BDD + TDD 按需 | focused + 全量 + 与改动相关的安全、EXE 或发行检查 |

不按固定任务数量暂停，也不在每个小步骤重复跑全量测试。临时计划完成后删除；永久结论保留在 BDD、ADR、本文档或 changelog。准确规则以仓库根目录 `AGENTS.md` 为准。

### 7.4 测试运行

```bash
pytest                    # 全量
pytest tests/test_parser.py   # 单文件
pytest -k test_add         # 按名字过滤
pytest --cov=core --cov=x  # 带覆盖率
```

---

## 8. 打包与发布（v0.7.0 已实现）

### 8.1 单一版本来源

`core/version.py:__version__` 是唯一版本常量。`x.py` 直接导入它，
setuptools 通过 `[tool.setuptools.dynamic]` 读取它，WinGet 生成器会拒绝
与它不一致的版本。这样 CLI、wheel、EXE、tag 和 WinGet 不会各自漂移。

### 8.2 Python 包

`pyproject.toml` 使用递归包发现：`core*` + `plugins*`，并显式包含
`core.web/static/**`（Vue SPA 构建产物）。运行时依赖仍然为零；`build`、`PyInstaller`
只属于 `release` 可选依赖。前端源码在 `web/`（不进 Python 包）；改动前端后须先
`cd web && npm run build` 重新生成 `core/web/static/` 再打包。

```powershell
.venv\Scripts\python.exe -m build --no-isolation
```

产物为 wheel 和 sdist。wheel 构建测试会检查 Web handlers 和静态资源，
防止 editable install 正常、正式安装缺文件。

### 8.3 Windows 独立程序

`packaging/x-cli.spec` 使用 PyInstaller one-file console 模式生成：

```text
dist/x-windows-x86_64.exe
dist/x-windows-x86_64.exe.sha256
```

完整入口是 `scripts/build-windows.ps1`。它按顺序执行 pytest、Python 包构建、
PyInstaller、版本帮助冒烟测试、真实 Web 首页 HTTP 冒烟测试和 SHA-256 生成。
EXE 不申请管理员权限，不启用 UPX，用户不需要安装 Python。

### 8.4 WinGet

`scripts/generate_winget_manifest.py` 使用 stdlib 生成 WinGet 1.12.0 singleton
清单。当前只有一个 Windows x64 安装文件，所以采用 `portable`：WinGet 负责
放置 EXE、注册 `x` 命令别名、升级和卸载。

```text
PackageIdentifier: XuanyuanLuoxue.XCLI
InstallerType: portable
Architecture: x64
Command: x
```

GitHub Release 是不可变下载源。清单提交前必须运行 `winget validate`；微软
默认源接受前，README 不得声称安装命令当前可用。

### 8.5 GitHub Actions

`.github/workflows/release.yml` 分成两个权限边界：

1. `build`：`contents: read`，全量测试、构建、生成并验证清单、上传私有 artifact。
2. `release`：仅 tag 触发，`contents: write`，下载已验证 artifact 并创建 Release。

`workflow_dispatch` 永远只走 build。只有 `vX.Y.Z` tag 与源码版本完全一致时
才允许进入 release job。

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
| 插件加载 | 静态白名单 + importlib 延迟加载 | version/help 不加载无关插件，同时阻止任意模块导入 |
| 数据存储 | 文件系统（todo） + JSON DB（secret） | todo 兼容 `<xcli_todo_dir>/`；secret 用独立 JSON（不与 legacy TODO system耦合）|
| 测试框架 | pytest + pytest-cov | Python 生态标准 |
| 打包 | PyInstaller one-file（Windows x64） | 首次发行简单；约 10 MiB，无需预装 Python |
| Windows 分发 | GitHub Release + WinGet portable | 安装、升级、卸载由系统包管理器接管 |

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

plugins/
  secret.py         ← argparse、命令 handler 与 SecretStore 调用

tests/
  test_paths.py     ← 路径解析（跨平台 mock）
  test_secrets.py   ← SecretStore 单元测试
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

*本文档是活文档，随架构演进更新。当前实际状态时间：2026-07-17。*
