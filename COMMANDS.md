# x 命令清单

> **专用文档** — 我（用户）编辑这里，AI agent 根据这里实现 / 写测试 / 写文档。
>
> **怎么用**：
> - ✅ = 已实现，AI 不用动
> - 🚧 = 正在开发，AI 可以继续
> - ⏳ = 我想要的，AI 等指令实现
> - ❌ = 明确不要，AI 看到就知道别做
>
> **AI 的工作流**：每次接到任务前先读本文件 → 看 ⏳ 列表 → 问我优先级 → 按 BDD+TDD 实现。

---

## ✅ 已实现（v0.3.0 — 2026-06-21）

| 命令 | 用途 | 关键参数 |
|------|------|----------|
| `x --version` | 显示版本号 | — |
| `x --help` | 显示帮助 | — |
| `x todo` | 显示 todo 子命令帮助 | — |
| `x todo list` | 列出任务（CJK 对齐 + 状态/优先级图标） | `--status` `--priority` `--tag` `--all` |
| `x todo add <名称>` | 添加任务 | `--priority` `--deadline` `--tags` |
| `x todo update <id>` | 更新任务字段 | `--status` `--priority` `--deadline` `--tags` |
| `x todo archive <id>` | 归档任务 | `--reason` (done/cancelled/expired/failed) |
| `x todo stats` | 统计信息（带图标） | — |
| `x secret list` | 列出所有密钥（**不显示 value**）| — |
| `x secret get <name>` | 输出 value 到 stdout（带警告）| `--full` |
| `x secret set <name>` | 新增条目 | `--value` `--category` `--note` |
| `x secret update <name>` | 改 value / note | `--value` `--note` |
| `x secret rm <name>` | 删除条目 | — |
| `x secret search <keyword>` | name/note 模糊搜（不搜 value）| — |
| `x secret import --from <dir>` | 从 .md 批量迁移（旧文件保留）| — |
| `x secret export` | JSON 备份 | `--to <path>` |

**数据源**：`~/.xavier/TODO/任务/` + `~/.xavier/TODO/归档/`

**调用方式**：PowerShell 直接 `x todo list`（PATH 已配 `.venv\Scripts`）

---

## ⏳ 我想要的（按优先级排序）

### P0 — 立即做

- [x] `x secret list` — 列出所有密钥（id / name / category / updated_at，**不显示值**）
- [x] `x secret get <name>` — 输出 value 到 stdout（带"密钥外泄"警告）
- [x] `x secret set <name> --value <v> [--category <c>] [--note <n>]` — 插入新条目
- [x] `x secret update <name> --value <v> [--note <n>]` — 改 value
- [x] `x secret rm <name>` — 删除条目
- [x] `x secret search <keyword>` — name/note 模糊匹配
- [x] `x secret import --from <dir>` — 从 `~/.xavier/密钥/*.md` 批量迁移（旧文件保留）
- [x] `x secret export` — JSON 备份

**存储（独立于 xavier 系统）**：
- Windows: `%LOCALAPPDATA%\x-cli\secrets.json`
- macOS/Linux: `~/.local/share/x-cli/secrets.json`
- 环境变量 `XCLI_SECRETS_DIR` 覆盖
- 文件权限 600
- MVP 不加密（明文 + 文件权限保护）
- Schema: `{name, category, value, note, created_at, updated_at}`

**迁移字段映射**：
| DB 字段 | 来源 |
|---------|------|
| `name` | `.md` 文件的 `## <section>` 标题 |
| `category` | 文件名（去 `.md`）|
| `value` | 整个 `text` 代码块原文 |
| `note` | section 上面的 metadata 表格 |

**退出码**：0 成功 / 2 参数错 / 3 不存在 / 4 已存在（set 时）/ 5 DB 错

---

### P0 — 立即做（✅ v0.4.0 — x todo 独立化 已完成）

- [x] **存储路径改独立** — `core/storage.py:_default_todo_dir()` 改用 `core/paths.py:xcli_todo_dir()`（默认 `%LOCALAPPDATA%\x-cli\todo\` Win / `~/.local/share/x-cli/todo/` Unix）
  - 不变量：`x todo` **永不**读写 `~/.xavier/TODO/`（除非显式 `--from`）
  - 向后兼容：`XAVIER_TODO_DIR` 环境变量仍可覆盖
  - BDD 规格：[docs/behaviors/todo-storage-behavior.md](docs/behaviors/todo-storage-behavior.md)
  - **已上线（commit `a6978c8`）**
- [x] `x todo init [--dir <path>]` — 一键创建 x-cli 独立 TODO 目录（任务/ + 归档/ + README.md）
  - 幂等：已存在则提示，不覆盖
  - 退出码：0 成功 / 1 无法创建（权限 / IO 错）/ 2 参数错
  - BDD 规格：[docs/behaviors/todo-init-behavior.md](docs/behaviors/todo-init-behavior.md)
  - **已上线（commit `a6978c8`）**
- [x] `x todo import --from <dir> [--to <dir>]` — 从 xavier 系统单向迁移任务到 x-cli 独立库
  - **不写回 xavier**（单向只读）
  - 重复跳过（同 name 已存在不覆盖）
  - Frontmatter 全字段 round-trip（含未知字段如 `paused_at`）
  - BDD 规格：[docs/behaviors/todo-import-behavior.md](docs/behaviors/todo-import-behavior.md)
  - **已上线（commit `a6978c8`）**

---

### P1 — 这周做（🚧 v0.4.x — todo 全生命周期闭环）

- [ ] `x todo restore <id>` — 从归档还原到 active
  - 行为：把 `归档/YYYYMMDD-<name>/` 移回 `任务/<name>/`，清掉 `status: archived` + `reason` 字段
  - 退出码：0 成功 / 3 任务不存在 / 4 任务没归档（不可 restore）/ 5 归档 YAML 解析失败
  - 边界：归档名带日期前缀，restore 时去掉；同名 active 任务已存在 → 退出码 3
  - 增强：保留最后已知 status（不只是 pending）；--status 强制覆盖；--dry-run 预览
  - BDD 规格：[docs/behaviors/todo-restore-behavior.md](docs/behaviors/todo-restore-behavior.md)

---

### P2 — 以后做（v0.4.x — 常用快捷）

- [ ] `x todo search <keyword>` — 跨字段模糊搜索（name + note + tags）
  - 大小写不敏感，子串匹配，默认含归档
  - 退出码：0 成功 / 2 空关键词
  - BDD 规格：[docs/behaviors/todo-search-behavior.md](docs/behaviors/todo-search-behavior.md)
- [ ] `x todo done <id>` — `archive --reason done` 的快捷方式（80% 常用 case）
  - 行为完全等价于 `x todo archive <id> --reason done`
  - 退出码：0 成功 / 3 不存在 / 4 已归档
  - BDD 规格：[docs/behaviors/todo-done-behavior.md](docs/behaviors/todo-done-behavior.md)

---

### P1 — 这周做（配置 / 环境）

- [ ] `x --config <路径>` — 加载 YAML 配置（路径 / 日志级别 / TODO 目录覆盖）
  - 配置文件 schema：`{todo_dir: ..., log_level: DEBUG/INFO/WARNING/ERROR}`
  - 环境变量 `XAVIER_CONFIG` 作为隐式默认值
- [ ] `x --log-level <级别>` — 全局日志级别（DEBUG / INFO / WARNING / ERROR）
  - 输出到 `~/.xavier/logs/x.log`（按日期滚动）

### P2 — 以后做（可选功能）

- [ ] `x todo edit <id>` — 交互式编辑器打开 TODO.md（vim / notepad）
- [ ] `x todo tag <id> <标签...>` — 单独管理 tags（不重写整个任务）

> **已完成（移到 P2 块上方 / 独立 BDD 规格）**：
> - `x todo search` → [docs/behaviors/todo-search-behavior.md](docs/behaviors/todo-search-behavior.md)
> - `x todo done` → [docs/behaviors/todo-done-behavior.md](docs/behaviors/todo-done-behavior.md)

### P3 — 远期（其他插件）

- [ ] `x skill list` — 列出已安装 skills
- [ ] `x skill install <name>` — 安装 skill
- [ ] `x system backup` — 备份 `~/.xavier/` 到本地 / 云端
- [ ] `x system health` — 系统健康检查

---

## 🚧 我正在做的（AI 看着办）

<!-- 我会在这里加：当前开发中的命令 + 进度 -->
<!-- 例：- [ ] x todo restore（开发中，今天完成 BDD 规格）-->

---

## ❌ 明确不要

<!-- 我会在这里加：明确不要实现的命令 / 功能 -->
<!-- 例：- 不做 TUI（rich 库）-->
<!-- - 不引 PyYAML（手写 parser）-->
<!-- - 不做子命令缩写（argcomplete 补全更直接）-->

---

## 📝 备注（给我自己看的）

<!-- 自由记录：开发心得、想法、约束 -->

- 命令名用 kebab-case：x todo list（不缩写）
- 退出码约定：0 成功 / 1 未知 / 2 参数错 / 3 不存在 / 4 已归档 / 5 数据完整性
- 输出格式：成功有 emoji 前缀（✅ ❌ ⏳），表格列 CJK 对齐
- 配置文件：`~/.xavier/config.yaml`（手写解析，不引 PyYAML）

---

*最后更新：2026-06-21（创建 + 列出 MVP 已实现 + Phase 2-4 待开发）*