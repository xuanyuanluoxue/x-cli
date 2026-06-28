# Backend Polish 设计文档

**日期**：2026-06-28
**分支**：`feature/backend-polish`（基于 `dev`，领先 origin 7 commit）
**作者**：x-cli 后端 agent（solo）
**状态**：✅ 用户已确认

---

## 0. 背景

`dev` 分支当前 v0.6.0，含 5 个子系统（todo / secret / config / logging / web）。**v0.6.0 收尾有 4 件事未做**：

1. **x web 插件没注册** — `plugins/web.py` 已写完（HTTP server + REST API + token auth），但 `x.py:SUBCOMMAND_HANDLERS` 字典没加 `"web"` 条目，命令行 `x web` 报"未知子命令"
2. **P1 命令 `x todo tag` 未实现** — COMMANDS.md ⏳ P1 第 2 项
3. **3 份文档未创建** — AGENTS.md §0 列出的 `docs/release.md` / `docs/testing.md` / `docs/plugin-dev.md`
4. **PyInstaller 打包未实装** — AGENTS.md §8 标"待决策"

**为什么现在做**：dev 上 7 commit 涉及前端 merge 收尾、importlib 插件发现（feature/importlib-plugin-discovery 仍 open）、PyInstaller 未实现。这些**不冲突**于本设计，本设计专注于"**后端 polish 收尾**"。

---

## 1. 目标 & 非目标

### 1.1 目标

- ✅ **解锁 x web**：命令行 `x web` 可启动 HTTP server
- ✅ **实现 x todo tag**：COMMANDS.md P1 命令，完整 BDD+TDD
- ✅ **文档收口**：3 份文档写完，AGENTS.md §0 不再有"未创建"
- ✅ **PyInstaller 收口**：`release/build.py` 跨平台脚本 + `release/README.md`（`docs/release.md`）

### 1.2 非目标

- ❌ 不改 `plugins/web.py` 内部实现（handoff 文档明确"不在你修复范围内"）
- ❌ 不实现 COMMANDS.md P2/P3（log rotation / skill / agent / system）
- ❌ 不重写 plugin 加载机制（feature/importlib-plugin-discovery 是别人分支）
- ❌ 不改 storage YAML 格式兼容性
- ❌ 不引第三方依赖

---

## 2. 任务分解

### 2.1 任务 A：修 x web 注册 bug

**优先级**：P0（解锁整个 web 子系统）

**改动**：
- `x.py:30-40` 区域加 `import plugins.web as _web_plugin`
- `x.py:37-40` `SUBCOMMAND_HANDLERS` 加 `"web": _web_plugin.run`
- `tests/test_x.py` 加 2 个 test：
  - `test_web_subcommand_registered` — 断言 `SUBCOMMAND_HANDLERS` 含 `"web"`
  - `test_web_help_lists_web` — 断言 `x` 帮助里出现 `"web"`

**测试策略**：
- **不**用 subprocess 测 `x web start`（会真启动 HTTP server，e2e 难）
- 只测"注册" + "出现在帮助"两个最小契约

**风险**：
- 极低（1 行 + 1 import）

### 2.2 任务 B：x todo tag 命令

**优先级**：P1（COMMANDS.md ⏳ P1 第 2 项）

**子命令设计**：
```
x todo tag <id> <tag> [<tag> ...]          # 添加 tag（已存在则幂等）
x todo tag --remove <id> <tag> [<tag> ...] # 移除 tag
x todo tag --clear <id>                    # 清空所有 tag
```

**退出码**：
- 0 = 成功
- 2 = 参数错（缺 id / 缺 tag / 同时指定 --remove 和 --clear）
- 3 = 任务不存在
- 4 = 任务已归档

**开发流程（AGENTS.md §5 BDD+TDD 强制）**：
1. `docs/behaviors/todo-tag-behavior.md` — 8+ 场景
2. `tests/test_todo_tag.py` — Red
3. `plugins/todo.py` 加 `_todo_tag` handler + `TODO_ACTIONS` 注册 — Green
4. `tests/test_e2e_todo.py` 加 e2e
5. 重构（如果需要）

**风险**：
- 中（动 storage，但只动 `update_task` 路径的 tags 字段，不动 YAML 格式）

### 2.3 任务 C：docs/testing.md

**优先级**：P1（AGENTS.md §0 标"未创建"）

**内容大纲（4 节）**：
1. **测试分层** — 单测 / BDD 行为 / e2e 子进程（3 层次 + 各层定位）
2. **597 用例分布** — 按文件统计（test_models / test_parser / test_storage / test_x / test_todo_* / test_secret_* / test_e2e_* / test_config / test_logging / test_paths）
3. **运行命令** — `pytest` / `pytest --cov` / `pytest -k xxx` / 跨平台坑
4. **e2e 模式** — subprocess 启动 `x.exe` 的 fixture 模板

**风险**：低（docs only）

### 2.4 任务 D：docs/plugin-dev.md

**优先级**：P1（AGENTS.md §0 标"未创建"）

**内容大纲（3 节）**：
1. **插件 contract** — `register(parser)` + `run(args) -> int` 约定
2. **加新插件 checklist** — 6 步骤：建文件 → 写 BDD → 写测试 → 写实现 → 注册 SUBCOMMAND_HANDLERS → e2e
3. **真实案例** — todo / secret / web 三个插件的演进（从 inline 到 plugins/，从 0 到 1 插件的全过程）

**风险**：低（docs only）

### 2.5 任务 E：PyInstaller 打包（docs/release.md + release/build.py）

**优先级**：P2（AGENTS.md §8 标"待决策"，v0.7.0 收口）

**内容**：
- `docs/release.md`：
  - 目标产物（`x.exe` for Windows / `x` for macOS / `x` for Linux）
  - 跨平台约束（PyInstaller 在不同 OS 的差异）
  - `release/build.py` 用法
  - 故障排查（anti-virus / missing module / 启动慢）
- `release/build.py`：
  - `--platform {win,mac,linux}` 选择（默认当前 OS）
  - `--clean` 清 build cache
  - `--onefile` PyInstaller --onefile 模式
  - 输出 `<xcli_data_dir>/bin/x{.exe}`
  - 不签名 / 不打 DMG / 不做 MSI（个人用，没必要）

**风险**：中（PyInstaller 跨平台坑多，但脚本本身只是包装 + 文档）

---

## 3. 执行顺序

| Step | 任务 | commit 粒度 | 依赖 |
|---|---|---|---|
| 1 | A: 修 x web 注册 | 1 commit | 无 |
| 2 | B-1: docs/behaviors/todo-tag-behavior.md | 1 commit | 无 |
| 3 | B-2: tests/test_todo_tag.py（Red）| 1 commit | B-1 |
| 4 | B-3: plugins/todo.py 实现 | 1 commit | B-2 |
| 5 | B-4: tests/test_e2e_todo.py 加 e2e | 1 commit | B-3 |
| 6 | C: docs/testing.md | 1 commit | 无 |
| 7 | D: docs/plugin-dev.md | 1 commit | C（参考 testing.md 风格）|
| 8 | E-1: release/build.py 脚本 | 1 commit | 无 |
| 9 | E-2: docs/release.md | 1 commit | E-1 |
| 10 | CHANGELOG 更新 | 1 commit | 全部 |

**总 commit 数**：10

---

## 4. 测试策略

- 每个 step 完成后跑 `pytest --tb=short -q` 确认全绿
- B 任务完整 BDD + TDD（AGENTS.md §5 强制）
- A 任务只加 2 个 test 断言注册契约
- C/D/E 任务无新代码测试需求

---

## 5. 风险 & 缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| dev 上 7 commit 跟我的分支冲突 | 中 | 不动 dev；feature/backend-polish 推前 fetch + rebase 一次 |
| feature/importlib-plugin-discovery 跟我冲突 | 低 | 不动 plugin 加载机制（我加 1 行 SUBCOMMAND_HANDLERS 条目即可）|
| Windows pytest PermissionError | 低 | 不修（项目级问题），用 `--no-cleanup` 或忽略 |
| PyInstaller 跨平台 | 中 | build.py 提供 platform flag，docs 明确说"建议在目标 OS 上构建" |
| x todo tag 破坏 storage YAML 兼容性 | 低 | 只动 tags 字段（List[str]），不新增字段，不动格式 |

---

## 6. 不在本设计范围内

- ❌ 修复 Windows pytest PermissionError（项目级问题，不在本分支范围）
- ❌ 实现 COMMANDS.md P2/P3（user not prioritized）
- ❌ 重构 SUBCOMMAND_HANDLERS 为 importlib 动态加载（feature/importlib-plugin-discovery 在做）
- ❌ 更新 AGENTS.md 到 v0.6.0 真实状态（信息差，不在本任务范围；用户没要求）

---

*Last updated: 2026-06-28*
