# Changelog

本文档记录 x-cli 项目的版本历史。

格式基于 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [Semantic Versioning](https://semver.org/)。

---

## [Unreleased]

### Added
- 无

### Changed
- 无

### Deprecated
- 无

### Removed
- 无

### Fixed
- 无

---

## [0.3.0] - 2026-06-21 — x secret 子系统完成

### Added
- **`x secret` 子命令族**（独立 JSON DB，8 个子命令：list/get/set/update/rm/search/import/export）：独立于 `~/.xavier/密钥/`，自管数据
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
- **E2E 子进程测试**（`tests/test_e2e_todo.py`，22 用例）：用 `subprocess.run` 真正启动 `x.exe`，覆盖 `pyproject.toml` 脚本入口 + `XAVIER_TODO_DIR` 环境变量路由
- **E2E 行为规格**（`docs/behaviors/e2e-cli-behavior.md`，21 场景）：从 PowerShell 真实调用视角描述所有 todo action
- **venv 强制要求**：README/AGENTS.md 文档化 venv 是必须（系统 Python 3.14.2 被 `hydra-core` 拉入的 `antlr4` 污染）
- **CJK 对齐 + 状态/优先级图标**：`x todo list` 和 `x todo stats` 现在用 `_display_width` / `_pad` CJK 感知的列宽，附 `⏳`/`▶`/`⏸`/`⌛`/`✅`/`🚫`/`⏰`/`❌` 状态图标和 `🔥`/`⚡`/`🐢` 优先级图标
- **表格分隔线**：列表表头下面用 `───` 增强可视化

### Changed
- 测试套件从 240 / 91% 覆盖 → 262 / 92% 覆盖
- README 快速开始改为 venv + pip install -e 工作流
- `x secret` 使用独立存储（`%LOCALAPPDATA%\x-cli\secrets.json`），不与 xavier 系统密钥库耦合

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
- **环境变量**：`XAVIER_TODO_DIR` 覆盖 TODO 根目录（测试用）
- **退出码约定**：0/1/2/3/4/5 体系（详见 `docs/commands.md §5`）
- **占位包**：`plugins/__init__.py`（Phase 4 拆插件用）

### Compatibility / 兼容性
- ✅ 与现有 `~/.xavier/TODO/` 数据 **byte-identical round-trip**（SHA-256 验证）
- ✅ 未知 frontmatter 字段（如 `paused_at` / `description` / `pause_reason` / `subtasks`）原样保留
- ✅ 与 `regen-index.ps1` 不冲突（`x todo archive/stats` 自动维护 TODO.md 总索引）

### Documented but not implemented（已规划但未实现）
- `x --config` / `--log-level` 全局选项
- `x todo init`（初始化 TODO 目录）
- `x todo restore`（从归档还原）
- `x skill` / `x system` 插件
- `~/.xavier/config.yaml` 配置加载
- `~/.xavier/logs/x-cli.log` 日志系统
- PyInstaller 打包（`x.exe` ~10MB）
- importlib 动态加载插件
- Tab 补全（argcomplete）

### Test Metrics
- 240+ tests pass / 0 failed / 1 skipped
- 覆盖率 91%（`core/` 95%+，`x.py` 90%+）

---

## [0.1.0] - 2026-06-21 — 项目骨架

### Added
- 项目启动（替代 `xavier-todo`）
- 定义统一入口 `x`（Xavier CLI 总控）
- 定义技术栈（Python + argparse + stdlib-only）
- 项目目录结构定义
- AGENTS.md / README.md / docs/architecture.md / docs/commands.md 模板
- .gitignore（Python + IDE + OS + Mavis plan 状态）
- pyproject.toml（setuptools + pytest 配置，**`dependencies = []`**）

### Notes
- 0.1.0 是「项目骨架」版本，**没有可执行的 x todo 命令**（只有占位）

---

[Unreleased]: https://github.com/xavier/x-cli/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/xavier/x-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/xavier/x-cli/releases/tag/v0.1.0
