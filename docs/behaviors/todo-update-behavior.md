# x todo update 行为规格

> **对应命令**：`x todo update <id> [选项]`
> **命令参考**：[docs/commands.md §2.4](../../commands.md)
> **数据规范**：[../TODO-SPEC.md](../TODO-SPEC.md)
>
> **覆盖范围**：
> - 更新单字段（status / priority / deadline / tags）
> - 同时更新多字段
> - ID 不存在
> - 非法状态/优先级/日期值
> - 清除 deadline（边界）
> - **保留未知字段**（关键兼容性约束，如 `description` / `paused_at` / `pause_reason`）

---

## 场景 1：更新任务状态（最常见）

**Given**：
- 任务 `kemu1` 存在：`status=pending / priority=high / deadline=2026-08-31`
- 当前日期：`2026-06-21`

**When**：
- 运行 `x todo update kemu1 --status in_progress`

**Then**：
- 退出码：`0`
- 输出：`"✅ 任务已更新：科目一模拟考（ID: kemu1）"`
- `<xcli_todo_dir>/任务/科目一模拟考/TODO.md` 的 frontmatter：
  - `status`：in_progress（已更新）
  - `priority`：high（**未变**）
  - `deadline`：2026-08-31（**未变**）
  - `updated`：2026-06-21（**已更新**）
  - `created`：2026-03-27（**未变**）
  - `folder`：**未变**（不移动文件）

---

## 场景 2：同时更新多字段

**Given**：
- 任务 `kemu1` 存在：`status=pending / priority=high / deadline=2026-08-31 / tags=[驾照, 暑假]`

**When**：
- 运行 `x todo update kemu1 --priority medium --deadline 2026-07-15 --tags 驾照`

**Then**：
- 退出码：`0`
- frontmatter 变化：
  - `priority`：medium
  - `deadline`：2026-07-15
  - `tags`：`[驾照]`（**完全替换**，不是合并）
  - `updated`：2026-06-21

---

## 场景 3：ID 不存在（错误路径）

**Given**：
- 仓库中不存在任务 `nonexistent-id`
- 但 `<xcli_todo_dir>/任务/科目一/TODO.md` 存在（id=`kemu1`）

**When**：
- 运行 `x todo update nonexistent-id --status in_progress`

**Then**：
- 退出码：非 0（如 `3`）
- 输出错误：`"❌ 任务不存在：nonexistent-id"`
- 提示信息：`"💡 提示：运行 'x todo list' 查看现有任务 ID"`
- 不修改任何文件

---

## 场景 4：非法 status 值（错误路径）

**Given**：
- 任务 `kemu1` 存在

**When**：
- 运行 `x todo update kemu1 --status active`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ 无效的 status 值：active（合法值：pending / in_progress / blocked / waiting / archived）"`
- 不修改 `TODO.md`

---

## 场景 5：清除 deadline（边界）

**Given**：
- 任务 `kemu1` 存在：`deadline=2026-08-31`

**When**：
- 运行 `x todo update kemu1 --deadline ""`（显式清空）

**Then**：
- 退出码：`0`
- frontmatter 中 **移除 `deadline` 字段**（不是设为空字符串，是完全删除）
- `updated`：2026-06-21

---

## 场景 6：保留未知字段（关键兼容性）

**Given**：
- 任务 `kemu1` 的 `TODO.md` 包含 x-cli 不识别的字段：
  ```yaml
  description: 科目一学时已刷完
  paused_at: 2026-06-13
  pause_reason: 用户 6/13 01:11 「不刷题了，长期规划中」
  ```

**When**：
- 运行 `x todo update kemu1 --status in_progress`

**Then**：
- 退出码：`0`
- 更新后的 frontmatter **必须保留** `description` / `paused_at` / `pause_reason` 三个字段及其值
- 这些字段的顺序可以保持不变或在合理位置
- 不允许因为 `status` 更新而丢失任何非 x-cli 管理的字段

---

## 场景 7：更新 archived 任务（错误路径）

**Given**：
- 归档任务 `20260521-xiangjifanmai` 存在（位于 `<xcli_todo_dir>/归档/20260521-相机贩卖业务/TODO.md`，`status=archived`）

**When**：
- 运行 `x todo update 20260521-xiangjifanmai --priority high`

**Then**：
- 退出码：非 0（如 `4`）
- 输出错误：`"❌ 已归档任务不可更新：20260521-xiangjifanmai"`
- 提示信息：`"💡 如需重新激活，请先用 'x todo restore' 还原（如该命令存在）"`
- 不修改归档文件

---

## 场景 8：无任何选项（错误路径）

**Given**：
- 任务 `kemu1` 存在

**When**：
- 运行 `x todo update kemu1`（不带任何 --xxx 选项）

**Then**：
- 退出码：非 0（如 `2`）
- 输出 argparse 标准错误：`"at least one of --status / --priority / --deadline / --tags is required"`
- 不修改任何文件

---

*本文件由 bdd-specs 任务生成（2026-06-21），覆盖 x todo update 命令的所有成功/边界/错误路径*
