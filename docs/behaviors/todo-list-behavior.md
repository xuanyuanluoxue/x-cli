# x todo list 行为规格

> **对应命令**：`x todo list [选项]`
> **命令参考**：[docs/commands.md §2.2](../../commands.md)
> **数据规范**：[../TODO-SPEC.md](../TODO-SPEC.md)
>
> **覆盖范围**：
> - 无过滤（默认只列未归档）
> - `--status` 过滤
> - `--priority` 过滤
> - `--tag` 过滤
> - `--all`（含归档）
> - 空仓库 / 无匹配（边界）

---

## 场景 1：默认列出所有未归档任务

**Given**：
- 仓库 `<xcli_todo_dir>/` 已初始化
- 存在 3 个未归档任务：
  - `kemu1`（科目一模拟考，pending / high）
  - `zizhushixi`（自主实习，in_progress / medium）
  - `laodongjiaoyu3`（劳动教育III，blocked / low）
- 存在 1 个已归档任务：`20260521-xiangjifanmai`（相机贩卖业务，archived）

**When**：
- 运行 `x todo list`

**Then**：
- 退出码：`0`
- 表格中只出现 3 行：`kemu1` / `zizhushixi` / `laodongjiaoyu3`
- `20260521-xiangjifanmai` **不出现**（默认隐藏归档）
- 表头列：`ID / Name / Status / Priority / Deadline`
- 输出顺序：按 `deadline` 升序，无截止日的任务排在末尾

---

## 场景 2：按 `--status` 过滤

**Given**：
- 仓库存在以下任务：
  - `kemu1`：pending
  - `zizhushixi`：in_progress
  - `laodongjiaoyu3`：blocked

**When**：
- 运行 `x todo list --status in_progress`

**Then**：
- 退出码：`0`
- 只显示 `zizhushixi` 一行
- `kemu1` / `laodongjiaoyu3` 不出现
- 输出列同场景 1

---

## 场景 3：按 `--priority` 过滤

**Given**：
- 仓库存在以下任务：
  - `kemu1`：priority=high
  - `zizhushixi`：priority=medium
  - `laodongjiaoyu3`：priority=low

**When**：
- 运行 `x todo list --priority high`

**Then**：
- 退出码：`0`
- 只显示 `kemu1` 一行
- `zizhushixi` / `laodongjiaoyu3` 不出现

---

## 场景 4：按 `--tag` 过滤

**Given**：
- 仓库存在以下任务：
  - `kemu1`：tags=`[驾照, 暑假]`
  - `zizhushixi`：tags=`[实习]`
  - `laodongjiaoyu3`：tags=`[学校]`

**When**：
- 运行 `x todo list --tag 暑假`

**Then**：
- 退出码：`0`
- 只显示 `kemu1` 一行
- `zizhushixi` / `laodongjiaoyu3` 不出现

---

## 场景 5：`--all` 显示全部（含归档）

**Given**：
- 仓库存在 3 个未归档任务（kemu1 / zizhushixi / laodongjiaoyu3）
- 仓库存在 1 个归档任务：`20260521-xiangjifanmai`

**When**：
- 运行 `x todo list --all`

**Then**：
- 退出码：`0`
- 表格中显示 4 行（含归档任务）
- 归档任务的 Status 列显示 `archived`，并附 `reason`（如 `done` / `cancelled`）
- 排序优先级：未归档在前，归档在后；同类内按 `deadline` 升序

---

## 场景 6：空仓库（无任务）

**Given**：
- 仓库 `<xcli_todo_dir>/` 已初始化
- `任务/` 子目录为空
- `归档/` 子目录为空

**When**：
- 运行 `x todo list`

**Then**：
- 退出码：`0`
- 输出提示信息：`"📭 没有任务"`
- 不打印空表格
- 不报错（exit code 仍为 0）

---

## 场景 7：多过滤条件组合（边界）

**Given**：
- 仓库存在以下任务：
  - `kemu1`：status=pending / priority=high / tags=`[驾照, 暑假]`
  - `zizhushixi`：status=in_progress / priority=medium / tags=`[实习]`

**When**：
- 运行 `x todo list --status pending --priority high --tag 暑假`

**Then**：
- 退出码：`0`
- 只显示 `kemu1` 一行
- 多个过滤条件为 **AND** 关系（同时满足才显示）

---

## 场景 8：过滤值无效（错误路径）

**Given**：
- 仓库存在任意任务

**When**：
- 运行 `x todo list --status invalid_status`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ 无效的 status 值：invalid_status（合法值：pending / in_progress / blocked / waiting / archived）"`
- 不打印任何表格

---

*本文件由 bdd-specs 任务生成（2026-06-21），覆盖 x todo list 命令的所有成功/边界/错误路径*
