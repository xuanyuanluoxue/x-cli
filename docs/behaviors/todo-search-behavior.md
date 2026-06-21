# x todo search 行为规格

> **目标读者**: 接续开发的 AI agent
> **范围**: `x todo search <keyword>` 命令，跨字段关键词搜索
> **对应测试**: `tests/test_todo_search.py`（单元）+ `tests/test_e2e_todo.py`（E2E）
> **状态**: 🚧 P2 规划中（2026-06-21）

---

## 用途

`x todo list` 只能按 status / priority / tag 过滤，不能按**任意关键词**搜。`search` 是对 list 的补充 — 在 name + note + tags 三个字段里模糊匹配，方便"我记不清叫什么但记得一些字"。

---

## 路径与不变量

- **存储位置**（v0.4.0+）：x-cli's 独立库（`%LOCALAPPDATA%\x-cli\todo\`）
- **永不动**：`~/.xavier/TODO/`
- **默认包含归档**（除非显式 `--active-only`）— 搜不到是常见痛苦
- **不搜 body**（body 太长 + 容易误匹配）

---

## 场景 1：基本搜索（name 命中）

**Given**:
- active 有 `任务/驾驶证考取/TODO.md`，name=驾驶证考取
- active 有 `任务/助学金/TODO.md`，name=助学金-下学期材料

**When**: 运行 `x todo search 驾驶`

**Then**:
- 退出码 0
- stdout 是表格（含表头 + 1 行）
- 命中 `驾驶证考取`
- 不命中 `助学金`（与"驾驶"无公共子串）

---

## 场景 2：note 字段也参与搜索

**Given**:
- `任务/kemu1/TODO.md` 的 frontmatter 含 `note: 跟朋友 AA 分摊`

**When**: 运行 `x todo search AA`

**Then**:
- 退出码 0
- 命中 `kemu1`（因为 note 字段含 "AA"）

---

## 场景 3：tags 字段也参与搜索

**Given**:
- `任务/kemu1/TODO.md` frontmatter 含 `tags: [驾照, 暑假]`

**When**: 运行 `x todo search 驾照`

**Then**:
- 退出码 0
- 命中 `kemu1`

> **注意**：`x todo list --tag 驾照` 和 `x todo search 驾照` 类似但**不等价**。前者是精确 tag 过滤，后者是任意字段的子串匹配。

---

## 场景 4：大小写不敏感

**Given**:
- `任务/aliyun/TODO.md` name=aliyun

**When**: 运行 `x todo search ALIYUN`

**Then**:
- 命中 `aliyun`（case-insensitive 匹配）

---

## 场景 5：默认包含归档

**Given**:
- active 0 个任务匹配
- 归档区有 1 个匹配任务 `归档/20260521-kemu1/TODO.md`

**When**: 运行 `x todo search kemu1`

**Then**:
- 退出码 0
- 命中归档任务（默认 `--all`）
- 表格 Status 列显示 `✅ archived (done)` 之类

---

## 场景 6：--active-only 只看 active

**Given**:
- 归档区有 `归档/20260521-kemu1/TODO.md`
- active 没有 `kemu1`

**When**: 运行 `x todo search kemu1 --active-only`

**Then**:
- 退出码 0
- 表格为空（或者"📭 没找到"）
- 退出码 0（空结果不算错）

---

## 场景 7：--archived-only 只看归档

**Given**:
- active 有 `kemu1`
- 归档区有 1 个 `kemu1`（曾经归档过）

**When**: 运行 `x todo search kemu1 --archived-only`

**Then**:
- 命中归档的那份（active 那份不显示）
- 表格 Status 显示 `✅ archived (...)`

---

## 场景 8：空 keyword → 退出码 2

**When**: 运行 `x todo search ""`

**Then**:
- 退出码 2
- stderr 含 `❌ 关键词不能为空`

> **设计选择**：跟 `x secret search` 一致（避免意外 dump 全库）

---

## 场景 9：无匹配

**Given**:
- 任何数据库状态

**When**: 运行 `x todo search xyz_no_match_hopefully`

**Then**:
- 退出码 0
- stdout 含 `📭 没有匹配 "xyz_no_match_hopefully" 的任务`

---

## 场景 10：组合过滤

**Given**:
- 任务 A: in_progress + 关键词 "X"
- 任务 B: pending + 关键词 "X"
- 任务 C: in_progress + 关键词 "Y"

**When**: 运行 `x todo search X --status in_progress`

**Then**:
- 仅命中 A（搜索 + status 过滤 AND）

---

## 场景 11：模糊匹配（多字符都出现）

**Given**:
- 任务 name="助学金-下学期材料"

**When**: 运行 `x todo search 助材`

**Then**:
- 命中（"助"和"材"都在 name 里出现）
- 实现策略：name/note/tags 任一字段含 keyword 的子串 OR keyword 的每个字符都在该字段中出现

> **注意**：避免更激进的 fuzzy match（如"学材"也命中"助学金-下学期材料"），保持简单可预测。

---

## 场景 12：YAML 解析失败的任务不参与搜索

**Given**:
- `任务/坏任务/TODO.md` 是无效 YAML
- 任务 A 是有效任务，含 keyword "X"

**When**: 运行 `x todo search X`

**Then**:
- 仅命中 A
- 不抛异常（坏任务被静默跳过）
- stderr 不打印警告（避免噪音；broken 任务走 `x todo stats` 的 broken report）

---

## 不变量

| 项 | 值 |
|---|---|
| 搜索字段 | `name` + `note` + `tags`（不搜 body / 不搜 priority） |
| 大小写 | 不敏感 |
| 子串 | keyword 作为整体子串 OR 每个字符都出现（宽松匹配）|
| 默认范围 | active + archived（`--all` 隐式）|
| 空 keyword | 退出码 2（防御）|
| 性能 | O(N × M)，N=任务数, M=keyword 长度；不建索引（MVP 不需要）|
| 依赖 | **零**第三方库（用现有的 `core/parser.py`）|

---

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功（0 个匹配也算 0）|
| 2 | 参数错（空 keyword / 缺 keyword）|
| 3+ | 保留（与 x todo 其他命令对齐）|

---

## 输出示例

### 找到多个
```
$ x todo search 暑假
ID         Name         Status         Priority   Deadline   Updated
─────────  ───────────  ─────────────  ─────────  ─────────  ──────────
kemu1      驾驶证考取   ▶ in_progress  🔥 high    2026-08-31  2026-06-20
zijiashixi 自主实习     ▶ in_progress  🔥 high    2026-07-01  2026-06-15
```
（按 `deadline` 升序，与 `x todo list` 一致）

### 0 个匹配
```
$ x todo search xyz_no_match
📭 没有匹配 "xyz_no_match" 的任务（搜索 name + note + tags）
💡 试试：x todo list
```

---

## 与现有命令的关系

| 命令 | 用途 |
|---|---|
| `x todo list` | 全量列出 + 结构化过滤（status / priority / tag）|
| `x todo list --tag X` | 精确 tag 匹配 |
| `x todo search X` | 跨字段模糊（name + note + tags）|
| `x todo get <id>`（未来）| 看一个任务的完整内容 |

**优先级**：`list` > `search`（list 全，search 筛）

---

## 不做（v0.4.x）

- ❌ body 字段搜索（太长、误匹配多）
- ❌ 正则表达式（`x secret search` 也不支持，保持一致）
- ❌ 搜索结果高亮（terminal 渲染复杂，MVP 不做）
- ❌ 搜索优先级 / status 字段（这些用 list --filter 更好）
- ❌ 搜索 archived 的 reason（用户通常搜任务名，不搜归档原因）

---

*本文档是活文档，search 行为扩展同步更新。*