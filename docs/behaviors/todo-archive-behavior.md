# x todo archive 行为规格

> **对应命令**：`x todo archive <id> [选项]`
> **命令参考**：[docs/commands.md §2.5](../../commands.md)
> **数据规范**：[../TODO-SPEC.md](../TODO-SPEC.md)
>
> **覆盖范围**：
> - 默认 `reason=done` 归档
> - 指定 `reason`（done / cancelled / expired / failed）
> - ID 不存在
> - 任务已归档（重复归档错误）
> - 文件夹物理移动副作用
> - 未知字段保留（与 update 一致）

---

## 场景 1：默认 `reason=done` 归档（最常见）

**Given**：
- 任务 `kemu1` 存在：`<xcli_todo_dir>/任务/科目一/TODO.md`
- `status=in_progress / priority=high / deadline=2026-08-31`
- 当前日期：`2026-08-30`

**When**：
- 运行 `x todo archive kemu1`

**Then**：
- 退出码：`0`
- 输出：`"✅ 任务已归档：科目一模拟考（ID: kemu1，reason=done）"`
- **物理移动**：`任务/科目一/` → `归档/20260830-科目一/`
- 新位置：`<xcli_todo_dir>/归档/20260830-科目一/TODO.md`
- 新 frontmatter：
  - `status`：archived
  - `reason`：done（默认值）
  - `updated`：2026-08-30
  - `folder`：归档/20260830-科目一
  - 其他字段（id / name / priority / deadline / tags / created / subtasks）保留
- 旧位置 `任务/科目一/` **不存在**（已被移动）

---

## 场景 2：指定 `reason=cancelled`

**Given**：
- 任务 `tvg-repair-2026` 存在：`status=blocked`
- 当前日期：`2026-06-21`

**When**：
- 运行 `x todo archive tvg-repair-2026 --reason cancelled`

**Then**：
- 退出码：`0`
- 输出：`"✅ 任务已归档：电视维修单（ID: tvg-repair-2026，reason=cancelled）"`
- 物理移动：`任务/电视维修单/` → `归档/20260621-电视维修单/`
- 新 frontmatter：
  - `status`：archived
  - `reason`：cancelled
  - `updated`：2026-06-21

---

## 场景 3：指定 `reason=expired`（逾期归档）

**Given**：
- 任务 `kemu1` 存在：`deadline=2026-05-01`（已过期）
- 当前日期：`2026-06-21`

**When**：
- 运行 `x todo archive kemu1 --reason expired`

**Then**：
- 退出码：`0`
- 输出：`"✅ 任务已归档：科目一模拟考（ID: kemu1，reason=expired）"`
- 物理移动到 `归档/20260621-科目一/`
- frontmatter `reason=expired`

---

## 场景 4：ID 不存在（错误路径）

**Given**：
- 仓库中无 `nonexistent-id` 任务

**When**：
- 运行 `x todo archive nonexistent-id`

**Then**：
- 退出码：非 0（如 `3`）
- 输出错误：`"❌ 任务不存在：nonexistent-id"`
- 不修改任何文件

---

## 场景 5：任务已归档（重复归档错误）

**Given**：
- 归档任务 `20260521-xiangjifanmai` 存在，位于 `<xcli_todo_dir>/归档/20260521-相机贩卖业务/`

**When**：
- 运行 `x todo archive 20260521-xiangjifanmai`

**Then**：
- 退出码：非 0（如 `4`）
- 输出错误：`"❌ 任务已归档：20260521-xiangjifanmai（位于 归档/20260521-相机贩卖业务）"`
- 不创建重复归档文件夹（如 `归档/20260621-20260521-相机贩卖业务/`）

---

## 场景 6：非法 `reason` 值（错误路径）

**Given**：
- 任务 `kemu1` 存在

**When**：
- 运行 `x todo archive kemu1 --reason invalid_reason`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ 无效的 reason 值：invalid_reason（合法值：done / cancelled / expired / failed）"`
- 不移动文件夹，不修改文件

---

## 场景 7：保留未知字段（关键兼容性）

**Given**：
- 任务 `kemu1` 存在，frontmatter 含未知字段：
  ```yaml
  description: 科目一学时已刷完
  paused_at: 2026-06-13
  pause_reason: 用户表态「不刷题了」
  ```

**When**：
- 运行 `x todo archive kemu1 --reason cancelled`

**Then**：
- 退出码：`0`
- 归档后 `<xcli_todo_dir>/归档/20260621-科目一/TODO.md` **必须保留**：
  - `description: 科目一学时已刷完`
  - `paused_at: 2026-06-13`
  - `pause_reason: 用户表态「不刷题了」`
- 同时新增：`status: archived` / `reason: cancelled` / `folder: 归档/20260621-科目一`

---

## 场景 8：归档时更新总索引 TODO.md

**Given**：
- 仓库总索引 `<xcli_todo_dir>/TODO.md` 已存在（v1.1 格式，含 `inventory:` 字段）
- 归档前：`pending: 3 / in_progress: 4 / blocked: 1 / waiting: 0 / archived: 22`

**When**：
- 运行 `x todo archive kemu1 --reason done`

**Then**：
- 退出码：`0`
- 总索引 `TODO.md` 更新：
  - `inventory.in_progress` 减 1（如 4 → 3）
  - `inventory.archived` 加 1（如 22 → 23）
  - `last_updated`：当前日期
  - `version`：保持不变（不因归档而升级 schema 版本）

---

*本文件由 bdd-specs 任务生成（2026-06-21），覆盖 x todo archive 命令的所有成功/边界/错误路径*
