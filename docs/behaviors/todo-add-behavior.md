# x todo add 行为规格

> **对应命令**：`x todo add <名称> [选项]`
> **命令参考**：[docs/commands.md §2.3](../../commands.md)
> **数据规范**：[~/.xavier/TODO/00-TODO-SPEC.md](../../../_TODO-SPEC.md)（v1.3）
> **ID 生成规则**：从任务名生成 kebab-case slug（如"科目一模拟考" → `kemu1-moni-kao`），冲突时自动追加数字后缀
>
> **覆盖范围**：
> - 最简形式（只给名称）
> - 完整参数（--priority + --deadline + --tags）
> - 默认值（priority=medium）
> - 错误路径（缺名称 / 重复 / 非法值 / 日期格式）

---

## 场景 1：最简形式（只给名称）

**Given**：
- 仓库 `~/.xavier/TODO/` 已初始化
- `任务/` 子目录为空（或无重复名任务）
- 当前日期：`2026-06-21`

**When**：
- 运行 `x todo add "测试任务A"`

**Then**：
- 退出码：`0`
- 输出：`"✅ 任务已创建：测试任务A（ID: <自动生成的 kebab-case id>）"`
- 文件系统：创建 `~/.xavier/TODO/任务/测试任务A/TODO.md`
- YAML frontmatter：
  - `id`：自动生成（kebab-case + 可选数字后缀）
  - `name`：测试任务A
  - `status`：pending（默认值）
  - `priority`：medium（默认值）
  - `created`：2026-06-21
  - `updated`：2026-06-21
  - `folder`：任务/测试任务A
  - `deadline` 字段：**不写入**（默认无截止日）

---

## 场景 2：完整参数（--priority + --deadline + --tags）

**Given**：
- 仓库 `~/.xavier/TODO/` 已初始化
- 当前日期：`2026-06-21`

**When**：
- 运行 `x todo add "科目一模拟考" --priority high --deadline 2026-08-31 --tags 驾照,暑假`

**Then**：
- 退出码：`0`
- 输出：`"✅ 任务已创建：科目一模拟考（ID: kemu1-moni-kao）"`
- 文件系统：创建 `~/.xavier/TODO/任务/科目一模拟考/TODO.md`
- YAML frontmatter：
  - `id`：kemu1-moni-kao
  - `name`：科目一模拟考
  - `status`：pending
  - `priority`：high
  - `created`：2026-06-21
  - `updated`：2026-06-21
  - `deadline`：2026-08-31
  - `tags`：`[驾照, 暑假]`
  - `folder`：任务/科目一模拟考

---

## 场景 3：重复任务名（错误路径）

**Given**：
- 仓库已存在任务 `~/.xavier/TODO/任务/科目一/TODO.md`（id=`kemu1`）

**When**：
- 运行 `x todo add "科目一"`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ 任务已存在：科目一（ID: kemu1，位于 任务/科目一）"`
- 不创建新文件夹
- 不修改任何现有文件

---

## 场景 4：缺必填参数 `名称`（错误路径）

**Given**：
- 仓库 `~/.xavier/TODO/` 已初始化

**When**：
- 运行 `x todo add`（不带任何位置参数）

**Then**：
- 退出码：非 0（如 `2`）
- 输出 argparse 标准错误：`"the following arguments are required: 名称"`
- 不创建任何文件

---

## 场景 5：非法 priority 值（错误路径）

**Given**：
- 仓库 `~/.xavier/TODO/` 已初始化

**When**：
- 运行 `x todo add "新任务" --priority urgent`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ 无效的 priority 值：urgent（合法值：high / medium / low）"`
- 不创建任何文件

---

## 场景 6：日期格式错误（错误路径）

**Given**：
- 仓库 `~/.xavier/TODO/` 已初始化

**When**：
- 运行 `x todo add "新任务" --deadline 2026/08/31`

**Then**：
- 退出码：非 0（如 `2`）
- 输出错误：`"❌ deadline 格式错误：2026/08/31（必须为 YYYY-MM-DD）"`
- 不创建任何文件

---

## 场景 7：未指定 `--tags` 时 frontmatter 不写入 tags 字段

**Given**：
- 仓库 `~/.xavier/TODO/` 已初始化

**When**：
- 运行 `x todo add "无标签任务"`

**Then**：
- 退出码：`0`
- 创建 `~/.xavier/TODO/任务/无标签任务/TODO.md`
- YAML frontmatter 中 **不存在** `tags` 字段（不是空数组，是完全省略）

---

## 场景 8：未知 frontmatter 字段必须保留（兼容性）

**Given**：
- 仓库 `~/.xavier/TODO/` 已初始化
- 用户在任务文件夹里手动加了一些 x-cli 不识别的字段（如 `description: "..."`、`paused_at: 2026-06-13`）

**When**：
- 运行 `x todo add "新任务"`

**Then**：
- 退出码：`0`
- 新任务的 `TODO.md` **不写入**任何未在前缀参数中出现的字段（因为是新增）
- 同时：未来 `x todo update` 不得删除任何用户自定义字段（见 `todo-update-behavior.md` 场景 6）

---

*本文件由 bdd-specs 任务生成（2026-06-21），覆盖 x todo add 命令的所有成功/边界/错误路径*
