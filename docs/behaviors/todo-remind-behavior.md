# x todo 提醒 行为规格（v0.5 Phase C）

> **对应命令**：`x todo add / update / list / reminder list / reminder clear`
> **新增 flag**：`--remind`（add / update 都支持）
> **新增子命令**：`x todo reminder list / clear`
> **新增 list flag**：`--reminding`（筛选带 remind 字段的任务）
> **数据规范**：`remind` 字段（list[str] 数组，元素格式 `Nd / Nh / Nm`）
> **来源**：[PLAN-v0.5.md §2.2.2](../../../PLAN-v0.5.md)
>
> **v0.5 范围**（明确）：
> - ✅ 字段可写、可显示、可清除、可筛选、可统计
> - ❌ **不触发任何通知**（daemon / scheduler / 系统通知全部推到 v0.6+ 打包 exe 后）
>
> **覆盖范围**：
> - remind 字段 add / update / clear 写入
> - 互斥/校验（reminder clear "" → 清字段）
> - `x todo reminder list` 只读
> - `x todo reminder clear` 多 id
> - `x todo list --reminding` 筛选
> - `x todo stats` 统计有提醒的任务数
> - 错误路径（非法 remind 格式）
> - 向后兼容（无 remind 字段）

---

## 场景 1：`add --remind` 单值

**Given**：
- 仓库 `<xcli_todo_dir>/` 已初始化

**When**：
- 运行 `x todo add "考试" --deadline 2026-07-03 --time 08:20 --remind 1d`

**Then**：
- 退出码：`0`
- YAML frontmatter `remind`：`["1d"]`（list[str]）

---

## 场景 2：`add --remind` 多值（逗号分隔）

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "重要会议" --deadline 2026-07-05 --remind 1d,2h,30m`

**Then**：
- 退出码：`0`
- YAML frontmatter `remind`：`["1d", "2h", "30m"]`

---

## 场景 3：`update --remind` 修改

**Given**：
- 任务 `t-xxx` 存在，`remind = ["1d"]`

**When**：
- 运行 `x todo update t-xxx --remind 2h,15m`

**Then**：
- 退出码：`0`
- YAML frontmatter `remind` 改为 `["2h", "15m"]`

---

## 场景 4：`update --remind ""` 清除

**Given**：
- 任务 `t-xxx` 存在，`remind = ["1d", "2h"]`

**When**：
- 运行 `x todo update t-xxx --remind ""`

**Then**：
- 退出码：`0`
- YAML frontmatter 中 **删除** `remind` 字段

---

## 场景 5：非法 remind 格式（错误路径）

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "测试" --remind abc`（非 Nd/Nh/Nm 格式）

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ remind 格式错误：abc（合法：Nd / Nh / Nm，支持小数）"`
- 不创建任何文件

**When**：
- 运行 `x todo add "测试" --remind -5m`（负数）

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ remind 必须为正数：-5m"`

---

## 场景 6：`x todo reminder list` 只读展示

**Given**：
- 任务 A：`remind = ["1d"]`
- 任务 B：`remind = ["2h", "30m"]`
- 任务 C：无 `remind` 字段

**When**：
- 运行 `x todo reminder list`

**Then**：
- 退出码：`0`
- 输出按表头列出：**ID / Name / Deadline / Time / Reminders**
- 任务 A 行的 Reminders 列：`1d`
- 任务 B 行的 Reminders 列：`2h, 30m`
- 任务 C **不出现**（无 remind 字段的任务不显示）
- 表格提示文案末尾说明：`📭 没有带提醒的任务`（若无任何提醒）

---

## 场景 7：`x todo reminder clear <id...>` 多 id 清除

**Given**：
- 任务 A：`remind = ["1d"]`
- 任务 B：`remind = ["2h"]`

**When**：
- 运行 `x todo reminder clear t-A t-B`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已清除提醒：t-A, t-B（共 2 个）"`
- 两个任务的 YAML frontmatter 中 **remind 字段均已删除**

---

## 场景 8：`x todo reminder clear` 不存在的任务（错误路径）

**Given**：
- 仓库已初始化，**不存在**任务 `t-nope`

**When**：
- 运行 `x todo reminder clear t-nope`

**Then**：
- 退出码：非 0（如 `3`）
- 输出错误：`"❌ 任务不存在：t-nope"`

---

## 场景 9：`x todo list --reminding` 筛选

**Given**：
- 任务 A：`remind = ["1d"]`
- 任务 B：`remind = ["2h"]`
- 任务 C：无 `remind` 字段

**When**：
- 运行 `x todo list --reminding`

**Then**：
- 退出码：`0`
- 表格仅显示任务 A 和 B（C 被过滤）
- 不影响其他列（Time / Deadline 等正常显示）

---

## 场景 10：`x todo stats` 显示有提醒任务数

**Given**：
- 任务 A：`remind = ["1d"]`
- 任务 B：`remind = ["2h", "30m"]`
- 任务 C：无 `remind` 字段
- 其他 5 个无提醒任务

**When**：
- 运行 `x todo stats`

**Then**：
- 退出码：`0`
- 输出中包含：`"⏰ 有提醒任务数：2"`（A + B，C 不算，其他任务不算）

---

## 场景 11：向后兼容（v0.4 任务无 remind 字段）

**Given**：
- v0.4 创建的任务 `t-legacy`，YAML **无** `remind` 字段

**When**：
- 运行 `x todo reminder list`

**Then**：
- 退出码：`0`
- 任务不出现（无 remind 字段不视为「带提醒」）

**When**：
- 运行 `x todo update t-legacy --priority high`

**Then**：
- 退出码：`0`
- 仍不写入 `remind` 字段（不传就不写）

---

## 场景 12：`x todo add --remind ""`（空字符串）等价于不传

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "测试" --remind ""`

**Then**：
- 退出码：`0`
- YAML frontmatter 中 **不写入** `remind` 字段（空字符串等价不传）

---

*本文件由 v0.5 Phase C 任务生成（2026-06-30），覆盖提醒只读 + 筛选 + 清除 + 统计，不含通知触发（v0.6+ 落地）*