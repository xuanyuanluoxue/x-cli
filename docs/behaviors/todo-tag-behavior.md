# x todo tag 行为规格

> **对应命令**：`x todo tag <id> [<tag>...] [--remove] [--clear]`
> **命令参考**：[docs/commands.md §2.6](../../commands.md)
> **数据规范**：[../TODO-SPEC.md](../TODO-SPEC.md)
> **复用契约**：底层调用 `core.storage.update_task(id, fields={'tags': ...})`，跟 `x todo update --tags` 共用同一写入路径
>
> **覆盖范围**：
> - 添加 tag（单 / 多 / 已存在的幂等）
> - 移除 tag（`--remove` 单 / 多 / 不存在的幂等）
> - 清空 tags（`--clear`）
> - 互斥校验（`--remove` 与 `--clear`，添加模式与 `--clear`）
> - 错误路径（id 缺 / tag 缺 / 任务不存在 / 已归档）
> - **保留未知字段**（关键兼容性约束，如 `description` / `paused_at` / `pause_reason`）
> - 退出码约定（0 成功 / 2 参数错 / 3 不存在 / 4 已归档）

---

## 场景 1：添加单个 tag（最常见）

**Given**：
- 任务 `kemu1` 存在：`tags=[驾照, 暑假]`
- 当前日期：`2026-06-28`

**When**：
- 运行 `x todo tag kemu1 冲刺`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已添加 tag '冲刺'：科目一模拟考（ID: kemu1）"`
- frontmatter 变化：
  - `tags`：`[驾照, 暑假, 冲刺]`（追加，保留原顺序）
  - `updated`：2026-06-28
  - 其他字段（status / priority / deadline / name / created / folder）：**未变**
  - 未知字段（如 `description` / `paused_at`）：**保留**

---

## 场景 2：一次性添加多个 tag

**Given**：
- 任务 `kemu1` 存在：`tags=[驾照]`

**When**：
- 运行 `x todo tag kemu1 暑假 冲刺 高频错题`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已添加 3 个 tags：科目一模拟考（ID: kemu1）"`
- `tags`：`[驾照, 暑假, 冲刺, 高频错题]`（去重 + 保留原顺序，新加的追加在尾部）

---

## 场景 3：添加已存在的 tag（幂等）

**Given**：
- 任务 `kemu1` 存在：`tags=[驾照, 暑假]`

**When**：
- 运行 `x todo tag kemu1 驾照 冲刺`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已添加 1 个 tag：科目一模拟考（ID: kemu1）"`（**只报告实际新增的数量**）
- `tags`：`[驾照, 暑假, 冲刺]`（**不重复**）
- `updated`：2026-06-28

---

## 场景 4：移除单个 tag（`--remove`）

**Given**：
- 任务 `kemu1` 存在：`tags=[驾照, 暑假, 冲刺]`

**When**：
- 运行 `x todo tag --remove kemu1 暑假`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已移除 tag '暑假'：科目一模拟考（ID: kemu1）"`
- `tags`：`[驾照, 冲刺]`（**保持原剩余顺序**）
- `updated`：2026-06-28

---

## 场景 5：移除多个 tag

**Given**：
- 任务 `kemu1` 存在：`tags=[驾照, 暑假, 冲刺, 高频错题]`

**When**：
- 运行 `x todo tag --remove kemu1 暑假 冲刺`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已移除 2 个 tags：科目一模拟考（ID: kemu1）"`
- `tags`：`[驾照, 高频错题]`

---

## 场景 6：移除不存在的 tag（幂等）

**Given**：
- 任务 `kemu1` 存在：`tags=[驾照, 暑假]`

**When**：
- 运行 `x todo tag --remove kemu1 不存在 已移除`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已移除 0 个 tags：科目一模拟考（ID: kemu1）"`（**报告实际移除数量 0，不报错**）
- `tags`：`[驾照, 暑假]`（**未变**）
- `updated`：2026-06-28（**仍更新**，因为用户明确表达了"我想做 tag 操作"的意图）

---

## 场景 7：清空所有 tag（`--clear`）

**Given**：
- 任务 `kemu1` 存在：`tags=[驾照, 暑假, 冲刺]`

**When**：
- 运行 `x todo tag --clear kemu1`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已清空 tags：科目一模拟考（ID: kemu1）"`
- frontmatter 中 **`tags` 字段完全删除**（不写 `tags: []`，遵循与 `deadline: ""` 相同的"显式清空 = 删除字段"约定）
- `updated`：2026-06-28

---

## 场景 8：同时指定 `--remove` 和 `--clear`（互斥错误）

**Given**：
- 任务 `kemu1` 存在

**When**：
- 运行 `x todo tag --remove --clear kemu1 暑假`

**Then**：
- 退出码：`2`（参数错）
- 输出错误：`"❌ --remove 与 --clear 互斥，不能同时使用"`
- 不修改任何文件

---

## 场景 9：添加模式下同时指定 `--clear`（互斥错误）

**Given**：
- 任务 `kemu1` 存在

**When**：
- 运行 `x todo tag --clear kemu1 冲刺`

**Then**：
- 退出码：`2`
- 输出错误：`"❌ --clear 模式下不能指定 tag 参数（用 'x todo tag <id> <tag...>' 添加）"`
- 不修改任何文件

---

## 场景 10：任务 ID 不存在

**Given**：
- 仓库中不存在任务 `nonexistent-id`

**When**：
- 运行 `x todo tag nonexistent-id 冲刺`

**Then**：
- 退出码：`3`
- 输出错误：`"❌ 任务不存在：nonexistent-id"`
- 提示：`"💡 提示：运行 'x todo list' 查看现有任务 ID"`
- 不修改任何文件

---

## 场景 11：任务已归档

**Given**：
- 任务 `kemu1` 存在但**已归档**（`status: archived` 或 `archived: true`）

**When**：
- 运行 `x todo tag kemu1 冲刺`

**Then**：
- 退出码：`4`
- 输出错误：`"❌ 任务已归档：科目一模拟考（ID: kemu1）"`
- 提示：`"💡 提示：用 'x todo restore <id>' 还原后再操作"`
- 不修改任何文件

---

## 场景 12：缺任务 ID

**When**：
- 运行 `x todo tag 冲刺`（没给 id）

**Then**：
- 退出码：`2`
- 输出错误：`"❌ 缺少任务 ID（用法：x todo tag <id> <tag...>）"`
- 提示：`"💡 用法：x todo tag <id> <tag...> [--remove] [--clear]"`

---

## 场景 13：添加模式下缺 tag 参数

**Given**：
- 任务 `kemu1` 存在

**When**：
- 运行 `x todo tag kemu1`（没给 tag）

**Then**：
- 退出码：`2`
- 输出错误：`"❌ 至少指定一个 tag"`
- 提示：`"💡 用法：x todo tag <id> <tag...>  或  x todo tag --clear <id>"`

---

## 场景 14：移除模式下缺 tag 参数

**Given**：
- 任务 `kemu1` 存在

**When**：
- 运行 `x todo tag --remove kemu1`（没给 tag）

**Then**：
- 退出码：`2`
- 输出错误：`"❌ --remove 模式至少指定一个 tag"`
- 提示：`"💡 用法：x todo tag --remove <id> <tag...>"`

---

## 场景 15：保留未知字段（兼容性约束）

**Given**：
- 任务 `kemu1` 存在，frontmatter 含未知字段：
  - `description`：用户写的长文
  - `paused_at`：2026-05-10（外部工具写入）
  - `pause_reason`：用户主动暂停

**When**：
- 运行 `x todo tag kemu1 冲刺`

**Then**：
- 退出码：`0`
- 写入后的 frontmatter：
  - `description`：**保留**（值不变）
  - `paused_at`：**保留**
  - `pause_reason`：**保留**
  - `tags`：`[<原 tags>, 冲刺]`
  - `updated`：2026-06-28
  - 注释 / 空行 / 引号风格 / key 顺序：保留手写 parser 的 round-trip 保证

---

## 场景 16：tag 含特殊字符（边界）

**Given**：
- 任务 `kemu1` 存在：`tags=[]`

**When**：
- 运行 `x todo tag kemu1 "含 空格" "含/斜杠"`

**Then**：
- 退出码：`0`
- `tags`：`[含 空格, 含/斜杠]`（**不**做 slug 化或转义，按用户字面存）
- 后续 `x todo list --tag "含 空格"` 能精确匹配

---

## 场景 17：重复 tag 在一次命令中（去重）

**Given**：
- 任务 `kemu1` 存在：`tags=[驾照]`

**When**：
- 运行 `x todo tag kemu1 冲刺 冲刺 暑假 冲刺`

**Then**：
- 退出码：`0`
- `tags`：`[驾照, 冲刺, 暑假]`（**去重**，只加 1 份"冲刺"）
- 输出：`"✅ 已添加 2 个 tags：..."`

---

## 设计决策摘要

| 决策 | 选择 | 理由 |
|---|---|---|
| 互斥标志校验 | `--remove` 与 `--clear` 互斥；`--clear` 不能带 tag 参数 | 防止用户歧义意图 |
| 已存在 tag 添加 | 幂等，不报错 | 与 `update --tags` 行为一致；用户可能重复调用 |
| 不存在 tag 移除 | 幂等，报告"0 移除" | 同上 |
| `--clear` 写入 | 完全删除 `tags` 字段 | 跟 `update --deadline ""` 同约定 |
| tag 字符串 | 字面存，不 slug 化 | 跟 `update --tags` 行为一致 |
| 重复输入去重 | 单次命令内去重 | 防止用户误操作 |
| 已归档 | 拒绝（exit 4） | 跟 `update` 一致，不允许改归档任务 |
| 未知字段 | 保留 | 关键兼容性约束，手写 parser round-trip 保证 |

---

*Last updated: 2026-06-28*
