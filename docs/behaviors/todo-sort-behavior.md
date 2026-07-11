# x todo 排序 + urgent 高亮 行为规格（v0.5 Phase D）

> **对应命令**：`x todo list`、`x todo add / update --priority`
> **新增 flag**：`--sort priority | deadline | created | time`（默认 priority）
> **新增优先级**：`urgent`（比 high 更高，ANSI red 高亮）
> **数据规范**：Priority 枚举新增 `URGENT = "urgent"`
> **来源**：[PLAN-v0.5.md §2.3.3 + §3.2 + §6.5](../../../PLAN-v0.5.md)
>
> **v0.5 范围**：
> - ✅ list 4 种 sort 模式
> - ✅ urgent 优先级 + ANSI red 高亮（终端能力自动检测）
> - ✅ `--no-color` flag 全局禁用颜色
> - ⚠️ Windows cmd（不支持 ANSI）→ 自动启用 VT100 mode（ctypes），失败回退无颜色
>
> **覆盖范围**：
> - sort priority（默认，urgent > high > medium > low）
> - sort deadline / created / time
> - urgent add / update
> - 终端颜色自动检测（Linux/macOS → ANSI / Windows Terminal → ANSI / Windows cmd → 尝试 VT100）
> - --no-color flag

---

## 场景 1：`list --sort priority`（默认）

**Given**：
- 任务 A：priority=low
- 任务 B：priority=urgent
- 任务 C：priority=medium

**When**：
- 运行 `x todo list`（不传 --sort）或 `x todo list --sort priority`

**Then**：
- 退出码：`0`
- 输出顺序：B（urgent）→ C（medium）→ A（low）

---

## 场景 2：`list --sort deadline`

**Given**：
- 任务 A：deadline=2026-08-01
- 任务 B：deadline=2026-07-01
- 任务 C：无 deadline

**When**：
- 运行 `x todo list --sort deadline`

**Then**：
- 退出码：`0`
- 输出顺序：B（07-01）→ A（08-01）→ C（None，末尾）

---

## 场景 3：`list --sort created`

**Given**：
- 任务 A：创建最早
- 任务 B：创建最晚
- 任务 C：创建中间

**When**：
- 运行 `x todo list --sort created`

**Then**：
- 输出顺序：A → C → B（按 created 升序）

---

## 场景 4：`list --sort time`

**Given**：
- 任务 A：time=10:00
- 任务 B：time=08:00
- 任务 C：无 time

**When**：
- 运行 `x todo list --sort time`

**Then**：
- 输出顺序：B（08:00）→ A（10:00）→ C（无 time，按 deadline fallback，末尾）

---

## 场景 5：`--sort` 非法值（错误路径）

**When**：
- 运行 `x todo list --sort invalid`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ 无效的 sort 值：invalid（合法：priority / deadline / created / time）"`

---

## 场景 6：`add --priority urgent`

**When**：
- 运行 `x todo add "明天考试" --priority urgent`

**Then**：
- 退出码：`0`
- YAML frontmatter `priority`：`"urgent"`
- 图标：`🔥🔥`（双火焰）

---

## 场景 7：`update --priority urgent`

**Given**：
- 任务 `t-x`：priority=high

**When**：
- 运行 `x todo update t-x --priority urgent`

**Then**：
- 退出码：`0`
- YAML frontmatter `priority`：`"urgent"`

---

## 场景 8：`urgent` 排序优先于 `high`

**Given**：
- 任务 A：priority=high
- 任务 B：priority=urgent
- 任务 C：priority=low

**When**：
- 运行 `x todo list --sort priority`

**Then**：
- 输出顺序：B（urgent）→ A（high）→ C（low）

---

## 场景 9：`urgent` 在 ANSI-capable 终端显示红色

**Given**：
- 终端支持 ANSI（Linux/macOS terminal / Windows Terminal / VS Code）
- 任务 `t-urg`：priority=urgent

**When**：
- 运行 `x todo list`

**Then**：
- 任务行包含 ANSI 转义序列：`\x1b[31m`（红色）

---

## 场景 10：`urgent` 在不支持 ANSI 的终端无颜色

**Given**：
- 终端不支持 ANSI（Windows cmd，未启用 VT100）
- 或环境变量 `NO_COLOR` 存在
- 任务 `t-urg`：priority=urgent

**When**：
- 运行 `x todo list`

**Then**：
- 任务行**不**含 ANSI 转义序列（纯文本）
- 优先级图标仍为 `🔥🔥`

---

## 场景 11：`--no-color` 全局禁用

**Given**：
- 终端支持 ANSI
- 任务 `t-urg`：priority=urgent

**When**：
- 运行 `x todo list --no-color`

**Then**：
- 任务行**不**含 ANSI 转义序列

---

## 场景 12：`priority urgent` 非法值（错误路径）

**When**：
- 运行 `x todo add "test" --priority critical`（不支持）

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ 无效的 priority 值：critical（合法值：urgent / high / medium / low）"`

---

## 场景 13：`--no-color` 与 `--sort` 组合

**When**：
- 运行 `x todo list --sort deadline --no-color`

**Then**：
- 退出码：`0`
- 输出按 deadline 排序，**不**含 ANSI 颜色（即使终端支持）

---

*本文件由 v0.5 Phase D 任务生成（2026-06-30），覆盖排序 + urgent 优先级 + ANSI 颜色*