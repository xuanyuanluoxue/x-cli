# x todo import 行为规格

> **目标读者**: 接续开发的 AI agent
> **范围**: `x todo import --from <dir>` 命令，从 xavier 系统单向迁移 TODO 到 x-cli's 独立库
> **对应测试**: `tests/test_e2e_todo.py`（E2E 子进程测试）
> **状态**: 🚧 P1 实现中（2026-06-21）

---

## 用途

把 `~/.xavier/TODO/任务/<name>/` 下的所有任务（含 frontmatter）复制到 x-cli 的独立数据库。**单向**，**不删源**，**不写回 xavier**。

---

## 场景 1：基本迁移

**Given**:
- 源目录 `C:\Users\X\xavier-todo\` 含 5 个 active 任务（`<name>/TODO.md`）+ 30 个 archived 任务（`归档/YYYYMMDD-<name>/TODO.md`）
- x-cli's TODO 库为空

**When**:
- 运行 `x todo import --from C:\Users\X\xavier-todo`

**Then**:
- 退出码 0
- stdout 含 `📥 迁移完成：导入 35 个，跳过 0 个（重复）`
- x-cli 的 TODO 库新增 35 个条目（5 active + 30 archived）
- 源目录**不**被修改（`~/.xavier/TODO\` 仍然完整）

---

## 场景 2：跳过重复（同 name 已存在）

**Given**:
- 源目录有 `科目一模拟考/TODO.md`（id=kemu1）
- x-cli's TODO 库已有 `科目一模拟考`（id=kemu1）

**When**:
- 运行 `x todo import --from <src>`

**Then**:
- 退出码 0
- stdout 含 `📥 迁移完成：导入 X 个，跳过 1 个（重复）`
- x-cli 的现有条目**不变**（不覆盖）

---

## 场景 3：源目录不存在

**Given**:
- `--from /nonexistent/path/`

**When**:
- 运行 `x todo import --from /nonexistent/path/`

**Then**:
- 退出码 1（IO 错）
- stderr 含 `❌ 源目录不存在：/nonexistent/path/`
- x-cli 库不变

---

## 场景 4：解析 frontmatter 失败

**Given**:
- 源目录有 `坏任务/TODO.md`，内容是 `not valid frontmatter`

**When**:
- 运行 `x todo import --from <src>`

**Then**:
- 退出码 0（其他正常任务继续迁移）
- stdout 含 `⚠️ 跳过 1 个（YAML 解析失败）：坏任务`
- 其他有效任务正常导入

---

## 场景 5：迁移到自定义目录

**Given**:
- `--from C:\xavier-todo --to D:\my-xcli\todo`
- `D:\my-xcli\todo` 不存在

**When**:
- 运行 `x todo import --from C:\xavier-todo --to D:\my-xcli\todo`

**Then**:
- 退出码 0
- 自动创建 `D:\my-xcli\todo\任务\` 和 `D:\my-xcli\todo\归档\`
- 35 个任务导入到 D:\my-xcli\todo\
- stdout 含路径信息

---

## 场景 6：`--dry-run`（默认行为）

**Given**:
- 任何 `--from` 路径

**When**:
- 运行 `x todo import --from <src>`

**Then**:
- 默认就是只读源（不写回 xavier）
- 即不传 `--dry-run`，也不写源
- **显式 `--dry-run` flag**：只显示会迁什么，不实际写

---

## 场景 7：保留源数据（硬性约束）

**Given**:
- 任何导入操作

**When**:
- 任意 `x todo import` 命令

**Then**:
- 源目录的 `.md` 文件**永不**被修改
- 源目录的文件夹结构**永不**被删除
- 源目录的归档区**永不**被触动

> **这是核心安全约束**：迁移是单向只读的。任何破坏源数据的代码都是 bug。

---

## 不变量

| 项 | 值 |
|---|---|
| 源路径 | `--from <dir>`（必填）|
| 目标路径 | 默认 x-cli's TODO 库；`--to <dir>` 覆盖（可选）|
| 重复处理 | 跳过，不覆盖 |
| 失败处理 | 单个失败不阻塞其他，跳过并报告 |
| 源数据保护 | **永不**修改、删除源文件 |
| Frontmatter 字段 | 全字段 round-trip（含未知字段如 `paused_at`）|
| 文件格式 | YAML frontmatter + Markdown body（与 xavier 兼容）|
| 依赖 | **零**第三方库（用现有的 `core/parser.py`）|

---

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功（部分跳过也是 0）|
| 1 | 源目录不存在 / IO 错 |
| 2 | 缺少 `--from` 参数 |
| 3+ | 保留（与 x todo 其他命令对齐）|

---

## 输出示例

```
$ x todo import --from C:\Users\Chatxavier\.xavier\TODO
📥 迁移完成：
   - 导入 35 个（5 active + 30 archived）
   - 跳过 0 个（重复）
   - 跳过 2 个（YAML 解析失败）：坏任务1, 坏任务2

💡 试用：x todo list
```

---

## 与 `x secret import` 的差异

| | `x secret import` | `x todo import` |
|---|---|---|
| 源格式 | `.md` 文件（每个 `## section` 一个 secret）| `.md` 文件（每个 folder 一个 task）|
| 目标格式 | JSON 单文件 | 多 `.md` 文件（每任务一文件夹，复用 storage 格式）|
| 重复策略 | 跳过同名 | 跳过同名（同 task name）|
| 源保护 | 不删 .md | 不删 .md + 不删文件夹 |

---

*本文档是活文档，import 行为扩展同步更新。*