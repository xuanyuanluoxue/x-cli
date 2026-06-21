# x todo CLI 行为规格（E2E 子进程层）

> **目标读者**: 接续开发的 AI agent  
> **范围**: 本规格覆盖 **从 PowerShell 真实调用 `x todo ...`** 的端到端行为，区别于 `tests/test_todo_*.py` 里直接调 `x.main()` 的 in-process 测试。  
> **对应测试**: `tests/test_e2e_todo.py`  
> **前置条件**: 必须用 `py -3.14 -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"` 建好 venv（系统 Python 3.14.2 被 `hydra-core` 拉入的 `antlr4` 污染，pytest 跑不起来）。

---

## 场景 1：列出任务（无参数）

**Given**:
- venv 已建好（`.venv/Scripts/x.exe` 存在）
- `XCLI_TODO_DIR` 指向临时目录，里面有 1 个 active 任务

**When**:
- 在 PowerShell 任意目录运行 `x todo list`

**Then**:
- 退出码 = 0
- stdout 是 tab 分隔表格，包含 1 行任务数据
- stderr 为空

---

## 场景 2：添加任务并立即列出

**Given**:
- venv + 空 TODO 目录

**When**:
- 运行 `x todo add "科目一模拟考" --priority high --deadline 2026-08-31 --tags 驾照,暑假`
- 运行 `x todo list`

**Then**:
- 第一条命令退出码 0，stdout 含 `✅ 任务已创建：科目一模拟考（ID: kemu1）`
- 第二条命令退出码 0，表格含 `kemu1` 行
- 文件系统：`<xcli_todo_dir>/任务/科目一模拟考/TODO.md` 存在

---

## 场景 3：按状态过滤

**Given**:
- 临时目录里 3 个任务：1 in_progress / 1 pending / 1 archived

**When**:
- 运行 `x todo list --status in_progress`

**Then**:
- 退出码 0
- 表格只含 1 行（in_progress 那个）
- 不含 archived

---

## 场景 4：按优先级过滤

**Given**:
- 临时目录里 3 个任务：2 high / 1 medium

**When**:
- 运行 `x todo list --priority high`

**Then**:
- 表格含 2 行

---

## 场景 5：按 tag 过滤

**Given**:
- 临时目录里任务 A tags=[驾照]，任务 B tags=[暑假]

**When**:
- 运行 `x todo list --tag 驾照`

**Then**:
- 表格含 A 不含 B

---

## 场景 6：组合过滤

**Given**:
- 任务 A: in_progress, high, [驾照]
- 任务 B: in_progress, high, [暑假]
- 任务 C: pending, high, [驾照]

**When**:
- 运行 `x todo list --status in_progress --priority high --tag 驾照`

**Then**:
- 只含 A（AND 关系）

---

## 场景 7：--all 含归档

**Given**:
- 1 active + 1 archived

**When**:
- 运行 `x todo list --all`

**Then**:
- 表格含 2 行；归档行 Status 列形如 `archived (done)`

---

## 场景 8：非法 status 值

**Given**:
- 任意 TODO 目录

**When**:
- 运行 `x todo list --status not_a_status`

**Then**:
- 退出码 = 2
- stderr 含 `❌ 无效的 status 值：not_a_status`
- stderr 列出合法值（pending / in_progress / blocked / waiting / archived）

---

## 场景 9：添加任务缺任务名

**When**:
- 运行 `x todo add`

**Then**:
- 退出码 = 2（argparse 拒绝）
- stderr 含 `the following arguments are required: 名称`

---

## 场景 10：添加任务名重复

**Given**:
- 临时目录已有 `科目一模拟考`（slug `kemu1`）

**When**:
- 运行 `x todo add "科目一模拟考"`

**Then**:
- 退出码 = 3
- stderr 含 `❌ 任务名已存在：科目一模拟考`

---

## 场景 11：添加任务非法 priority

**When**:
- 运行 `x todo add "测试" --priority urgent`

**Then**:
- 退出码 = 2
- stderr 含 `❌ 无效的 priority 值：urgent`

---

## 场景 12：更新任务

**Given**:
- 临时目录有任务 `kemu1`（pending, high）

**When**:
- 运行 `x todo update kemu1 --status in_progress`

**Then**:
- 退出码 0
- stdout 含 `✅ 任务已更新`
- 重新 `x todo list` 该行 Status = `in_progress`

---

## 场景 13：更新不存在的任务

**When**:
- 运行 `x todo update nonexistent --status done`

**Then**:
- 退出码 = 3
- stderr 含 `❌ 任务不存在：nonexistent`

---

## 场景 14：归档任务

**Given**:
- 临时目录有任务 `kemu1`

**When**:
- 运行 `x todo archive kemu1`

**Then**:
- 退出码 0
- stdout 含 `✅ 任务已归档：科目一模拟考（ID: kemu1，reason=done）`
- 文件系统：`<xcli_todo_dir>/归档/YYYYMMDD-科目一模拟考/TODO.md` 存在
- 重新 `x todo list` 该任务消失（默认不显示归档）

---

## 场景 15：重复归档

**Given**:
- 任务 `kemu1` 已归档

**When**:
- 运行 `x todo archive kemu1`

**Then**:
- 退出码 = 4
- stderr 含 `❌ 任务已归档：kemu1`

---

## 场景 16：非法 reason

**When**:
- 运行 `x todo archive kemu1 --reason 完成`

**Then**:
- 退出码 = 2
- stderr 含 `❌ 无效的 reason 值：完成`

---

## 场景 17：统计

**Given**:
- 临时目录有混合状态 / 优先级 / 归档的任务

**When**:
- 运行 `x todo stats`

**Then**:
- 退出码 0（无 broken YAML）
- stdout 含 `📊 TODO 统计信息`、`总任务数：`、各状态分布、优先级分布、`即将到期`、`🔥 高优先级任务`

---

## 场景 18：`x --version`

**When**:
- 运行 `x --version`

**Then**:
- 退出码 0
- stdout = `x 0.2.0`（无换行以外的字符）

---

## 场景 19：`x --help`

**When**:
- 运行 `x --help`

**Then**:
- 退出码 0
- stdout 含 `usage:` 和子命令列表（todo）

---

## 场景 20：`x todo` 无 action

**When**:
- 运行 `x todo`

**Then**:
- 退出码 0
- stdout 含 `usage: x todo` 和可用 action 列表

---

## 场景 21：未知子命令

**When**:
- 运行 `x nonexistent`

**Then**:
- 退出码 = 1
- stderr 含 `❌ 错误：未知子命令：nonexistent`

---

## 不变量

| 项 | 值 |
|---|---|
| Python 版本 | 3.14.2 |
| venv 路径 | `.venv/` |
| 真实 TODO 路径 | **永不触碰**（全部走 `XCLI_TODO_DIR` 临时目录） |
| `x` 调用方式 | subprocess 启动 `.venv/Scripts/x.exe`（**不**走 `python x.py`）|
| 测试隔离 | pytest fixture `tmp_path` + `monkeypatch.setenv("XCLI_TODO_DIR", ...)` |

---

*本文档是活文档，E2E 测试集随命令扩展同步更新。*

