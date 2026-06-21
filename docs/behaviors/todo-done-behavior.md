# x todo done 行为规格

> **目标读者**: 接续开发的 AI agent
> **范围**: `x todo done <id>` 命令，`x todo archive --reason done` 的快捷方式
> **对应测试**: `tests/test_todo_done.py`（单元）+ `tests/test_e2e_todo.py`（E2E）
> **状态**: 🚧 P2 规划中（2026-06-21）

---

## 用途

最常见的归档操作是"做完了"（而不是 cancelled / expired / failed）。`x todo done <id>` 是 `x todo archive <id> --reason done` 的语义化快捷方式，省 1 个 flag、少 1 个心智负担。

---

## 路径与不变量

- **存储位置**（v0.4.0+）：x-cli's 独立库
- **永不动**：`~/.xavier/TODO/`
- **底层调用**：`x.py:_todo_done` 直接 delegate 给 `_todo_archive(parsed)`（`--reason done` 预填）

---

## 场景 1：基本 done（最常用）

**Given**:
- active 有 `任务/kemu1/TODO.md`，status=in_progress

**When**: 运行 `x todo done kemu1`

**Then**:
- 退出码 0
- stdout 含 `✅ 任务已归档：驾驶证考取（ID: kemu1，reason=done）`
- 任务文件夹从 `任务/kemu1/` 移到 `归档/20260621-kemu1/`（当天日期）
- frontmatter `status: archived` + `reason: done`
- 更新 `updated: '2026-06-21'`

> **完全等价于**：`x todo archive kemu1 --reason done`（用户可以放心 alias）

---

## 场景 2：与 archive 行为完全一致

**Given**: 任何 active 任务

**When**:
- 用 `x todo done <id>` 归档
- 然后用 `x todo archive <id> --reason done` 尝试再次归档

**Then**:
- 第一次成功（退出码 0）
- 第二次退出码 4（"已归档"错误），跟 archive 行为一致

---

## 场景 3：任务不存在

**Given**: 任何数据库状态

**When**: 运行 `x todo done nonexistent`

**Then**:
- 退出码 3
- stderr 含 `❌ 任务不存在：nonexistent`

---

## 场景 4：任务已归档

**Given**:
- 任务在 `归档/20260521-kemu1/`（已归档）

**When**: 运行 `x todo done kemu1`

**Then**:
- 退出码 4
- stderr 含 `❌ 任务已归档：kemu1（位于 归档/20260521-kemu1）`

---

## 场景 5：多种 reason 的对比（语义化收益）

| 任务类型 | 推荐命令 | 实际 reason |
|---|---|---|
| 做完了 | `x todo done <id>` | done |
| 主动放弃 | `x todo archive <id> --reason cancelled` | cancelled |
| 过期没做 | `x todo archive <id> --reason expired` | expired |
| 试了失败 | `x todo archive <id> --reason failed` | failed |

> **设计意图**：`done` 是 80% case 的快捷入口（最常见）。其它 reason 保留 `--reason` flag（语义明确）。

---

## 场景 6：与 x secret get 的"clipboard" 哲学一致

类比：
- `x secret get <name>` = 拷贝到剪贴板（"我马上要粘贴"）→ **use case 优化**
- `x todo done <id>` = 归档为 done（"我做完了"）→ **use case 优化**

两者都是"高频场景 → 少打几个字"的快捷命令。

---

## 不变量

| 项 | 值 |
|---|---|
| 实现的 reason | 固定 `done`（不接受 `--reason` flag 覆盖） |
| 行为 | 与 `x todo archive <id> --reason done` **完全等价** |
| 退出码 | 0 成功 / 3 不存在 / 4 已归档（跟 archive 对齐） |
| 副作用 | 文件夹移动 + frontmatter 更新 + inventory 维护 |

---

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 2 | 参数错（缺 `<id>`）|
| 3 | 任务不存在 |
| 4 | 任务已归档 |
| 5 | 归档碰撞（目标文件夹已存在）|

---

## 输出示例

```
$ x todo done kemu1
✅ 任务已归档：驾驶证考取（ID: kemu1，reason=done）
   归档：任务/kemu1/ → 归档/20260621-kemu1/
   状态：in_progress → archived (done)
```

---

## 与 archive 的关系

| 维度 | `x todo archive` | `x todo done` |
|---|---|---|
| 接受 `--reason` | ✅（4 个值）| ❌（固定 done）|
| 字符数（典型）| 30+ | 13 |
| 覆盖 use case | 100% | ~80%（most common）|
| 调用关系 | 基础 | delegate 到 archive（`--reason done`）|

**用户视角**：
- 80% 时间用 `x todo done <id>`
- 20% 时间（特殊 reason）用 `x todo archive <id> --reason <X>`

**实现视角**：
- `_todo_done` 复用 `_todo_archive`（DRY）
- `_todo_done` 预填 `--reason done`

---

## 不做（v0.4.x）

- ❌ 接受 `--reason` 覆盖（保持语义单一 — "done 就是 done"）
- ❌ 接受 `--note` 写"为什么 done"（用 `x todo update <id> --note ...` 之前记录）
- ❌ `x todo done --all` 批量完成（shell 循环即可）
- ❌ `x todo undid <id>` 撤销（用 `x todo restore` 即可）

---

*本文档是活文档，done 行为扩展同步更新。*