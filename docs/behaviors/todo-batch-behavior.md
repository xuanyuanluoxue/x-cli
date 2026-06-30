# x todo 批量操作 行为规格（v0.5 Phase D）

> **对应命令**：`x todo done / archive / update / remove`
> **新增 flag**：
> - `<id...>` 接受多个 id（空格分隔）
> - `--filter <keyword>`（模糊匹配 name + tags + note）
> - `--all`（扩到 archived 范围，update/remove 默认 active only）
> - `--force`（`x todo remove` 时跳过回收站，物理删除）
> **新增子命令**：`x todo remove <id...>`
> **数据规范**：无新增字段；只改命令面
> **来源**：[PLAN-v0.5.md §2.3.2 + §2.3.4](../../../PLAN-v0.5.md)
>
> **v0.5 范围**：
> - ✅ done / archive / update / remove 接受多 id
> - ✅ --filter 模糊匹配（替代显式 id 列表）
> - ✅ --all 扩到 archived（与 --filter 配合更强大）
> - ✅ x todo remove 走系统回收站（Windows / macOS / Linux 跨平台）
> - ✅ remove --force 跳过回收站
> - ⚠️ **批量 done/archive 不逐个 y/N 确认级联**（用户显式敲命令 = 已确认；单个父任务级联已在 Phase B 实现）

---

## 场景 1：`done` 批量多 id

**Given**：
- 任务 `t-a`, `t-b`, `t-c` 存在（active）

**When**：
- 运行 `x todo done t-a t-b t-c`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已归档 3 个任务（done）：t-a, t-b, t-c"`
- 3 个任务全部 archived（reason=done）

---

## 场景 2：`done` 部分 id 不存在（部分成功 + 部分错误）

**Given**：
- 任务 `t-a` 存在；`t-nope` 不存在

**When**：
- 运行 `x todo done t-a t-nope`

**Then**：
- 退出码：非 0（如 `3`，表示有失败）
- 输出：`"⚠️ 部分失败：已归档 1 个，未找到 1 个（t-nope）"`
- `t-a` 已归档

---

## 场景 3：`archive` + `--filter` 模糊匹配

**Given**：
- 任务 A：`name="买菜"`, `tags=["周末"]`
- 任务 B：`name="买衣服"`, `tags=["购物"]`
- 任务 C：`name="做饭"`, `tags=["厨房"]`

**When**：
- 运行 `x todo archive --filter "买"`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已归档 2 个匹配 '买' 的任务：买菜, 买衣服"`
- 任务 A + B 归档；任务 C 不动

---

## 场景 4：`update --filter` 批量更新 deadline

**Given**：
- 任务 A, B 都 deadline 2026-06-01；任务 C deadline 2026-07-01

**When**：
- 运行 `x todo update --filter "买菜|买衣服" --deadline 2026-12-31`

**Then**：
- 退出码：`0`
- 任务 A + B 的 deadline 改为 2026-12-31
- 任务 C 不动

---

## 场景 5：`update --all` 扩到 archived 范围

**Given**：
- 任务 `t-active`（active）
- 任务 `t-archived`（已归档，status=archived）

**When**：
- 运行 `x todo update --all --filter "test" --priority low`

**Then**：
- 退出码：非 0（如 `4`）
- 输出错误：`"❌ 已归档任务不可更新：t-archived"`
- `t-active` 如匹配被更新；`t-archived` 拒绝（Phase B 行为）

---

## 场景 6：`x todo remove <id>` 走回收站

**Given**：
- 任务 `t-trash` 存在（active）

**When**：
- 运行 `x todo remove t-trash`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已移入回收站：t-trash"`
- 文件系统：
  - `任务/t-trash/` 不再存在
  - 文件进了系统回收站（Windows: Recycle Bin; macOS: ~/.Trash; Linux: gio trash）

---

## 场景 7：`x todo remove --force` 跳过回收站

**Given**：
- 任务 `t-perm` 存在

**When**：
- 运行 `x todo remove t-perm --force`

**Then**：
- 退出码：`0`
- 输出：`"⚠️ 已物理删除（绕过回收站）：t-perm"`
- 文件**不**进回收站（直接物理删除，不可恢复）

---

## 场景 8：`x todo remove` 批量多 id

**Given**：
- 任务 `t-a`, `t-b` 存在

**When**：
- 运行 `x todo remove t-a t-b`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已移入回收站：t-a, t-b（共 2 个）"`
- 两个任务文件夹都进了回收站

---

## 场景 9：`x todo remove --filter` 模糊匹配

**Given**：
- 任务 A, B, C（同场景 3）

**When**：
- 运行 `x todo remove --filter "买"`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已移入回收站 2 个：买菜, 买衣服"`
- 任务 A + B 进回收站；任务 C 不动

---

## 场景 10：`x todo remove` 不存在任务（错误路径）

**When**：
- 运行 `x todo remove t-nope`

**Then**：
- 退出码：非 0（如 `3`）
- 输出：`"❌ 任务不存在：t-nope"`

---

## 场景 11：`x todo remove` y/N 确认（破坏性操作）

**Given**：
- 任务 `t-confirm` 存在

**When**（stdin 输入 `y`）：
- 运行 `x todo remove t-confirm`

**Then**：
- 退出码：`0`
- 输出：`"? 确认删除 t-confirm？(y/N)"`
- 用户输入 `y` → 任务进回收站

**When**（stdin 输入 `n` 或 EOF）：
- 运行 `x todo remove t-confirm`

**Then**：
- 退出码：`2`（取消）
- 输出：`"❌ 已取消"`

**注**：v0.5 默认**不**强制 y/N（避免与脚本/管道冲突）；后续可加 `--confirm` 强制。

---

## 场景 12：`remove` 父任务 → 子任务也进回收站

**Given**：
- 任务 `t-parent`（有子 `t-child`，`t-child` 有孙 `t-gc`）

**When**：
- 运行 `x todo remove t-parent`

**Then**：
- 退出码：`0`
- 输出：`"✅ 已移入回收站 3 个：t-parent, t-child, t-gc"`
- 3 个任务都进回收站（永远级联，与 Phase B archive 一致）

---

*本文件由 v0.5 Phase D 任务生成（2026-06-30），覆盖批量 + filter + 回收站*