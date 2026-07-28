# x todo 自动归档 行为规格

> **对应命令**：`x todo list` / `x todo stats` / `x todo search` 的「自动归档」副作用
> **命令参考**：[docs/commands.md §2.2 / §2.6](../../commands.md)
> **数据规范**：[../TODO-SPEC.md](../TODO-SPEC.md)
>
> **覆盖范围**：
> - 启用方式（YAML `todo.auto_archive` 或环境变量 `XCLI_TODO_AUTO_ARCHIVE`）
> - 触发命令（list / stats / search）
> - 逾期判定（deadline < today() 且 status ∈ active）
> - 归档副作用（`reason=expired` + stdout 顶部提示）
> - 默认关闭（不破坏现有用户）

---

## 设计要点（实现前必读）

| 项 | 值 | 说明 |
|----|----|------|
| 默认行为 | **关闭** | 现有用户 0 改动 |
| 启用方式 A | YAML 嵌套字段 `todo.auto_archive: true` | 写到 `<xcli_data_dir>/config.yaml` |
| 启用方式 B | 环境变量 `XCLI_TODO_AUTO_ARCHIVE=1` | 临时启用（如沙盒 / 调试） |
| 优先级 | YAML < 环境变量 | 与现有 `core/config.py` 一致（env 优先于文件） |
| 触发命令 | `list` / `stats` / `search` | 查询类命令进入时**第一步**检查 |
| 不触发命令 | `add` / `update` / `archive` / `restore` / `init` / `import` / `done` | 写命令 / 显式归档不改 |
| 逾期判定 | `deadline < today()` 且 `status ∈ {pending, in_progress, blocked, waiting}` | status=archived 跳过（已被归档） |
| 归档方式 | 复用 `TaskStore.archive_task(task_id, reason="expired")` | reason 固定为 expired（**不是**用户主动删） |
| 提示位置 | stdout **顶部**（在 list/stats/search 正常输出前） | 单行摘要：`⏰ 自动归档 N 个逾期任务：id1 / id2 / ...` |
| 无任务归档 | 不打印提示 | 0 个 = 静默，不污染输出 |

---

## 场景 1：YAML 启用 + list 触发 + 有逾期任务 → 自动归档 + 顶部提示

**Given**：
- `<xcli_data_dir>/config.yaml` 内容：
  ```yaml
  todo:
    auto_archive: true
  ```
- 仓库 `<xcli_todo_dir>/` 存在以下任务：
  - `kemu1`：status=pending / priority=high / **deadline=2026-05-01**（已逾期）
  - `zizhushixi`：status=in_progress / priority=medium / deadline=2026-08-31（未到期）
- 当前日期：测试运行时 `date.today()`（2026-06-26 编写；`deadline=2026-05-01` 始终为过去日期）

**When**：
- 运行 `x todo list`

**Then**：
- 退出码：`0`
- **stdout 顶部**打印：
  ```
  ⏰ 自动归档 1 个逾期任务：kemu1
  ```
- 紧接其后打印 list 表格（**只含** `zizhushixi`，`kemu1` 不再出现）
- **物理移动**：`任务/科目一/` → `归档/20260626-科目一/`（reason=expired）
- `归档/<date>-科目一/TODO.md` 的 frontmatter `reason: expired`
- 退出码不受影响（仍是 0）

---

## 场景 2：YAML 启用 + list 触发 + 无逾期任务 → 不归档，无提示

**Given**：
- `<xcli_data_dir>/config.yaml` 含 `todo.auto_archive: true`
- 仓库任务：
  - `kemu1`：deadline=2026-08-31（未到期）
  - `zizhushixi`：deadline=None（无 deadline，**不**算逾期）

**When**：
- 运行 `x todo list`

**Then**：
- 退出码：`0`
- stdout **没有** `⏰ 自动归档` 提示行（0 个就不打）
- stdout 输出 list 表格（含 `kemu1` 和 `zizhushixi`）
- 任务文件位置不变（没有发生归档）

---

## 场景 3：禁用（默认）+ list → 不归档，无提示（关键 — 不能破坏现有用户）

**Given**：
- `<xcli_data_dir>/config.yaml` **不存在**（或存在但**没有** `todo.auto_archive` 字段）
- 环境变量 `XCLI_TODO_AUTO_ARCHIVE` **未设置**
- 仓库任务：
  - `kemu1`：deadline=2025-12-31（早就过期）

**When**：
- 运行 `x todo list`

**Then**：
- 退出码：`0`
- stdout **没有** `⏰ 自动归档` 提示
- stdout 输出 list 表格（含 `kemu1`）
- `kemu1` **未被归档**（任务文件位置不变；status 仍为 pending）

---

## 场景 4：YAML 启用 + stats 触发 → 归档后统计正确（archived 数 +N）

**Given**：
- `<xcli_data_dir>/config.yaml` 含 `todo.auto_archive: true`
- 仓库任务（stats 前）：
  - `kemu1`：status=pending / deadline=2026-05-01（已逾期）
  - `kemu2`：status=pending / deadline=2026-04-01（已逾期）
  - `zizhushixi`：status=in_progress / deadline=2026-08-31

**When**：
- 运行 `x todo stats`

**Then**：
- 退出码：`0`
- stdout **顶部**打印：
  ```
  ⏰ 自动归档 2 个逾期任务：kemu1 / kemu2
  ```
- 紧接其后打印 stats 输出（归档后）：
  - `archived` 数 = 之前 +2
  - `pending` 数 = 之前 −2
  - 优先级分布同步更新
- 物理文件：`kemu1` 和 `kemu2` 都被移动到 `归档/<date>-<name>/`

---

## 场景 5：YAML 启用 + search 触发 → 搜索结果不含已归档的逾期任务

**Given**：
- `<xcli_data_dir>/config.yaml` 含 `todo.auto_archive: true`
- 仓库任务：
  - `kemu1`：name="科目一模拟考" / deadline=2026-05-01（已逾期）
  - `kemu2`：name="科目二模拟考" / deadline=2026-08-31（未到期）

**When**：
- 运行 `x todo search 模拟考`

**Then**：
- 退出码：`0`
- stdout **顶部**打印：
  ```
  ⏰ 自动归档 1 个逾期任务：kemu1
  ```
- search 结果**只**含 `kemu2`（kemu1 已归档，不再出现在 active 搜索结果里）
- `kemu1` 在 `归档/<date>-科目一模拟考/` 下，frontmatter reason=expired

---

## 场景 6：环境变量 `XCLI_TODO_AUTO_ARCHIVE=1` 启用（无配置文件字段）

**Given**：
- `<xcli_data_dir>/config.yaml` **不存在**（或不含 `todo.auto_archive` 字段）
- 环境变量 `XCLI_TODO_AUTO_ARCHIVE=1`（任何非空、非 0、非 false 都算启用）
- 仓库任务：
  - `kemu1`：deadline=2026-05-01（已逾期）

**When**：
- 运行 `x todo list`（环境变量 XCLI_TODO_AUTO_ARCHIVE=1 已在 process 上下文里）

**Then**：
- 退出码：`0`
- stdout **顶部**打印：`⏰ 自动归档 1 个逾期任务：kemu1`
- 任务被归档（reason=expired）
- **同时** YAML 配置文件**没有**写入（仅环境变量启用）— 说明 env 优先级最高

---

## 边界与反向 case（实现时一并验证，不写单独测试）

| 情况 | 期望行为 |
|------|----------|
| 任务 deadline=今天（deadline == today） | **不**归档（只严格小于才算逾期） |
| 任务 deadline=None | **不**归档（无 deadline 永远不逾期） |
| 任务 status=archived | **不**二次归档 |
| 任务 deadline=2025-13-99（非法日期） | 跳过（`_parse_date` 返回 None → 当作无 deadline） |
| 多个 query 命令连续触发 | 第二次触发时已无逾期任务 → 不重复打提示 |
| 同一任务的 deadline 已过期但用户在前一秒用 `update --deadline 2030-01-01` 改了 | 不归档（update 不触发自动归档；后续 list 才可能触发） |
| 同时设置 env 和 YAML，且两者都启用 | 按 OR 关系（任一启用就算启用） |
| 同时设置 env 和 YAML，env=1 YAML=false | 启用（env 优先） |

---

*本文件由 todo-auto-archive 任务生成（2026-06-26），覆盖 `x todo list` / `x todo stats` / `x todo search` 的自动归档副作用的所有成功 / 边界 / 错误路径*