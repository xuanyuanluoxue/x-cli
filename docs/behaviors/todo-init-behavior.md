# x todo init 行为规格

> **目标读者**: 接续开发的 AI agent
> **范围**: `x todo init` 命令，初始化 x-cli 独立的 TODO 数据库
> **对应测试**: `tests/test_e2e_todo.py`（E2E 子进程测试）
> **状态**: 🚧 P1 实现中（2026-06-21）

---

## 用途

新设备 / 新用户 / 重置时，一键创建 x-cli's 独立 TODO 目录结构，避免手动 `mkdir`。

---

## 场景 1：首次初始化，目录不存在

**Given**:
- `XAVIER_TODO_DIR` 未设
- `%LOCALAPPDATA%\x-cli\todo\` 不存在

**When**:
- 运行 `x todo init`

**Then**:
- 退出码 0
- stdout 含 `✅ TODO 目录已创建：<full_path>`
- 创建以下结构：
  ```
  <xcli_todo_dir>/
  ├── 任务/         (active 任务)
  ├── 归档/         (archived 任务)
  └── README.md     (目录说明文档)
  ```
- 文件权限 600（Unix）

---

## 场景 2：目录已存在（幂等）

**Given**:
- `XAVIER_TODO_DIR` 未设
- `%LOCALAPPDATA%\x-cli\todo\任务\` 已存在（来自之前的 `x todo list` 调用）

**When**:
- 运行 `x todo init`

**Then**:
- 退出码 0
- stdout 含 `✅ TODO 目录已存在：<full_path>`（不是"已创建"）
- 不覆盖任何已有内容
- 不报错

---

## 场景 3：自定义目录 `x todo init --dir <path>`

**Given**:
- `--dir D:\my-projects\todo`

**When**:
- 运行 `x todo init --dir D:\my-projects\todo`

**Then**:
- 退出码 0
- stdout 含 `✅ TODO 目录已创建：D:\my-projects\todo`
- 在该路径创建 `任务/` + `归档/` + `README.md`
- 后续 `x todo list`（不设 XAVIER_TODO_DIR）仍读默认路径 — **--dir 只影响本次 init**

---

## 场景 4：环境变量 + init

**Given**:
- `XAVIER_TODO_DIR=D:\test-todo`

**When**:
- 运行 `x todo init`

**Then**:
- 退出码 0
- stdout 含 `✅ TODO 目录已创建：D:\test-todo`
- 在 `D:\test-todo\` 创建目录结构

---

## 场景 5：权限不足

**Given**:
- `--dir C:\Windows\System32\protected\`（无写权限）

**When**:
- 运行 `x todo init --dir C:\Windows\System32\protected\`

**Then**:
- 退出码非 0（一般是 1）
- stderr 含 `❌ 无法创建目录：<error>`
- 不抛 Python traceback

---

## 场景 6：`x todo init`（无参数）显示用法

**When**:
- 运行 `x todo init`

**Then**:
- 退出码 0
- stdout 含 usage + `--dir <路径>` 说明

---

## 不变量

| 项 | 值 |
|---|---|
| 默认路径 | `%LOCALAPPDATA%\x-cli\todo\` (Win) / `~/.local/share/x-cli/todo/` (Unix) |
| 创建内容 | `任务/` + `归档/` 子目录 + `README.md` 索引 |
| README.md 内容 | 说明这是 x-cli 独立数据库，跟 `~/.xavier/TODO/` 是两个独立副本（如果用户同时用两边）|
| 幂等 | 是（已存在则提示，不覆盖） |
| 依赖 | **零**第三方库（只 stdlib `pathlib` + `os`）|

---

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功（新建或已存在）|
| 1 | 无法创建目录（权限 / IO 错误）|
| 2 | 参数错误（argparse 拒绝）|

---

## 输出示例

### 首次初始化
```
$ x todo init
✅ TODO 目录已创建：C:\Users\Chatxavier\AppData\Local\x-cli\todo\
   - 任务\
   - 归档\
   - README.md

💡 试用：x todo add "我的第一个任务"
```

### 已存在
```
$ x todo init
✅ TODO 目录已存在：C:\Users\Chatxavier\AppData\Local\x-cli\todo\
   不需要重复创建。
```

---

*本文档是活文档，init 行为扩展同步更新。*