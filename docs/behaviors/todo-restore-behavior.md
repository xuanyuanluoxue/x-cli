# x todo restore 行为规格

> **目标读者**: 接续开发的 AI agent
> **范围**: `x todo restore <id>` 命令，把归档任务还原到 active
> **对应测试**: `tests/test_todo_restore.py`（单元）+ `tests/test_e2e_todo.py`（E2E）
> **状态**: 🚧 P1 规划中（2026-06-21，todo 全生命周期闭环的最后一块）

---

## 用途

把 `归档/YYYYMMDD-<name>/` 下的任务还原为 active `任务/<name>/`，恢复 `status: pending`（默认）+ 移除 `reason` 字段 + 更新 `updated` 时间戳。**不删源**（归档文件夹保留为审计备份）。

---

## 路径与不变量

- **存储位置**（v0.4.0+）：x-cli's 独立库 `%LOCALAPPDATA%\x-cli\todo\` (Win) / `~/.local/share/x-cli/todo/` (Unix)
- **永不动**：`~/.xavier/TODO/`（除非显式 `XAVIER_TODO_DIR` 覆盖）
- **归档目录命名**：`YYYYMMDD-<name>/`（date 是归档当天）
- **还原目标**：`任务/<name>/`（去掉日期前缀）

---

## 场景 1：基本还原（最常用）

**Given**:
- 归档区有 `归档/20260521-kemu1/TODO.md`，内容是：
  ```yaml
  ---
  id: kemu1
  name: 驾驶证考取
  status: archived
  priority: high
  deadline: 2026-08-31
  reason: done
  updated: '2026-05-21'
  ---
  ```
- active 区没有 `任务/kemu1/`

**When**:
- 运行 `x todo restore kemu1`

**Then**:
- 退出码 0
- stdout 含 `✅ 任务已还原：驾驶证考取（ID: kemu1，was archived on 2026-05-21）`
- 归档区 `归档/20260521-kemu1/` **仍然存在**（不删源）
- active 区 `任务/kemu1/TODO.md` 新建，内容：
  ```yaml
  ---
  id: kemu1
  name: 驾驶证考取
  status: pending      # ← archived → pending
  priority: high
  deadline: 2026-08-31
  # reason 字段移除
  updated: '2026-06-21' # ← 今天
  ---
  ```
- frontmatter 其它字段（`created`、`tags`、`note`、未知字段如 `paused_at`）**全部保留**

---

## 场景 2：按 ID 或按归档名（带日期前缀）都能识别

**Given**:
- 归档区有 `归档/20260521-kemu1/TODO.md`

**When A**: 运行 `x todo restore kemu1`（不带日期）
**Then A**: 还原成功（按 `id` 字段匹配）

**When B**: 运行 `x todo restore 20260521-kemu1`（带完整归档名）
**Then B**: 还原成功（按 folder 名匹配）

**When C**: 运行 `x todo restore kemu1` 但**两个版本都存在**（kemu1 同时在 active 和 归档）
**Then C**:
- 退出码 3
- stderr 含 `❌ 任务已存在（active）：kemu1（请先 archive 或改用归档名）`

---

## 场景 3：找不到任务

**Given**:
- 任何数据库状态

**When**: 运行 `x todo restore nonexistent`

**Then**:
- 退出码 3
- stderr 含 `❌ 任务不存在：nonexistent`

---

## 场景 4：任务不在归档区

**Given**:
- active 有 `任务/kemu1/`，但归档区没有

**When**: 运行 `x todo restore kemu1`

**Then**:
- 退出码 4
- stderr 含 `❌ 任务未归档：kemu1（请用 x todo update 改状态）`
- active 文件**不**被修改

---

## 场景 5：恢复后保留原 status（不只是 pending）

**Given**:
- 归档 frontmatter `status: in_progress`（还原前是 in_progress）
- 归档 `updated: '2026-05-21'`

**When**: 运行 `x todo restore kemu1`

**Then**:
- 还原后 `status: in_progress`（**保留**原状态，不是强制 pending）
- `updated: '2026-06-21'`（刷新到今天）

> **设计选择**：restore 不"重置"任务到 pending，而是恢复**最后已知状态**。用户如果想真正重新开始，可以 `x todo update kemu1 --status pending`。

---

## 场景 6：归档 YAML 损坏

**Given**:
- 归档区 `归档/20260521-bad/TODO.md` 内容是 `not valid frontmatter`

**When**: 运行 `x todo restore bad`

**Then**:
- 退出码 5（数据完整性错）
- stderr 含 `❌ 归档任务解析失败：bad（YAML 格式错误）`
- 不创建新 active 文件

---

## 场景 7：同名归档多份（极端情况）

**Given**:
- 归档区有 `归档/20260521-kemu1/` 和 `归档/20260601-kemu1/`（同一任务被多次归档）

**When**: 运行 `x todo restore kemu1`

**Then**:
- 优先还原**最新**的一份（`20260601-kemu1`，按日期排序最大）
- 退出码 0
- stdout 含 `（选择最新归档：20260601-kemu1）`
- 另一份归档保留

---

## 场景 8：断电 / 部分写入恢复

**Given**:
- 归档文件存在
- active 文件**已存在**（手动或其他进程创建的）
- 归档 status=archived

**When**: 运行 `x todo restore kemu1`

**Then**:
- 退出码 3
- stderr 含 `❌ active 任务已存在：kemu1（先 archive 或手动删除 任务/kemu1/）`
- 不覆盖现有 active

---

## 场景 9：自定义 status 恢复（force flag）

**Given**:
- 归档 status=archived
- 归档 priority=high

**When**: 运行 `x todo restore kemu1 --status in_progress`

**Then**:
- 还原后 status 强制设为 in_progress（覆盖归档的原值）
- 退出码 0
- priority / deadline 等其它字段保留归档值

---

## 场景 10：--dry-run（不实际还原）

**Given**:
- 归档区有 `归档/20260521-kemu1/`

**When**: 运行 `x todo restore kemu1 --dry-run`

**Then**:
- 退出码 0
- stdout 含 `🔍 [dry-run] 将还原：驾驶证考取（ID: kemu1）` + 字段预览
- active 区**不**创建任何文件
- 归档区**不**修改

---

## 不变量

| 项 | 值 |
|---|---|
| 归档文件夹**不**删除 | 永远保留作为审计 |
| 归档文件**不**修改 | read-only |
| 还原目标 | `任务/<name>/TODO.md` |
| 字段保留 | 除 `status`（→pending 或原值）、`reason`（删除）、`updated`（→今天）外全部 |
| 未知字段 | 全部保留（用 Task.to_markdown() round-trip）|
| frontmatter 模板版本 | 不变（v1.0）|
| 并发 | 单进程内串行；多进程并发未保护（跟 todo 写操作一致）|

---

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功（--dry-run 也算 0）|
| 2 | 参数错（缺 `<id>` 等）|
| 3 | 任务不存在 / active 已有同名（冲突）|
| 4 | 任务没归档（不是 archived 状态）|
| 5 | 归档 YAML 解析失败 / 复制失败（IO 错）|

---

## 输出示例

### 基本还原
```
$ x todo restore kemu1
✅ 任务已还原：驾驶证考取（ID: kemu1）
   归档：归档/20260521-kemu1/TODO.md → 任务/kemu1/TODO.md
   字段变化：status archived → pending, reason 移除, updated 刷新
```

### 已存在 active
```
$ x todo restore kemu1
❌ 任务已存在（active）：kemu1
💡 提示：先 archive 或改用 20260521-kemu1 引用归档
```

### dry-run
```
$ x todo restore kemu1 --dry-run
🔍 [dry-run] 将还原：驾驶证考取（ID: kemu1）
   from: 归档/20260521-kemu1/TODO.md
   to:   任务/kemu1/TODO.md
   field diff: status archived → pending, reason 删除, updated 刷新
```

---

## 不做（v0.4.x）

- ❌ 自动从 active 还原（需要用户显式 `restore`，避免误操作）
- ❌ 还原到非 pending 状态（用 `--status` 覆盖）
- ❌ 删除归档源（保留作为审计记录）
- ❌ 批量 restore `x todo restore --all`（用 shell 循环即可，单命令先简化）

---

*本文档是活文档，restore 行为扩展同步更新。*
