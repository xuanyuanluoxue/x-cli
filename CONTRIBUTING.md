# Contributing to x-cli

> **目标读者**：所有给 x-cli 提交代码的人 / AI agent
> **适用**：v0.6.0 起（多人直接协作模式）
> **AI 注意**：本规范通过 [AGENTS.md §4.4](AGENTS.md) 同步给 AI agent，强制遵守

---

## 1. 项目模式：多人直接 push（**不是 fork 模式**）

x-cli 用**多人直接 push 到 `dev`** 的模式（不是 GitHub fork / PR base `main` 的传统模式）。

| 分支 | 用途 | 直接 push？|
|---|---|---|
| `main` | 稳定发布分支 | ❌ **禁止** — 受保护，只通过 `dev` merge 进来 |
| `dev` | 活跃开发分支（**origin/HEAD**）| ⚠️ 慎用 — 优先用 feature 分支 + PR |
| `feature/<name>` | 个人功能分支 | ✅ 默认 |
| `fix/<name>` | 修复分支（类似 feature 但语义明确）| ✅ |
| `hotfix/<name>` | 紧急修复（main + dev 同步）| ✅ |
| `refactor/<name>` | 重构（无功能变化）| ✅ |
| `docs/<name>` | 纯文档分支 | ✅ |
| `release/<version>` | 发布准备（changelog / version bump）| ✅ |

**核心铁律**：

1. ❌ **禁止直接 push 到 `main`**（任何情况，包括 hotfix 也通过分支合）
2. ❌ **禁止 PR 的 base = `main`**（永远是 `dev`）
3. ✅ **所有 PR merge 目标 = `dev`**
4. ✅ **`main` 只通过 maintainer 的 `--no-ff` merge 接收**

---

## 2. 分支策略（强制）

### 2.1 命名约定

```
feature/<scope>-<short-desc>     # 新功能
fix/<scope>-<short-desc>         # bug 修复
hotfix/<scope>-<short-desc>      # 紧急修复
refactor/<scope>                 # 重构
docs/<scope>                     # 纯文档
```

**`<scope>` 示例**：`web-frontend` / `web-backend` / `todo` / `secret` / `importlib-plugin-discovery` / `backend-polish`

### 2.2 生命周期

```bash
# 1. 拉最新 dev
git checkout dev
git pull origin dev

# 2. 建 feature 分支
git checkout -b feature/web-frontend

# 3. 开发 + commit（详见 §3）
git add .
git commit -m "feat(web-frontend): stats dashboard"

# 4. 推 + 开 PR（base = dev）
git push origin feature/web-frontend
# → GitHub 上 Create PR，**base = dev**（不是 main）

# 5. Review + merge（dev 收）
# → maintainer merge 后可删 feature 分支

# 6. 本地同步
git checkout dev
git pull origin dev
git branch -d feature/web-frontend
```

### 2.3 分支隔离（多方向并行）

多人并行开发时，按"方向"分分支：

| 方向 | 分支示例 | 互不冲突的范围 |
|---|---|---|
| **前端** | `feature/web-frontend` | `.design/` / `core/web/static/` / `docs/prompts/` |
| **后端** | `feature/web-backend` | `plugins/` / `core/`（除 web/static）/ `tests/` / `docs/` |
| **规范 / 文档** | `docs/<scope>` | `*.md` / `CONTRIBUTING.md` / `docs/` |

**边界规则**：
- 前端 agent **不**改 `plugins/*.py` / `core/storage.py` / `core/secrets.py`（后端核心）
- 后端 agent **不**改 `.design/` / `core/web/static/`（前端设计 + 静态资源）
- 文档 agent **不**改 `.py`（除非是 docstring）
- 任何人**不**直接动 `main` / `dev` 的核心文件（除非 maintainer）

### 2.4 merge 顺序（前端 / 后端）

前端和后端并行开发时，**后端先合**，前端再合：

```
后端：feature/web-backend ──→ dev
                               ↓
前端：feature/web-frontend ──→ dev  (后端 API 已稳定)
```

**为什么后端先合**：前端依赖后端 API（REST endpoints），后端接口稳定后前端才能对接。

**反模式**：前端先合进 dev → 后端合时改 API → 前端断 → 返工。

---

## 3. Commit 规范（Conventional Commits）

### 3.1 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 3.2 类型

| 类型 | 含义 | 例子 |
|---|---|---|
| `feat` | 新功能 | `feat(todo): x todo tag action` |
| `fix` | bug 修复 | `fix(x): register x web subcommand` |
| `docs` | 文档 | `docs: add release.md` |
| `test` | 测试 | `test(e2e): add 8 e2e tests for x todo tag` |
| `refactor` | 重构 | `refactor(todo): extract _todo_archive helper` |
| `chore` | 杂项 | `chore(.gitignore): exclude build/` |
| `perf` | 性能 | `perf(todo): cache tag list lookup` |

### 3.3 scope（可选）

模块 / 子命令 / 方向：
- `todo` / `secret` / `web` — 子系统
- `x` — 主入口
- `core` / `plugins` / `tests` — 目录
- `release` / `docs` — 类别
- `web-frontend` / `web-backend` — 多方向分支时

### 3.4 完整例子

```
feat(todo): 实现 x todo tag 命令

- 支持 x todo tag <id> <tag>... 添加 tag
- 支持 x todo tag --remove <id> <tag>... 移除 tag
- 支持 x todo tag --clear <id> 清空 tags
- 退出码：0 成功 / 2 参数错 / 3 不存在 / 4 已归档
- 保留未知字段（手写 parser round-trip 保证）

BDD: docs/behaviors/todo-tag-behavior.md (17 场景)
Tests: 14 unit + 8 e2e

Closes #15
```

---

## 4. PR / Merge 流程

### 4.1 PR checklist

开 PR 前自查：

- [ ] **base 分支 = dev**（不是 main）
- [ ] commit message 符合 Conventional Commits
- [ ] 跑过 `pytest` 全量（除 e2e 可选）+ 0 failed
- [ ] 新功能有 BDD 行为规格（`docs/behaviors/`）+ 单测 + e2e
- [ ] CHANGELOG `Unreleased` 段更新
- [ ] 没引入第三方依赖（`pyproject.toml:dependencies = []`）
- [ ] 没改 YAML frontmatter 格式
- [ ] 没直接动 `main`

### 4.2 PR 描述模板

```markdown
## 改动
- 一句话总结 + 列表

## 测试
- 新增 N 个 unit test / M 个 e2e test
- 全量测试：X passed, 0 failed

## 风险
- 列出可能影响 + 缓解

## 关联
- Closes #issue
- Refs COMMANDS.md P0/P1

## Spec
- 引用 docs/superpowers/specs/<date>-<topic>-design.md（如有）
```

### 4.3 merge 按钮选择

| 场景 | 按钮 | 原因 |
|---|---|---|
| 1-2 commit 的小修复 | **Squash and merge** | 干净主分支历史 |
| 多 commit 的功能（带 BDD/TDD/implementation 分阶段）| **Merge commit**（保留分支历史）| 阶段清晰可追溯 |
| 多 commit 的重构 | **Rebase and merge** | 线性历史 |

**默认**：个人 feature 分支用 **Merge commit**（`--no-ff`），保留 feature 边界。

### 4.4 merge 后

```bash
git checkout dev
git pull origin dev
git branch -d feature/<name>             # 删本地
git push origin --delete feature/<name> # 删远程
```

---

## 5. 冲突解决

### 5.1 dev 频繁 update 时

当别人先合进 dev，你的 feature 分支需要同步：

```bash
# 在 feature 分支上
git fetch origin
git rebase origin/dev       # 优先用 rebase（线性历史）

# 如果 rebase 冲突：
# 1. 编辑冲突文件
# 2. git add .
# 3. git rebase --continue
# 4. 重跑测试
# 5. git push --force-with-lease（不是 --force）
```

**为什么不用 merge commit**：rebase 保持主分支线性，避免"merge bomb"（几十个 merge commit 难以 review）。

### 5.2 跨方向分支冲突

前端 / 后端分支并行时，如果都改了 `plugins/web.py`（不该发生但偶尔有）：

```
conflict in plugins/web.py:
  <<<<<<< feature/web-frontend
  # 前端加了一个新参数
  =======
  # 后端重命名了 function
  >>>>>>> feature/web-backend
```

**解决步骤**：

1. 跟冲突的 owner 沟通（**不要**擅自决定）
2. 通常后端的结构性变化优先（影响 API）
3. 前端的非结构性变化可以 rebase 跟后端
4. **测试**：合并后跑 e2e 验证 API 兼容性

### 5.3 跨 commit 撤销

如果 commit 错了（比如 `--force` 把别人 commit 弄没了）：

```bash
git reflog                              # 找 commit hash
git reset --hard <safe-commit-hash>     # 回到安全点
```

**铁律**：`--force` 只在自己分支用，**绝不** `--force` `dev` / `main`。

---

## 6. 前端开发规范（`docs/prompts/` 模式）

### 6.1 文件位置

| 内容 | 路径 |
|---|---|
| 设计稿（HTML / 截图 / 树状结构）| `.design/preview/<feature>/`（gitignored） |
| 前端 → 后端交接单 | `docs/prompts/<feature>-handoff.md` |
| 实现代码 | `core/web/static/`（HTML / CSS / JS）|

### 6.2 开发流程

```
[后端 agent] 实装 API（core/web/handlers/）
    ↓
[后端 agent] 写 docs/prompts/<feature>-handoff.md
    ↓
[前端 agent] 看交接单 + .design/preview/<feature>/
    ↓
[前端 agent] 在 core/web/static/ 实现 HTML/CSS/JS
    ↓
[前端 agent] 本地跑 x web start，访问 127.0.0.1:port 测试
    ↓
[前端 agent] commit + push feature/web-frontend
    ↓
[maintainer] review + merge 到 dev
```

**交接单模板**（`docs/prompts/<feature>-handoff.md`）：

```markdown
# <feature> 前端交接单

## 后端 API（已实装 + 已测试）
- GET /api/<endpoint> — 描述
- POST /api/<endpoint> — 描述

## 数据格式
- response JSON 字段表

## UI 要求（基于 .design/preview/）
- 截图链接 / 设计稿位置

## 边界
- 前端不改动 plugins/*.py / core/*.py
- 前端只用现有 API（不新加 endpoint 除非跟后端讨论）

## 已知问题
- 不在你修复范围内的（标注来源）
```

### 6.3 前端 agent 不做的事

- ❌ 改 `plugins/*.py`（后端插件）
- ❌ 改 `core/*.py`（除 `core/web/static/` 静态资源）
- ❌ 改 `core/web/server.py` / `core/web/auth.py` / `core/web/handlers/*.py`（后端 server + auth）
- ❌ 新加 REST endpoint（除非跟后端沟通 + 后端先合）

### 6.4 真实案例

- `feature/web-frontend`（v0.6.0，commit `f1bdb06`）— stats dashboard
- 交接单：`docs/prompts/web-frontend-handoff.md`
- 设计稿：`.design/preview/x-web-preview/`
- 实现：`core/web/static/`

---

## 7. 后端开发规范（`plugins/` 模式）

### 7.1 文件位置

| 内容 | 路径 |
|---|---|
| 核心库（被多个插件复用）| `core/<module>.py` |
| 插件（每个子命令一个文件）| `plugins/<name>.py` |
| 单元测试 | `tests/test_<module>.py` 或 `tests/test_<command>_<action>.py` |
| E2E 测试（subprocess 启动 x.exe）| `tests/test_e2e_<command>.py` |
| BDD 行为规格 | `docs/behaviors/<command>-<action>-behavior.md` |

### 7.2 开发流程（AGENTS.md §5 BDD + TDD 强制）

```
1. BDD：docs/behaviors/<command>-<action>-behavior.md
2. TDD Red：tests/test_<command>_<action>.py（先红）
3. 实现：plugins/<name>.py 或 core/<module>.py（绿）
4. E2E：tests/test_e2e_<command>.py
5. Refactor（如需要）
```

**禁止**：
- ❌ 跳过 BDD 直接写测试
- ❌ 跳过 TDD Red 直接写实现
- ❌ BDD 写完没对应测试

### 7.3 插件契约

每个 plugin 必须暴露 2 个接口：

```python
# plugins/<name>.py

def register(parser: argparse._SubParsersAction) -> None:
    """定义 argparse 子命令。"""
    sp = parser.add_parser("name", help="...")
    # ...


def run(args: argparse.Namespace) -> int:
    """执行并返回退出码（0 / 2 / 3 / 4 / 5）。"""
    if args.<name>_action == "x":
        return _<name>_x(args)
    # ...
```

**注册到 `x.py` SUBCOMMAND_HANDLERS**（v0.4.0 起强制）：

```python
# x.py
from plugins import <name> as _<name>_plugin

SUBCOMMAND_HANDLERS = {
    "<name>": _<name>_plugin.run,
    # ...
}
```

**`x.py` SUBCOMMAND_HANDLERS 是单一接入点**——加新 plugin 必加条目，否则命令行"未知子命令"。

### 7.4 后端 agent 不做的事

- ❌ 改 `.design/` / `core/web/static/`（前端设计 + 静态资源）
- ❌ 改 `docs/prompts/`（除非是写交接单）
- ❌ 改 `COMMANDS.md`（user-only 文件）
- ❌ 引第三方依赖（除非 PyInstaller 等 opt-in）
- ❌ 改 YAML frontmatter 格式（兼容性原则）

### 7.5 真实案例

- `plugins/todo.py`（v0.4.0 拆出，10 个 action）
- `plugins/secret.py`（v0.3.0，8 个 action）
- `plugins/web.py`（v0.6.0，3 个 action）
- 见 [docs/plugin-dev.md](docs/plugin-dev.md) 详细

---

## 8. 规范开发要求（**强约束清单**）

### 8.1 分支 / merge

- ❌ **禁止直接 push `main`**
- ❌ **禁止 PR base = `main`**（永远 base = `dev`）
- ❌ **禁止 `--force` 推到 `dev` / `main`**
- ✅ **PR merge 目标 = `dev`**
- ✅ **`main` 只通过 maintainer 的 `--no-ff` merge**

### 8.2 代码

- ❌ **不引第三方依赖**（`dependencies = []` 原则）— PyInstaller 等 opt-in 不算
- ❌ **不改 YAML frontmatter 格式**（未知字段 round-trip 不丢）
- ❌ **不创建同名空目录**
- ❌ **不在 x.py 单文件堆代码**（新 handler 放 `plugins/<name>.py`）
- ❌ **不引入 PyYAML / click / rich / pypinyin / jieba**（已确认不需要）

### 8.3 测试

- ✅ **新功能必须有 BDD + 单测 + e2e**（AGENTS.md §5）
- ✅ **覆盖率 ≥ 80%**（v0.6.0 实际 ~95%）
- ✅ **跑全量 pytest 不允许有 failed**（permission error 之类 cleanup 问题忽略）

### 8.4 输出格式

- ✅ **成功输出 emoji 前缀**：`✅` / `⏳` / `⚠️`
- ✅ **错误输出 emoji 前缀 + stderr**：`❌` / `⚠️`
- ✅ **退出码遵循约定**：0 成功 / 1 未知子命令 / 2 参数错 / 3 不存在 / 4 已归档/已存在 / 5 数据完整性
- ✅ **CJK 对齐**（表格列宽考虑中文宽度）

### 8.5 文档

- ✅ **CHANGELOG Unreleased 段每次合并更新**
- ✅ **新功能有 BDD 行为规格**
- ✅ **新插件有 plugin-dev.md 引用**
- ✅ **AGENTS.md 反映项目真实状态**（AGENTS.md 是给"未来的 agent"看的）
- ✅ **COMMANDS.md 是 user-only 文件** — AI 不擅自加命令（除非用户明确指令）

---

## 9. FAQ

**Q: 同事的 feature 分支我能不能 cherry-pick？**

A: 可以（用 `git cherry-pick <commit>`），但**优先 rebase + merge commit**——保留完整历史。cherry-pick 只在快速拿一个修复时用。

**Q: 我能不能直接 commit 到 dev？**

A: **不建议**。即使你能（dev 是 origin/HEAD），请用 feature 分支 + PR。原因：
- 跳过 review
- 跟多人 merge 容易冲突
- 没有 commit 历史可追溯

**Q: 我的 PR 怎么没人 review？**

A: 在 PR 描述里 @ maintainer + 解释 blocker。如果超过 24 小时没响应，私信 maintainer。

**Q: 我新加了一个 plugin 但忘了注册 SUBCOMMAND_HANDLERS？**

A: **不会有这个 bug 了**——`CONTRIBUTING.md §7.3` 强制要求注册。但**测试**也会发现：`tests/test_x.py` 测每个子命令出现在主入口帮助里（参考 `test_web_subcommand_is_registered`）。

**Q: 我可以重命名 plugin 的 register/run 函数吗？**

A: 不行，x.py 直接 import 这两个名字。改名字要同步改 x.py:SUBCOMMAND_HANDLERS。

**Q: 我怎么知道 dev 分支现在领先 main 几个 commit？**

A: `git log main..dev --oneline | wc -l`。release 时机：dev 比 main 领先足够多（通常一个 sprint / 一个 minor 版本号）。

---

## 10. 关联文档

| 文档 | 内容 |
|---|---|
| [AGENTS.md](AGENTS.md) | AI agent 工作规范（**同步核心规范到 AI**）|
| [COMMANDS.md](COMMANDS.md) | 用户编辑的命令清单（**user-only 文件**）|
| [docs/architecture.md](docs/architecture.md) | 架构设计 |
| [docs/commands.md](docs/commands.md) | 完整命令参考 |
| [docs/plugin-dev.md](docs/plugin-dev.md) | 后端插件开发详解 |
| [docs/testing.md](docs/testing.md) | 测试分层 + 597 用例 |
| [docs/release.md](docs/release.md) | PyInstaller 打包 |
| [docs/behaviors/](docs/behaviors/) | BDD 行为规格 |
| [CHANGELOG.md](CHANGELOG.md) | 版本历史 |
| [docs/prompts/](docs/prompts/) | 前端 / 后端交接单 |

---

*Last updated: 2026-06-28 — v0.6.0 重写（原 fork 模式 → 多人直接协作）*