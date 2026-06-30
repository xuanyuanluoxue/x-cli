# x todo 重复任务 行为规格（v0.5 Phase D）

> **对应命令**：`x todo add / repeat-fire`
> **新增 flag**：`--repeat <规则>`（daily / weekly / weekdays / monthly / 标准 cron）
> **新增子命令**：`x todo repeat-fire <id>`（显式触发下一次实例）
> **数据规范**：`repeat` 字段（dict 形式 `{kind: "daily"}` 或 `{cron: "0 8 * * 1-5"}`）
> **来源**：[PLAN-v0.5.md §2.3.1](../../../PLAN-v0.5.md)
>
> **v0.5 范围**：
> - ✅ `--repeat` 字段写入（5 种语法）
> - ✅ `repeat-fire` 显式触发（用户可控）
> - ❌ archive done 时**不**自动触发下一次（避免误触）
> - ❌ **不做**循环依赖检测 / 不做超期补触发
>
> **覆盖范围**：
> - add --repeat 五种语法
> - repeat-fire 创建新实例 + seq 命名
> - 错误路径（非法 cron / 非法 kind）
> - 重复任务完成后的状态

---

## 场景 1：`add --repeat daily`

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo add "吃药" --repeat daily`

**Then**：
- 退出码：`0`
- YAML frontmatter `repeat`：`{kind: "daily"}`

---

## 场景 2：`add --repeat weekly`

**When**：
- 运行 `x todo add "周会" --repeat weekly`

**Then**：
- 退出码：`0`
- YAML frontmatter `repeat`：`{kind: "weekly"}`

---

## 场景 3：`add --repeat weekdays`

**When**：
- 运行 `x todo add "打卡" --repeat weekdays`

**Then**：
- 退出码：`0`
- YAML frontmatter `repeat`：`{kind: "weekdays"}`

---

## 场景 4：`add --repeat monthly`

**When**：
- 运行 `x todo add "月报" --repeat monthly`

**Then**：
- 退出码：`0`
- YAML frontmatter `repeat`：`{kind: "monthly"}`

---

## 场景 5：`add --repeat "<cron>"` 标准 5 字段 cron

**When**：
- 运行 `x todo add "备份" --repeat "0 8 * * 1-5"`（工作日早 8 点）

**Then**：
- 退出码：`0`
- YAML frontmatter `repeat`：`{cron: "0 8 * * 1-5"}`

---

## 场景 6：非法 cron 格式（错误路径）

**When**：
- 运行 `x todo add "test" --repeat "not a cron"`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ repeat 格式错误：not a cron（支持：daily / weekly / weekdays / monthly / 标准 5 字段 cron）"`
- 不创建任何文件

---

## 场景 7：非法 kind 字符串（错误路径）

**When**：
- 运行 `x todo add "test" --repeat yearly`（不支持的 kind）

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ repeat 格式错误：yearly（支持：daily / weekly / weekdays / monthly / 标准 5 字段 cron）"`

---

## 场景 8：`repeat-fire` 显式触发创建新实例

**Given**：
- 任务 `t-zhihui`：`name="周会"`, `repeat={kind: "weekly"}`

**When**：
- 运行 `x todo repeat-fire t-zhihui`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已创建下一次实例：t-zhihui-001"`
- 文件系统：
  - `任务/周会/TODO.md` 仍在（**原任务不删除**，作为锚点）
  - 新建 `任务/周会-001/TODO.md`，id=`t-zhihui-001`
- 新实例的 `repeat` 字段与原任务相同

---

## 场景 9：`repeat-fire` seq 自增

**Given**：
- `t-zhihui`（原）+ `t-zhihui-001`（已存在）

**When**：
- 运行 `x todo repeat-fire t-zhihui`

**Then**：
- 新实例 ID：`t-zhihui-002`（seq 取 max + 1）
- 文件夹名：`周会-002`

---

## 场景 10：`repeat-fire` 非重复任务（错误路径）

**Given**：
- 任务 `t-once`，无 `repeat` 字段

**When**：
- 运行 `x todo repeat-fire t-once`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ 任务没有 repeat 字段：t-once"`

---

## 场景 11：`repeat-fire` 不存在任务（错误路径）

**When**：
- 运行 `x todo repeat-fire t-nope`

**Then**：
- 退出码：非 0（如 `3`）
- 输出错误：`"❌ 任务不存在：t-nope"`

---

## 场景 12：`archive --reason done` 不自动触发 repeat-fire

**Given**：
- 任务 `t-zhihui-001`：repeat 任务，前一实例

**When**：
- 运行 `x todo archive t-zhihui-001 --reason done`

**Then**：
- 退出码：`0`
- `t-zhihui-002` **不**被自动创建（v0.5 显式触发，不自动）

---

## 场景 13：cron 6 字段（带秒）拒绝（v0.5 不支持秒级）

**When**：
- 运行 `x todo add "test" --repeat "0 0 8 * * *"`（6 字段）

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ repeat cron 必须为 5 字段（不支持秒级）"`

---

*本文件由 v0.5 Phase D 任务生成（2026-06-30），覆盖重复任务字段 + 显式 repeat-fire 触发，不含自动 archive 触发*