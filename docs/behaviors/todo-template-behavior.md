# x todo 任务模板 行为规格（v0.5 Phase E）

> **对应命令**：`x todo template create / list / remove`、`x todo add --template`
> **新增子命令**：`x todo template <action>`
> **存储**：`templates/<name>.yaml` 存于 `<xcli_data_dir>/templates/`
> **来源**：[PLAN-v0.5.md §2.4.1](../../../PLAN-v0.5.md)
>
> **覆盖范围**：
> - template create / list / remove
> - add --template 使用模板展开为父任务 + N 个子任务
> - 模板步骤命名去重（重复名自动加 -001/-002）
> - 错误路径（模板不存在 / 模板名冲突 / 模板为空）

---

## 场景 1：template create 含 steps

**Given**：
- 仓库已初始化

**When**：
- 运行 `x todo template create 退宿流程 --steps "清扫宿舍,清点物品,宿管核验"`

**Then**：
- 退出码：`0`
- 输出：`"✅ 模板已创建：退宿流程（3 步）"`
- 文件系统：`<xcli_data_dir>/templates/退宿流程.yaml` 存在

---

## 场景 2：template list 展示所有模板

**Given**：
- 已创建模板 `退宿流程` 和 `出差申请`

**When**：
- 运行 `x todo template list`

**Then**：
- 退出码：`0`
- 输出包含：`退宿流程` 和 `出差申请`

---

## 场景 3：template remove 删除模板

**Given**：
- 已创建模板 `退宿流程`

**When**：
- 运行 `x todo template remove 退宿流程`

**Then**：
- 退出码：`0`
- 输出：`"✅ 模板已删除：退宿流程"`
- `<xcli_data_dir>/templates/退宿流程.yaml` 不再存在

---

## 场景 4：template remove 不存在的模板（错误）

**When**：
- 运行 `x todo template remove 退宿流程`

**Then**：
- 退出码：非 0（如 `3`）
- 输出：`"❌ 模板不存在：退宿流程"`

---

## 场景 5：template create 重名（错误）

**Given**：
- 已创建模板 `退宿流程`

**When**：
- 运行 `x todo template create 退宿流程 --steps "X,Y"`

**Then**：
- 退出码：非 0（如 `5`）
- 输出：`"❌ 模板已存在：退宿流程（请用 remove 先删，或换名字）"`

---

## 场景 6：template create 空 steps（错误）

**When**：
- 运行 `x todo template create 空模板 --steps ""`

**Then**：
- 退出码：非 0（如 `2`）
- 输出：`"❌ 模板至少需要 1 个步骤"`

---

## 场景 7：`add --template 退宿流程` 展开为父任务 + 3 个子任务

**Given**：
- 已创建模板 `退宿流程` 含 3 步

**When**：
- 运行 `x todo add "退宿离校" --template 退宿流程 --deadline 2026-07-13`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已创建 4 个任务（父 + 3 子）"`
- 文件系统：
  - `任务/退宿离校/TODO.md` 父任务
  - `任务/退宿离校-001/TODO.md` 子任务（步骤 1）
  - `任务/退宿离校-002/TODO.md` 子任务（步骤 2）
  - `任务/退宿离校-003/TODO.md` 子任务（步骤 3）
- 子任务的 `parent` 字段指向父任务 ID
- 子任务 name = `<步骤名> -001` 等（步骤去重时自动加序号）

---

## 场景 8：`add --template 退宿流程` 步骤重名去重

**Given**：
- 模板 `检查清单` 含步骤 `["检查", "检查", "检查"]`（3 个同名步骤）

**When**：
- 运行 `x todo add "项目" --template 检查清单`

**Then**：
- 退出码：`0`
- 创建子任务：`<项目>-001 检查`、`<项目>-002 检查`、`<项目>-003 检查`
- 文件夹名不冲突

---

## 场景 9：`add --template 不存在的模板`（错误）

**When**：
- 运行 `x todo add "test" --template 不存在`

**Then**：
- 退出码：非 0（如 `3`）
- 输出：`"❌ 模板不存在：不存在"`
- 不创建任何文件

---

*本文件由 v0.5 Phase E 任务生成（2026-06-30），覆盖任务模板的 create/list/remove + --template 展开*