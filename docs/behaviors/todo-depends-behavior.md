# x todo 任务依赖 行为规格（v0.5 Phase E）

> **对应命令**：`x todo add / update`、`x todo list`
> **新增 flag**：`--depends <id>`（可多次指定，逗号分隔）
> **数据规范**：`depends: list[str]` 字段（被依赖任务的 ID 列表）
> **来源**：[PLAN-v0.5.md §2.4.2](../../../PLAN-v0.5.md)
>
> **v0.5 范围**：
> - ✅ 字段可写可清除
> - ✅ list 表格显示 🔒 + 依赖任务名（未完成时）
> - ❌ **不做**循环依赖检测（用户自己保证）
> - ❌ **不做**自动阻塞（v0.5 仅展示，不强制）
>
> **覆盖范围**：
> - add --depends 多个
> - update --depends 覆盖 / 清空
> - list 显示 🔒 + 依赖未完成的任务
> - 错误路径

---

## 场景 1：`add --depends` 单依赖

**Given**：
- 任务 `t-review` 存在

**When**：
- 运行 `x todo add "考试" --deadline 2026-07-03 --depends t-review`

**Then**：
- 退出码：`0`
- YAML frontmatter `depends`：`["t-review"]`

---

## 场景 2：`add --depends` 多依赖（逗号分隔）

**When**：
- 运行 `x todo add "综合" --depends t-a,t-b,t-c`

**Then**：
- 退出码：`0`
- YAML frontmatter `depends`：`["t-a", "t-b", "t-c"]`

---

## 场景 3：`add --depends` 引用不存在的任务（错误）

**When**：
- 运行 `x todo add "test" --depends t-nope`

**Then**：
- 退出码：非 0（如 `3`）
- 输出：`"❌ 依赖任务不存在：t-nope"`
- 不创建任何文件

---

## 场景 4：`update --depends` 覆盖

**Given**：
- 任务 `t-x`：`depends = ["t-a"]`

**When**：
- 运行 `x todo update t-x --depends t-b,t-c`

**Then**：
- 退出码：`0`
- YAML frontmatter `depends`：`["t-b", "t-c"]`（完全替换）

---

## 场景 5：`update --depends ""` 清空

**Given**：
- 任务 `t-x`：`depends = ["t-a"]`

**When**：
- 运行 `x todo update t-x --depends ""`

**Then**：
- 退出码：`0`
- YAML frontmatter 中 **不写入** `depends` 字段

---

## 场景 6：list 显示有未完成依赖的任务 🔒

**Given**：
- 任务 `t-prereq`：`status = pending`
- 任务 `t-task`：`depends = ["t-prereq"]`, `status = pending`

**When**：
- 运行 `x todo list`

**Then**：
- 退出码：`0`
- `t-task` 行的 Name 列显示 `🔒 t-task` 或类似（带依赖未完成标记）
- 内容含 `t-prereq` 名字（说明依赖谁）

---

## 场景 7：list 不显示 🔒 当依赖已完成

**Given**：
- 任务 `t-prereq`：`status = archived (done)`（已完成）
- 任务 `t-task`：`depends = ["t-prereq"]`, `status = pending`

**When**：
- 运行 `x todo list`

**Then**：
- `t-task` 行的 Name 列**不**带 🔒 标记（依赖已满足）
- 或 🔒 仍显示但附加 ✅ 标识

---

## 场景 8：list --show-deps 显示完整依赖

**Given**：
- 任务 A：depends = ["B", "C"]

**When**：
- 运行 `x todo list --show-deps`

**Then**：
- 任务 A 行追加额外列 `Deps: B, C`

---

*本文件由 v0.5 Phase E 任务生成（2026-06-30），覆盖 --depends 字段 + 列表显示，不含循环检测 / 自动阻塞*