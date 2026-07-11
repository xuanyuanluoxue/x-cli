# Collaborative Development Docs 设计

**日期**：2026-06-28
**作者**：x-cli 后端 agent
**状态**：✅ 用户已确认（4 选 1：重写 CONTRIBUTING.md）

---

## 0. 背景

x-cli 实际工作模式是**多人直接 push 到 dev 分支**（基于 v0.6.0 commit 历史和当前分支现状）：

```
* feature/backend-polish     ← 本 agent 这次开发
  feature/importlib-plugin-discovery   ← 别人在改
  feature/web-backend       ← 远程
  main                       ← 保护，不直接 push
  dev                        ← origin/HEAD（默认分支）
```

**但现有 CONTRIBUTING.md 还是 v0.4.x 的 GitHub fork 模式**，不适用于多人直接 push。

**CHANGELOG v0.6.0 第 47 行** 说"`AGENTS.md §4.4` Git 分支策略"要加，但实际没加。

---

## 1. 目标 & 非目标

### 1.1 目标

- ✅ **重写 CONTRIBUTING.md**：多人直接协作模式（删 fork 流程），覆盖前端 / 后端 / 规范三主题
- ✅ **AGENTS.md §4.4**：补 Git 分支策略（简明版，让 AI 看到）
- ✅ **AI + 人可见**：CONTRIBUTING.md 内容通过 AGENTS.md 同步给 AI（always_applied workspace rules）

### 1.2 非目标

- ❌ 不创建 docs/workflow.md / docs/frontend.md / docs/backend.md（用户没选）
- ❌ 不改 git remote / branch protection（那是 GitHub 设置）
- ❌ 不改 `feature/importlib-plugin-discovery` 等别人分支
- ❌ 不实装自动化（CI / pre-commit / PR 模板）— 只写规范

---

## 2. 方案对比

### 方案 A（推荐）：CONTRIBUTING.md 一份覆盖全部主题

| 优势 | 劣势 |
|---|---|
| GitHub 默认识别 CONTRIBUTING.md，PR 自动展示 | 单文件 ~300 行，偏长 |
| 主题连贯（前端 / 后端 / 规范在同一文档）| 不利于按主题查询 |
| 改一次同步所有人 + AI | — |

### 方案 B：CONTRIBUTING.md（人） + docs/ 多个文档（AI + 内部）

| 优势 | 劣势 |
|---|---|
| 主题分离 | 两份内容要同步维护 |
| 人只看 CONTRIBUTING.md，AI 看 docs/ | 用户明确选了仓库根 + AI 可见 |

**不推荐**，违反用户选择。

### 方案 C：拆 docs/collab.md / docs/frontend.md / docs/backend.md

**用户没选**，不符合用户"1 个 doc"的意图。

---

## 3. 文档结构（CONTRIBUTING.md）

### 3.1 章节大纲

```markdown
# Contributing to x-cli

## 1. 项目模式（多人直接 push）
   - 不是 fork / PR base main 模式
   - 主分支：main（保护）/ dev（origin/HEAD）
   - feature/<name> 分支开发

## 2. 分支策略（强制）
   - main：受保护，不直接 push
   - dev：origin/HEAD，所有 PR merge 目标
   - feature/<name>：从 dev 拉，做完 merge 回 dev
   - hotfix/<name>：紧急修复，main + dev 同步
   - **❌ 禁止：直接 push 到 main**

## 3. Commit 规范
   - Conventional Commits 格式
   - 例子
   - 类型列表（feat/fix/docs/test/refactor/chore）

## 4. PR / merge 流程
   - 创建 PR → base = dev（不是 main）
   - Review checklist
   - Merge 按钮（squash / merge commit / rebase）
   - Merge 后删 feature 分支

## 5. 冲突解决
   - dev 频繁 update 时 rebase 自己的 feature
   - 跨方向分支（前端 / 后端）的 merge 顺序

## 6. 前端开发规范（docs/prompts/ 模式）
   - 设计稿在 .design/preview/<name>/
   - 交接单在 docs/prompts/<name>-handoff.md
   - 实现代码在 core/web/static/
   - **边界**：前端 agent 不改 plugins/*.py / core/*.py（除 web/）

## 7. 后端开发规范（plugins/ 模式）
   - BDD + TDD 流程（AGENTS.md §5）
   - plugins/<name>.py 契约
   - 测试要求（单测 + e2e）
   - **边界**：后端 agent 不改 .design/ / core/web/static/

## 8. 规范开发要求（强约束）
   - 不直接合并主分支（合并目标必须是 dev）
   - 不直接 push main
   - BDD 先于 TDD
   - 不引第三方依赖（除非 PyInstaller 等 opt-in）
   - 不改 storage YAML 格式
   - 中文输出 + emoji 前缀
   - 退出码 0/2/3/4/5
```

---

## 4. AGENTS.md §4.4（简明版）

只补 Git 分支策略，让 AI 看到：

```markdown
### 4.4 Git 分支策略（v0.6.0 起强制）

- main：受保护，**禁止直接 push**。所有变更必须经 dev merge。
- dev：origin/HEAD，所有 PR 的 merge 目标。
- feature/<name>：从 dev 拉，做完 merge 回 dev。
- hotfix/<name>：紧急修复，main + dev 同步。
- 详细见 [CONTRIBUTING.md](CONTRIBUTING.md)。
```

---

## 5. 风险 & 缓解

| 风险 | 缓解 |
|---|---|
| 跟别人分支冲突 | 我**只**改 CONTRIBUTING.md + AGENTS.md（两个文件），不碰 plugins/ / core/ |
| GitHub 远程默认 base = main | CONTRIBUTING.md 明确写 "PR base = dev" |
| 中文 / 英文混杂 | CONTRIBUTING.md 用中英混合（跟 CHANGELOG / AGENTS.md 风格一致） |

---

## 6. 实施步骤

| Step | 操作 | Commit 前缀 |
|---|---|---|
| 1 | 重写 CONTRIBUTING.md | `docs(CONTRIBUTING)` |
| 2 | AGENTS.md §4.4 补 Git 分支策略 | `docs(AGENTS)` |
| 3 | （可选）CHANGELOG Unreleased 加一行 | `docs(changelog)` |

---

*Last updated: 2026-06-28*