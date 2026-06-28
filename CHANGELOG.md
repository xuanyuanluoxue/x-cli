# Changelog

本文档记录 x-cli 项目的版本历史。

格式基于 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [Semantic Versioning](https://semver.org/)。

---

## [Unreleased]

### Added
- **`x todo tag` 命令**（COMMANDS.md ⏳ P1 第 2 项）：单独管理 tags（不重写整个任务）
  - `x todo tag <id> <tag>...`  添加 tag（幂等：已存在则跳过）
  - `x todo tag --remove <id> <tag>...`  移除 tag（幂等：不存在的 tag 报 0 移除）
  - `x todo tag --clear <id>`  清空 tags（删除 frontmatter 字段，不写 `tags: []`）
  - 单 tag 用名字（"已添加 tag 'X'"），0/多 用数字（"已添加 3 个 tags"）
  - 退出码：0 成功 / 2 参数错 / 3 不存在 / 4 已归档
  - 复用 `TaskStore.update_task` 写入路径，未知字段（description / paused_at 等）自动保留
  - BDD：`docs/behaviors/todo-tag-behavior.md`（17 场景）
  - Tests：14 个单元测试 + 8 个 E2E 子进程测试
- **PyInstaller 打包脚本** `release/build.py`（AGENTS.md §8 标"待决策"的实装）
  - 包装 PyInstaller，输出到 `<xcli_data_dir>/bin/x{.exe}`（不污染仓库）
  - 接受 `--clean`（清缓存）和 `--platform {win,mac,linux,current}`（target 提示，不支持交叉编译）
  - 自检：找 pyinstaller + 检查 x.py 入口 + 友好中文错误
  - 文档：`docs/release.md`（6 节，含跨平台 + 故障排查 7 项 + 替代方案）
- **3 份新文档**（AGENTS.md §0 "未创建" 收口）：
  - `docs/testing.md` — 597 用例 / 20 文件 / 3 层测试（单测 / BDD / e2e）总览
  - `docs/plugin-dev.md` — 插件契约 + 6 步 checklist + 3 个真实插件演进案例
  - `docs/release.md` — PyInstaller 打包（见上）

### Changed
- 无

### Deprecated
- 无

### Removed
- 无

### Fixed
- **`x web` 子命令注册 bug**（v0.6.0 收口）：`plugins/web.py` 自 v0.6.0 在位（HTTP server + REST API + token auth），但 `x.py:SUBCOMMAND_HANDLERS` 字典没注册 `"web"` 条目，导致命令行 `x web` 报"未知子命令"。本 PR 修这个：
  - `x.py:24` 区域加 `from plugins import web as _web_plugin`
  - `x.py:38` SUBCOMMAND_HANDLERS 字典加 `"web": _web_plugin.run`
  - `tests/test_x.py` 加 3 个 test 固定该契约（注册 + 出现在帮助 + 未知子命令回归）
  - 已知问题来源：`docs/prompts/web-frontend-handoff.md` "不在你修复范围内" 标记

---

## [0.6.0] - 2026-06-27 — secret --category + todo auto-archive

### Added
- **`x secret` 分组增强**：`x secret list --category <c>` 按 category 过滤（大小写不敏感）；`x secret update <name> --category <c>` 修改分组（与 `--value` / `--note` 互不冲突，至少传一个）
  - 实现：`core/secrets.py:SecretStore.list(category=...)`；`plugins/secret.py` 暴露 CLI 参数
  - BDD：新增场景 §1.5 / §1.6 / §8.5 / §8.6 `docs/behaviors/secret-behavior.md`
  - 测试：新增 7 个单元测试 + 4 个 E2E 子进程测试
  - 向后兼容：`--category` 不传 = 不过滤（之前所有调用不变）
- **`x todo` 自动归档（opt-in）**：查询类命令（`list` / `stats` / `search`）进入时检查并归档 `deadline < today()` 且状态为 active 的任务，归档 `reason=expired`，stdout 顶部打摘要行 `⏰ 自动归档 N 个逾期任务：id1 / id2`。**默认关闭**——不破坏现有用户
  - **启用方式 A**：配置文件 `<xcli_data_dir>/config.yaml` 加嵌套 `todo.auto_archive: true`
  - **启用方式 B**：环境变量 `XCLI_TODO_AUTO_ARCHIVE=1`（优先级最高，OR 关系）
  - **逾期判定**：`deadline < today()`（严格小于）+ status ∈ {pending, in_progress, blocked, waiting} + 未归档；`deadline == today` 不算逾期
  - **触发命令**：`x todo list` / `x todo stats` / `x todo search`（handler 第一步检查）；`add` / `update` / `archive` 等写命令**不**触发
  - **search leak 防护**：auto-archive 触发 search 时，强制 `include_archived=False`（除非用户显式 `--archived-only`），刚归档的逾期任务**不会**出现在结果表里
  - **副作用收敛**：单个 task 归档失败（race / broken file）不影响后续 task；fall-through 到下一个 overdue
  - 实现：`core/config.py:is_auto_archive_enabled()` + `core/storage.py:TaskStore.find_overdue_tasks()` + `plugins/todo.py:_auto_archive_overdue()` + `_render_auto_archive_summary()`
  - BDD：新增 6 场景 `docs/behaviors/todo-auto-archive-behavior.md`
  - Tests：新增 8 用例 `tests/test_todo_auto_archive.py`
- **`AGENTS.md §4.4` Git 分支策略**：每个功能在 `feature/<name>` 分支开发、测试通过后 `--no-ff` 合并到 dev；为后续多人团队开发铺路

### Changed
- 无

### Deprecated
- 无

### Removed
- 无

### Fixed
- **`x secret get` 多行 value 剪贴板提取**：当存储的 value 包含 `api_key:` / `token:` / `app_secret:` / `gateway_token:` 行时，剪贴板只取第一个匹配行的值（**不是**整块多行文本），方便直接粘贴到 API 工具。stdout 仍给完整多行 value（管道 / `--no-clipboard` 用户看到全部），stderr 加"（已提取 api_key 行）"提示。修复用户报告的 `x secret get 小米` 粘贴出 5 行乱文本的 bug
  - 实现：`plugins/secret.py:_extract_first_key()` + `_KEY_LINE_RE`
  - BDD：新增场景 §2.5 `docs/behaviors/secret-behavior.md`
  - 测试：新增 `test_e2e_get_extracts_api_key_from_multiline_value` + 11/11 regex unit checks
- **修复 12 个 date-sensitive flaky test**：3 个 `test_todo_update.py` 测试（`test_update_status_changes_only_status` / `test_update_multi_fields_replaces_tags_and_others` / `test_update_clear_deadline_via_empty_string`）硬编码 `updated = "2026-06-21"`，9 个 `test_todo_auto_archive.py` 测试硬编码 archive 文件夹名 `"20260626-*"`。全部改为 `date.today().isoformat()` / `_TODAY_YMD`，未来不会再因日期漂移 fail

---

## [0.5.0] - 2026-06-21 — Phase 4 plugin split + open-source-prep

### Added
- **`core/formatting.py`**（55 行）：共享的 CJK-aware display helpers（`display_width()` + `pad()`），替代原本散落在 `x.py` 的 `_display_width` / `_pad`
- **`plugins/todo.py`**（1221 行）：`x todo` 子命令族的 10 个 handler + `register()` + `run()`，从 `x.py` 迁出
- **`plugins/secret.py`**（434 行）：`x secret` 子命令族的 8 个 handler + `register()` + `run()`，从 `x.py` 迁出
- **`plugins/__init__.py`**：package docstring + plugin contract 说明（`register` + `run` 约定）
- **`docs/TODO-SPEC.md`**：项目内嵌的 TODO 磁盘格式规范（YAML frontmatter schema / 字段规则 / 状态枚举 / 迁移说明），替换原本指向 `~/.xavier/TODO/00-TODO-SPEC.md` 的外链
- **`LICENSE`**：MIT License（Copyright © 2026 Xavier）
- **`README.md`**（重写）：公开面向的 README（install / usage / hard invariants / roadmap / license），替换 v0.2.0 时代版本
- **`README.zh.md`**（新增）：README 的中文完整翻译

### Changed
- **`x.py`**：1739 行 → 215 行（entry point only，subcommand 分发通过 `SUBCOMMAND_HANDLERS` 字典）
  - 加新子命令 = 1 个 `plugins/<name>.py` 文件 + `SUBCOMMAND_HANDLERS` 1 行字典条目
- **`core/paths.py`**：环境变量 `XAVIER_TODO_DIR` 改名为 `XCLI_TODO_DIR`（主名），`XAVIER_TODO_DIR` 保留为 deprecated alias 并触发 one-time stderr warning
- **`core/storage.py`**：`_default_todo_dir()` 简化为直接调用 `xcli_todo_dir()`（环境变量解析集中在 `core/paths.py`）
- **`x.py` 模板文本**：`x todo init` 创建的 README 模板从中文改为英文，避免在公开分享的代码里留个人化表述
- **14 个 BDD 文档**：路径占位符（`<xcli_todo_dir>/`、`<legacy-credentials-dir>/`、`xcli_data_dir`），env var 引用统一为 `XCLI_TODO_DIR`，spec 链接从 `~/.xavier/TODO/00-TODO-SPEC.md` 改为 `../TODO-SPEC.md`
- **12 个测试文件**：env var 从 `XAVIER_TODO_DIR` 改为 `XCLI_TODO_DIR`（兼容旧 alias，外部脚本不受影响）
- **`docs/architecture.md` / `docs/commands.md` / `AGENTS.md` / `COMMANDS.md`**：清理所有 `Xavier` / `xavier 系统` / `陈新捷` 引用，中性化为 `legacy TODO system` / `<legacy-config-dir>` 等

### Deprecated
- **`XAVIER_TODO_DIR` 环境变量**：保留为向后兼容（仍可读），但会触发一次性 stderr warning 指向新名 `XCLI_TODO_DIR`。计划 v0.6.0 移除

### Tests
- 526 PASS / 0 FAIL / 7 SKIP（与重构前完全一致；7 个 skip 全是平台条件 / 真用户样本 / stub 参数化）
- 19 个 test 文件**零修改**：`x.py` 通过 re-export 保持所有旧名（`_todo_list`、`_todo_register`、`_STATUS_ICONS` 等）

### Commits
- `92f9c46` — refactor(x): Phase 4 plugin split
- `7f6898a` — docs(AGENTS): mark Phase 4 plugin split as done
- `d822778` — docs+chore(x): open-source-prep (XCLI_TODO_DIR + neutralisation)
- `2d2816f` — docs(COMMANDS): flat-table rewrite
- `e8abe1b` + `deef0fd` — v0.4.y --config / --log-level / --config-init
- `a6978c8` — v0.4.0 x todo independent storage
- `265de76` + `e4b6813` — v0.4.x x todo restore/search/done
- `cb31ca5` + `f56834f` — v0.3.0 x secret clipboard + import
- `ec3eead` — v0.3.0 x secret initial

---

## [0.3.0] - 2026-06-21 — x secret 子系统完成

### Added
- **`x secret` 子命令族**（独立 JSON DB，8 个子命令：list/get/set/update/rm/search/import/export）：独立于 `<legacy-credentials-dir>/`，自管数据
  - 存储：`%LOCALAPPDATA%\x-cli\secrets.json`（Windows）/ `~/.local/share/x-cli/secrets.json`（Unix），文件权限 600
  - 覆盖：环境变量 `XCLI_SECRETS_DIR`
  - BDD 规格：[docs/behaviors/secret-behavior.md](docs/behaviors/secret-behavior.md)（17 场景）
- **`core/paths.py`**：跨平台路径解析（Windows 用 LOCALAPPDATA，Unix 用 XDG_DATA_HOME）
- **`core/secrets.py`**：`SecretStore` 类（CRUD + search + import + export，stdlib-only JSON）
- **`tests/test_paths.py`** + **`tests/test_secrets.py`**：49 单元测试（47 pass + 2 Windows-only chmod skip）
- **`tests/test_e2e_secret.py`**：19 E2E 子进程测试（覆盖 17 BDD 场景 + 2 个硬性约束）

### Changed
- 测试套件从 262 / 92% 覆盖 → 336 / 93% 覆盖（含 74 个 secret 相关测试）
- `x.py` 从 822 → 1166 行（+344 净增，inline MVP，Phase 4 拆插件时再迁出）

### Security
- **`x secret list` 永不显示 value**（硬性约束）
- **`x secret get` 永远 stderr 警告**（提醒密钥已离开数据库）
- **`x secret search` 不搜 value**（避免 grep 撞到密钥）
- JSON DB 文件权限 600（Windows 用 ACL）

### Files
- 新增：`core/paths.py` / `core/secrets.py` / `tests/test_paths.py` / `tests/test_secrets.py` / `tests/test_e2e_secret.py`
- 修改：`x.py`（+8 `_secret_*` handler + dispatcher）/ `README.md` / `AGENTS.md` / `docs/architecture.md` / `COMMANDS.md`

---

## [0.2.0] - 2026-06-21 — MVP 完成

### Added
- **E2E 子进程测试**（`tests/test_e2e_todo.py`，22 用例）：用 `subprocess.run` 真正启动 `x.exe`，覆盖 `pyproject.toml` 脚本入口 + `XCLI_TODO_DIR` 环境变量路由
- **E2E 行为规格**（`docs/behaviors/e2e-cli-behavior.md`，21 场景）：从 PowerShell 真实调用视角描述所有 todo action
- **venv 强制要求**：README/AGENTS.md 文档化 venv 是必须（系统 Python 3.14.2 被 `hydra-core` 拉入的 `antlr4` 污染）
- **CJK 对齐 + 状态/优先级图标**：`x todo list` 和 `x todo stats` 现在用 `_display_width` / `_pad` CJK 感知的列宽，附 `⏳`/`▶`/`⏸`/`⌛`/`✅`/`🚫`/`⏰`/`❌` 状态图标和 `🔥`/`⚡`/`🐢` 优先级图标
- **表格分隔线**：列表表头下面用 `───` 增强可视化

### Changed
- 测试套件从 240 / 91% 覆盖 → 262 / 92% 覆盖
- README 快速开始改为 venv + pip install -e 工作流
- `x secret` 使用独立存储（`%LOCALAPPDATA%\x-cli\secrets.json`），不与 legacy TODO system密钥库耦合

---

## [0.2.0] - 2026-06-21 — MVP 完成

**Phase 1 落地**：`x todo` 5 个 action 全部实现，core 库手写 stdlib-only，240+ tests pass。

### Added
- **主入口**（`x.py`，731 行）：
  - `--version` / `--help` 全局选项
  - `SUBCOMMAND_HANDLERS` 字典分发（未启用 importlib 动态加载）
  - 5 个 x todo action（inline 实现）：
    - `x todo list` — 列出任务（支持 --status/--priority/--tag/--all 过滤）
    - `x todo add` — 添加任务（slugify 自动生成 ID，碰撞自动加 -2/-3）
    - `x todo update` — 更新任务（status/priority/deadline/tags，未知字段保留）
    - `x todo archive` — 归档任务（4 种 reason：done/cancelled/expired/failed）
    - `x todo stats` — 统计信息（含 broken 文件检测）
- **核心库**（`core/`，零第三方依赖）：
  - `core/models.py` — Task dataclass + 3 个 enum（TaskStatus/Priority/ArchiveReason）
  - `core/parser.py` — YAML frontmatter 解析/序列化（手写，**不引 PyYAML**）
  - `core/slug.py` — 中英文 slug 生成（**不引 pypinyin**；50+ 硬编码拼音 + `unicodedata`）
  - `core/storage.py` — TaskStore：CRUD + 统计 + TODO.md 索引维护
- **BDD 行为规格**（`docs/behaviors/`，39 场景）：
  - `todo-add-behavior.md`（8 场景）
  - `todo-list-behavior.md`（8 场景）
  - `todo-update-behavior.md`（8 场景）
  - `todo-archive-behavior.md`（8 场景）
  - `todo-stats-behavior.md`（7 场景）
- **测试**（`tests/`，9 个文件，240+ 用例，覆盖率 91%）：
  - `test_models.py` / `test_parser.py` / `test_storage.py`（核心库）
  - `test_x.py`（主入口分发）
  - `test_todo_add.py` / `test_todo_list.py` / `test_todo_update.py` / `test_todo_archive.py` / `test_todo_stats.py`（CLI 集成）
- **环境变量**：`XCLI_TODO_DIR` 覆盖 TODO 根目录（测试用）
- **退出码约定**：0/1/2/3/4/5 体系（详见 `docs/commands.md §5`）
- **占位包**：`plugins/__init__.py`（Phase 4 拆插件用）

### Compatibility / 兼容性
- ✅ 与现有 `<xcli_todo_dir>/` 数据 **byte-identical round-trip**（SHA-256 验证）
- ✅ 未知 frontmatter 字段（如 `paused_at` / `description` / `pause_reason` / `subtasks`）原样保留
- ✅ 与 `regen-index.ps1` 不冲突（`x todo archive/stats` 自动维护 TODO.md 总索引）

### Documented but not implemented（已规划但未实现）
- `x --config` / `--log-level` 全局选项
- `x todo init`（初始化 TODO 目录）
- `x todo restore`（从归档还原）
- `x skill` / `x system` 插件
- `<xcli_config_path>` 配置加载
- `<xcli_data_dir>/x.log` 日志系统
- PyInstaller 打包（`x.exe` ~10MB）
- importlib 动态加载插件
- Tab 补全（argcomplete）

### Test Metrics
- 240+ tests pass / 0 failed / 1 skipped
- 覆盖率 91%（`core/` 95%+，`x.py` 90%+）

---

## [0.1.0] - 2026-06-21 — 项目骨架

### Added
- 项目启动（替代 `x-cli (project)`）
- 定义统一入口 `x`（x-cli 总控）
- 定义技术栈（Python + argparse + stdlib-only）
- 项目目录结构定义
- AGENTS.md / README.md / docs/architecture.md / docs/commands.md 模板
- .gitignore（Python + IDE + OS + Mavis plan 状态）
- pyproject.toml（setuptools + pytest 配置，**`dependencies = []`**）

### Notes
- 0.1.0 是「项目骨架」版本，**没有可执行的 x todo 命令**（只有占位）

---

[Unreleased]: https://github.com/x-cli/x-cli/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/x-cli/x-cli/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/x-cli/x-cli/compare/v0.2.0...v0.5.0
[0.2.0]: https://github.com/x-cli/x-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/x-cli/x-cli/releases/tag/v0.1.0
