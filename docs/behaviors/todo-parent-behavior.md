# x todo 子任务 行为规格（v0.5 Phase B）

> **对应命令**：`x todo add / update / list / archive / restore`
> **新增 flag**：`--parent <id>`（add / update）
> **数据规范**：`parent` 字段（仅 ID 引用，不嵌套 children）
> **来源**：[PLAN-v0.5.md §2.2.1](../../../PLAN-v0.5.md)
>
> **覆盖范围**：
> - 子任务创建（add / update 设 parent）
> - 2 层校验（parent chain 上限 = 2 跳）
> - 树形展示（list 自动 / 显式 `--tree`）
> - archive 父任务级联子任务
> - 向后兼容（旧任务无 parent 字段）

---

## 场景 1：add `--parent` 创建子任务

**Given**：
- 仓库 `<xcli_todo_dir>/` 已初始化
- 存在任务 `t-fd316ca8`（无 parent）

**When**：
- 运行 `x todo add "清扫宿舍" --parent t-fd316ca8`

**Then**：
- 退出码：`0`
- 输出：`"✅ 任务已创建：清扫宿舍（ID: <自动生成的子任务 slug>）"`
- YAML frontmatter：
  - `id`：新生成的 kebab-case id
  - `name`：清扫宿舍
  - `parent`：`t-fd316ca8`
  - `status`：pending
  - `priority`：medium

---

## 场景 2：add `--parent` 创建孙任务（2 层）

**Given**：
- 存在任务 `t-fd316ca8`（root，无 parent）
- 存在任务 `t-abc123`，`parent = t-fd316ca8`

**When**：
- 运行 `x todo add "擦窗户" --parent t-abc123`

**Then**：
- 退出码：`0`
- 新任务 `parent = t-abc123`
- 形成 root → child → grandchild 链路（depth=2）

---

## 场景 3：add `--parent` 引用不存在的任务（错误路径）

**Given**：
- 仓库已初始化，**不存在**任务 `t-nope`

**When**：
- 运行 `x todo add "子任务" --parent t-nope`

**Then**：
- 退出码：非 0（如 `3`）
- 输出错误：`"❌ 父任务不存在：t-nope"`
- 不创建任何文件

---

## 场景 4：add `--parent` 形成 3 层链（错误路径，超 2 层）

**Given**：
- 存在任务 `t-gc`（孙任务，`parent = t-child`，`t-child.parent = t-root`）

**When**：
- 运行 `x todo add "重孙" --parent t-gc`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ 子任务最多 2 层：t-gc 已经是孙任务"`
- 不创建任何文件

---

## 场景 5：`update --parent` 设置 parent

**Given**：
- 任务 `t-orphan` 存在，无 parent

**When**：
- 运行 `x todo update t-orphan --parent t-fd316ca8`

**Then**：
- 退出码：`0`
- YAML frontmatter：`parent` 设为 `t-fd316ca8`

---

## 场景 6：`update --parent ""` 清除 parent（脱离父任务）

**Given**：
- 任务 `t-child`，`parent = t-fd316ca8`

**When**：
- 运行 `x todo update t-child --parent ""`

**Then**：
- 退出码：`0`
- YAML frontmatter 中 **删除** `parent` 字段（不是空字符串）

---

## 场景 7：`list` 自动树形展示（有 parent 时）

**Given**：
- 任务 `t-root`（无 parent）
- 任务 `t-child`，`parent = t-root`
- 任务 `t-gc`，`parent = t-child`

**When**：
- 运行 `x todo list`

**Then**：
- 退出码：`0`
- 输出以树形展示：
  ```
  t-root      父任务         ⏳  ...
    └ t-child  子任务       ⏳  ...
      └ t-gc   孙任务       ⏳  ...
  ```
- 没有 parent 的其他任务正常列出（不带缩进）

---

## 场景 8：`list --tree` 显式开启树形展示

**Given**：
- 没有任务有 parent（全部独立）

**When**：
- 运行 `x todo list --tree`

**Then**：
- 退出码：`0`
- 输出与普通 list 相同（无缩进，因为没有父子关系）

---

## 场景 9：`archive` 父任务级联子 + 孙任务

**Given**：
- 任务 `t-root`，子 `t-child`，孙 `t-gc`

**When**：
- 运行 `x todo archive t-root --reason done`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已归档：t-root, t-child, t-gc（共 3 个）"`（或类似汇总）
- 文件系统：
  - `任务/` 下不再有 `t-root` / `t-child` / `t-gc` 文件夹
  - `归档/` 下有 3 个对应归档文件夹
- 所有 3 个任务的 `status` 变为 `archived`，`reason` 为 `done`

---

## 场景 10：archive 单个子任务不影响父任务

**Given**：
- 任务 `t-root`，子 `t-child`

**When**：
- 运行 `x todo archive t-child --reason done`

**Then**：
- 退出码：`0`
- 只有 `t-child` 归档；`t-root` 仍是 active

---

## 场景 11：update 子任务不影响父任务

**Given**：
- 任务 `t-root`，子 `t-child`

**When**：
- 运行 `x todo update t-child --priority low`

**Then**：
- 退出码：`0`
- `t-child.priority` 变为 `low`
- `t-root.priority` 不变（即使它原本是 high）

---

## 场景 12：向后兼容（旧任务无 parent 字段）

**Given**：
- v0.4 创建的任务 `t-legacy`，YAML **无** `parent` 字段

**When**：
- 运行 `x todo list`

**Then**：
- 退出码：`0`
- `t-legacy` 正常列出，作为 root（顶级无缩进）
- 运行 `x todo update t-legacy --priority high` 也不报错

---

## 场景 13：环形 parent 检测（错误路径）

**Given**：
- 任务 `t-a`，`parent = t-b`
- 任务 `t-b`，`parent = t-a`

**When**：
- 不需要触发该路径（实际使用中难以构造此情况）

**Then**：
- 文档说明：v0.5 不做循环依赖检测，用户自己保证

---

## 场景 14：`update` 不能把 parent 设为自己的子任务（避免环）

**Given**：
- 任务 `t-a`，子 `t-b`（`parent = t-a`）

**When**：
- 运行 `x todo update t-a --parent t-b`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ 不能把 parent 设为自己的后代：t-b"`
- `t-a.parent` 不变

---

*本文件由 v0.5 Phase B 任务生成（2026-06-30），覆盖子任务 2 层结构 + 永远级联 archive*