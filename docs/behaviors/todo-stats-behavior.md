# x todo stats 行为规格

> **对应命令**：`x todo stats`
> **命令参考**：[docs/commands.md §2.6](../../commands.md)
> **数据规范**：[~/.xavier/TODO/00-TODO-SPEC.md §4](../../_TODO-SPEC.md)（v1.3，总索引格式）
>
> **覆盖范围**：
> - 常规统计（状态分布 + 优先级分布 + 即将到期）
> - 空仓库
> - 仅归档任务
> - 即将到期窗口（≤ 7 天）
> - 高优先级任务占比
> - 输出格式稳定性

---

## 场景 1：常规统计（典型场景）

**Given**：
- 仓库 `~/.xavier/TODO/` 存在以下任务：
  - 状态分布：
    - `pending`：3（kemu1、zizhushixi、laodongjiaoyu3）
    - `in_progress`：5
    - `blocked`：1
    - `waiting`：0
    - `archived`：2
  - 优先级分布：
    - `high`：4
    - `medium`：6
    - `low`：1
  - 截止日期 ≤ 2026-06-28（7 天内）的任务：1 个（kemu1，deadline=2026-08-31 **不计入**；这里改：pending/in_progress 中 deadline=2026-06-25 的 1 个）

**When**：
- 运行 `x todo stats`

**Then**：
- 退出码：`0`
- 输出包含：
  ```
  📊 TODO 统计信息

  总任务数：11
  - pending：3
  - in_progress：5
  - blocked：1
  - waiting：0
  - archived：2

  优先级分布：
  - high：4
  - medium：6
  - low：1

  即将到期（7 天内）：1
  ```
- **统计口径**：
  - "总任务数"= 5 类状态合计 = 11
  - "即将到期"= `pending` + `in_progress` + `blocked` + `waiting` 中 deadline ≤ today+7 的数量（**不含 archived**）

---

## 场景 2：空仓库

**Given**：
- 仓库 `~/.xavier/TODO/` 已初始化
- `任务/` 和 `归档/` 均为空

**When**：
- 运行 `x todo stats`

**Then**：
- 退出码：`0`
- 输出：
  ```
  📊 TODO 统计信息

  总任务数：0

  优先级分布：
  - high：0
  - medium：0
  - low：0

  即将到期（7 天内）：0
  ```
- 不打印 `pending / in_progress / ...` 五行明细（0 时可省略）

---

## 场景 3：仅归档任务

**Given**：
- `任务/` 为空
- `归档/` 含有 5 个任务（均为 `status=archived`）

**When**：
- 运行 `x todo stats`

**Then**：
- 退出码：`0`
- 输出 `总任务数：5`
- 状态分布仅显示 `archived：5`（或保留全部 5 类，pending/in_progress/blocked/waiting 全部为 0）
- "即将到期"= 0（**不计归档任务的 deadline**）

---

## 场景 4：即将到期窗口边界（≤ 7 天）

**Given**：
- 任务 `t1`：`deadline=2026-06-21`（今天，**计入**）
- 任务 `t2`：`deadline=2026-06-28`（7 天后，**计入**）
- 任务 `t3`：`deadline=2026-06-29`（8 天后，**不计入**）
- 任务 `t4`：`deadline=2026-06-22`（明天，**计入**）
- 当前日期：`2026-06-21`

**When**：
- 运行 `x todo stats`

**Then**：
- 退出码：`0`
- "即将到期（7 天内）"= 3（t1 + t2 + t4，t3 不计入）

---

## 场景 5：高优先级任务单独提示

**Given**：
- 仓库中存在 4 个 `priority=high` 任务
- 全部为 `pending` 或 `in_progress`

**When**：
- 运行 `x todo stats`

**Then**：
- 退出码：`0`
- 输出末尾追加：`🔥 高优先级任务：4（pending: 2 / in_progress: 2）`
- 该行为是 v1.x 增强提示，非强约束（未来可调整）

---

## 场景 6：未知 frontmatter 字段不影响统计

**Given**：
- 任务 `kemu1` 存在但 frontmatter 含未知字段 `description / paused_at / pause_reason`

**When**：
- 运行 `x todo stats`

**Then**：
- 退出码：`0`
- 未知字段**不影响任何计数**（即 kemu1 只算 1 次，无论有多少非标准字段）

---

## 场景 7：死链 / YAML 损坏（错误路径）

**Given**：
- 仓库中存在一个损坏的 `TODO.md`（YAML 解析失败）

**When**：
- 运行 `x todo stats`

**Then**：
- 退出码：非 0（如 `5`）
- 输出错误：`"❌ 解析任务失败：任务/科目一/TODO.md（YAML 格式错误：...）"`
- 列出所有损坏文件路径
- 已成功解析的任务仍然参与计数（best-effort 统计）

---

*本文件由 bdd-specs 任务生成（2026-06-21），覆盖 x todo stats 命令的所有成功/边界/错误路径*
