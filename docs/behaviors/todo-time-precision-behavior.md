# x todo 时间精度 行为规格（v0.5 Phase A）

> **对应命令**：`x todo add / update / list`
> **新增 flag**：`--time HH:MM` / `--end-time HH:MM` / `--duration <N><h|m|空>`
> **数据规范**：[../TODO-SPEC.md](../TODO-SPEC.md)
> **来源**：[PLAN-v0.5.md §2.1](../../../PLAN-v0.5.md)
>
> **覆盖范围**：
> - `--time` 单时间点（add / update）
> - `--end-time` 时间段（add / update）
> - `--duration` 持续时间（add / update）
> - 互斥校验（`--end-time` vs `--duration`）
> - list 输出新增 `Time` 列
> - 错误路径（格式非法 / 范围越界）
> - 向后兼容（旧任务无 time 字段）

---

## 场景 1：`add --time` 单时间点

**Given**：
- 仓库 `<xcli_todo_dir>/` 已初始化
- 当前日期：`2026-08-31`

**When**：
- 运行 `x todo add "科目一模拟考" --deadline 2026-08-31 --time 08:20`

**Then**：
- 退出码：`0`
- 输出：`"✅ 任务已创建：科目一模拟考（ID: <slug>）"`
- YAML frontmatter：
  - `id`：自动生成
  - `name`：科目一模拟考
  - `status`：pending
  - `priority`：medium（默认）
  - `created`：2026-08-31
  - `updated`：2026-08-31
  - `deadline`：2026-08-31
  - `time`：`"08:20"`（字符串，HH:MM 24h 制）

---

## 场景 2：`add --time + --end-time` 时间段

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "期末考试" --deadline 2026-07-03 --time 08:20 --end-time 09:50`

**Then**：
- 退出码：`0`
- YAML frontmatter 新增：
  - `time`：`"08:20"`
  - `end_time`：`"09:50"`

---

## 场景 3：`add --time + --duration` 时间段（持续时间）

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "复习" --deadline 2026-07-02 --time 19:00 --duration 1.5h`

**Then**：
- 退出码：`0`
- YAML frontmatter 新增：
  - `time`：`"19:00"`
  - `duration_min`：`90`（计算后存整数分钟；`1.5h` = 90 分钟）

---

## 场景 4：`add --duration` 支持多种格式

**Given**：
- 仓库已初始化

**When**：
- 运行以下 4 条命令：
  - `x todo add "A" --time 08:00 --duration 90`
  - `x todo add "B" --time 08:00 --duration 90m`
  - `x todo add "C" --time 08:00 --duration 1.5h`
  - `x todo add "D" --time 08:00 --duration 2h`

**Then**：
- 全部退出码 `0`
- 任务 A 的 `duration_min`：`90`（默认单位 = 分钟）
- 任务 B 的 `duration_min`：`90`（`m` 后缀 = 分钟）
- 任务 C 的 `duration_min`：`90`（`h` 后缀 = 小时，支持小数）
- 任务 D 的 `duration_min`：`120`（`h` 后缀 = 小时）

---

## 场景 5：`add --end-time` 与 `--duration` 互斥（错误路径）

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "考试" --deadline 2026-07-03 --time 08:20 --end-time 09:50 --duration 1.5h`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ --end-time 与 --duration 互斥，不能同时使用"`
- 不创建任何文件

---

## 场景 6：`--time` 不带 `--deadline`（仅时间，无日期）

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "每日站会" --time 09:00`

**Then**：
- 退出码：`0`
- YAML frontmatter：
  - `time`：`"09:00"`
  - **不写入** `deadline` 字段（与场景 1 不同；时间可独立于日期）
- list 显示时 `Deadline` 列 `-`，`Time` 列 `09:00`

---

## 场景 7：`update --time` 修改时间

**Given**：
- 任务 `t-fd316ca8` 存在，`time` = `"08:20"`

**When**：
- 运行 `x todo update t-fd316ca8 --time 09:00`

**Then**：
- 退出码：`0`
- YAML frontmatter：`time` 改为 `"09:00"`
- `updated` 字段更新为当前日期

---

## 场景 8：`update --time ""` 清空时间

**Given**：
- 任务 `t-fd316ca8` 存在，`time` = `"08:20"`

**When**：
- 运行 `x todo update t-fd316ca8 --time ""`

**Then**：
- 退出码：`0`
- YAML frontmatter 中 **删除** `time` 字段（不是空字符串，是完全省略）

---

## 场景 9：非法 `time` 格式（错误路径）

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "测试" --deadline 2026-08-31 --time 25:00`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ time 格式错误：25:00（必须为 HH:MM，HH 范围 00-23，MM 范围 00-59）"`
- 不创建任何文件

**When**：
- 运行 `x todo add "测试" --deadline 2026-08-31 --time 8:20`（缺前导 0）

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ time 格式错误：8:20（必须为 HH:MM，如 08:20）"`

**When**：
- 运行 `x todo add "测试" --deadline 2026-08-31 --time abc`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ time 格式错误：abc（必须为 HH:MM）"`

---

## 场景 10：非法 `duration` 格式（错误路径）

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "测试" --time 08:00 --duration abc`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ duration 格式错误：abc（合法：N / Nm / Nh，支持小数）"`

**When**：
- 运行 `x todo add "测试" --time 08:00 --duration -5m`（负数）

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ duration 必须为正数：-5m"`

---

## 场景 11：`list` 输出新增 `Time` 列

**Given**：
- 仓库有以下 3 个任务：
  - 任务 A：`time="08:20"`, `end_time="09:50"`
  - 任务 B：`time="19:00"`, `duration_min=90`
  - 任务 C：无 `time` 字段（v0.4 旧任务）

**When**：
- 运行 `x todo list`

**Then**：
- 表格列头包含：`ID / Name / Status / Priority / Deadline / Time`
- 任务 A 的 Time 列：`"08:20-09:50"`
- 任务 B 的 Time 列：`"19:00-20:30"`（计算 end_time = time + duration）
- 任务 C 的 Time 列：`-`

---

## 场景 12：向后兼容（v0.4 旧任务无 time 字段）

**Given**：
- 仓库有 v0.4 创建的任务 `t-old`，YAML frontmatter **无** `time` / `end_time` / `duration_min` 字段

**When**：
- 运行 `x todo list`

**Then**：
- 退出码：`0`
- 任务 `t-old` 正常列出，Time 列显示 `-`
- 运行 `x todo update t-old --priority high` 也不报错
- 验证：parser 遇到缺失字段时返回 None，formatter 渲染为 `-`

---

## 场景 13：`end_time` < `time` 校验（错误路径）

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "测试" --deadline 2026-07-03 --time 10:00 --end-time 09:00`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ end_time (09:00) 早于 time (10:00)"`
- 不创建任何文件

---

## 场景 14：`duration_min` 与 `time` 推导 `end_time`

**Given**：
- 任务 `t-x` 存在，`time="19:00"`, `duration_min=90`

**When**：
- 运行 `x todo list`

**Then**：
- Time 列显示 `"19:00-20:30"`（运行时计算，不存回 YAML）

---

*本文件由 v0.5 Phase A 任务生成（2026-06-30），覆盖 x todo add/update/list 的 time / end-time / duration 所有路径*