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

## ✅ 已实现（v0.4.y — 2026-06-21）

| 命令 | 用途 | 关键参数 |
|------|------|----------|
| `x --version` (`-v`) | 显示版本号 | — |
| `x --help` (`-h`) | 显示帮助 | — |
| `x --config <path>` | 加载 YAML 配置 | 覆盖默认 todo_dir / secrets_path / log_level / log_path |
| `x --log-level <level>` | 全局日志级别 | DEBUG / INFO / WARNING / ERROR / CRITICAL（大小写不敏感，WARN/FATAL 别名） |
| `x --config-init` | 写默认配置到 `xcli_data_dir()/config.yaml` | 不覆盖（除非未来 `--force`） |
| `x todo list` | 列出任务（CJK 对齐 + 状态/优先级图标）| `--status` `--priority` `--tag` `--all` |
| `x todo add <name>` | 添加任务 | `--priority` `--deadline` `--tags` |
| `x todo update <id>` | 更新任务字段 | `--status` `--priority` `--deadline` `--tags` |
| `x todo archive <id>` | 归档任务 | `--reason` (done/cancelled/expired/failed) |
| `x todo restore <id>` | 归档→active 还原 | `--status`（强制覆盖）/ `--dry-run` |
| `x todo search <keyword>` | 跨字段模糊搜索（name + note + tags）| `--active-only` / `--archived-only` / `--status` |
| `x todo done <id>` | `archive --reason done` 的快捷 | — |
| `x todo stats` | 统计信息（带图标）| — |
| `x todo init [--dir <path>]` | 创建独立 TODO 目录（幂等）| — |
| `x todo import --from <dir>` | 从 xavier 系统单向迁移到 x-cli 库 | `--to <path>` `--dry-run` |
| `x secret list` | 列出所有密钥（**不显示 value**）| — |
| `x secret get <name>` | 输出 value（默认复制到剪贴板 + 输出 stdout）| `--full` / `--no-clipboard` / `--no-stdout` |
| `x secret set <name>` | 新增条目 | `--value`（必填）/ `--category` / `--note` |
| `x secret update <name>` | 改 value / note | `--value` / `--note` |
| `x secret rm <name>` | 删除条目 | — |
| `x secret search <keyword>` | name/note 模糊搜（**不搜 value**）| — |
| `x secret import --from <dir>` | 从 .md 批量迁移（旧文件保留）| — |
| `x secret export` | JSON 备份 | `--to <path>` |

**合计 21 个命令**（3 顶层 + 10 todo + 8 secret）+ 3 全局 flag

**存储（全部独立于 xavier 系统）**：

| 子系统 | 路径（Windows） | 路径（Unix） |
|---|---|---|
| TODO | `%LOCALAPPDATA%\x-cli\todo\` | `~/.local/share/x-cli/todo/` |
| Secret | `%LOCALAPPDATA%\x-cli\secrets.json` | `~/.local/share/x-cli/secrets.json` |
| Config | `%LOCALAPPDATA%\x-cli\config.yaml` | `~/.local/share/x-cli/config.yaml` |
| Log | `%LOCALAPPDATA%\x-cli\x.log` | `~/.local/share/x-cli/x.log` |

**环境变量覆盖**（向后兼容）：
- `XAVIER_TODO_DIR` / `XCLI_SECRETS_DIR` 仍 work（测试 / 用户覆盖）
- `XCLI_CONFIG` 覆盖配置文件路径
- 配置文件里的 `todo_dir` / `secrets_path` 优先级**高于**上面 2 个 env var

**调用方式**：PowerShell 直接 `x todo list`（PATH 已配 `C:\Users\Chatxavier\.local\bin\x.bat` wrapper）

---

## ⏳ 我想要的（按优先级排序）

### P1 — 立即做

- [ ] `x todo edit <id>` — 交互式编辑器打开 TODO.md（vim / notepad / 记事本）
- [ ] `x todo tag <id> <标签...>` — 单独管理 tags（不重写整个任务）
- [ ] `x --config --force` — `--config-init` 加 force flag（覆盖已存在配置）
- [ ] 日志轮转 — 按日期 / 按大小（v0.4.x 单文件 append 不够用）

### P2 — 以后做（常用快捷 / 增强）

- [ ] `x --log-level <level>` 在子命令里覆盖（现在是全局）
- [ ] Config validation（typo 检测 for unknown keys）
- [ ] Config 热重载（运行中修改不生效，需重启）
- [ ] `--help` 解析修复（现在被顶层 parser 截走，没传给子命令）
- [ ] x secret update 加 `--category` 支持（现在只能 rm + set）

### P3 — 远期（其他插件）

- [ ] `x skill list / install / remove / update` — 技能管理（150+ skills 散在 4 个目录）
- [ ] `x agent list / start / stop / logs` — agent 编排（hermes / marvis / brain-science 等）
- [ ] `x web start / stop / status` — 本地 web server 管理
- [ ] `x system backup / health / log` — 系统工具

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
- 退出码约定：0 成功 / 1 未知子命令 / 2 参数错 / 3 不存在 / 4 已归档/已存在 / 5 数据完整性
- 输出格式：成功有 emoji 前缀（✅ ❌ ⏳），表格列 CJK 对齐
- 配置/存储/日志文件用 stdlib（不引第三方），所有数据**独立于 xavier 系统**
- 跨平台路径用 `core/paths.py:xcli_data_dir()` 统一解析

---

## 📋 Commit history

| Commit | 版本 | 主题 |
|---|---|---|
| `deef0fd` | v0.4.y | docs: COMMANDS.md flip — --config / --log-level / --config-init ✅ |
| `e8abe1b` | v0.4.y | feat: --config / --log-level / --config-init global options |
| `e4b6813` | v0.4.x | feat: restore / search / done（todo 生命周期闭环 + 2 快捷）|
| `a6978c8` | v0.4.0 | feat: x todo 独立存储 + init + import |
| `0f73333` | v0.4.0 | docs: BDD specs (storage / init / import) |
| `44d0670` | v0.4.y | docs: BDD spec (config + log-level) |
| `265de76` | v0.4.x | docs: BDD specs (restore / search / done) |
| `f56834f` | v0.3.0 | fix(secret): preserve full text block content |
| `cb31ca5` | v0.3.0 | feat(secret): strip key prefix + clipboard + skip README |
| `ec3eead` | v0.3.0 | feat: CJK alignment + x secret subsystem |
| `eab6dac` | v0.2.0 | feat(x.py): 5 个 todo action + stats bug + slug stdlib |
| `f952549` | v0.2.0 | feat(core): parser + models + storage |
| `c1fa8e5` | v0.2.0 | docs(behaviors): 5 个 todo BDD 规格 |
| `ce36312` | v0.1.0 | chore: 项目骨架 |

---

*最后更新：2026-06-21（v0.4.y 落地后重写 — 扁平"已实现"表 + commit history）*
