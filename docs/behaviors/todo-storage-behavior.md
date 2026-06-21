# x todo 存储路径行为规格

> **目标读者**: 接续开发的 AI agent
> **范围**: `x todo` 子命令的存储路径解析规则
> **对应测试**: `tests/test_storage.py`（已有）+ 新增 `tests/test_todo_storage_path.py`
> **状态**: 🚧 P1 实现中（2026-06-21，决策：跟 `x secret` 对齐，**独立于 legacy TODO system**）

---

## 决策背景

`x-cli's x secret` 已经使用独立数据库（`%LOCALAPPDATA%\x-cli\secrets.json`），但 `x todo` 一直共享 legacy TODO system的 `<xcli_todo_dir>/`。这种不一致违反 "x-cli 是独立通用 CLI 工具" 的核心原则。本次决策：**`x todo` 也独立**。

---

## 路径解析规则

| 来源 | 行为 |
|------|------|
| 环境变量 `XCLI_TODO_DIR` | **第一优先级** — 设为任何路径就完全用该路径（向后兼容测试 / 用户覆盖）|
| 默认（Windows） | `%LOCALAPPDATA%\x-cli\todo\`（不存在则 mkdir） |
| 默认（Unix） | `$XDG_DATA_HOME/x-cli/todo/` → fallback `~/.local/share/x-cli/todo/`（不存在则 mkdir）|
| **永远不** 读 `<xcli_todo_dir>/` | 即使 legacy TODO system存在该目录，x-cli 也不自动用 |

**核心不变量**：`core/storage.py:_default_todo_dir()` 只返回 3 种路径之一 — 环境变量值 / Windows 默认 / Unix 默认。**绝不**爬到 `<xcli_todo_dir>/`。

---

## 场景 1：未设环境变量，Windows，默认路径

**Given**:
- 无 `XCLI_TODO_DIR`
- `LOCALAPPDATA=C:\Users\X\AppData\Local`

**When**:
- 启动 `x todo list`

**Then**:
- 实际读 `C:\Users\X\AppData\Local\x-cli\todo\任务\`（如不存在则 mkdir）
- 不读 `<xcli_todo_dir>\`（即使它存在）
- 输出任务列表

---

## 场景 2：未设环境变量，Unix，XDG_DATA_HOME 已设

**Given**:
- 无 `XCLI_TODO_DIR`
- `XDG_DATA_HOME=/custom/data`
- `<xcli_todo_dir>/` 存在并含任务

**When**:
- 启动 `x todo list`

**Then**:
- 实际读 `/custom/data/x-cli/todo/任务/`（新建）
- **不**读 `<xcli_todo_dir>/`
- 输出空（因为新目录没任务）

---

## 场景 3：未设环境变量，Unix，XDG_DATA_HOME 未设

**Given**:
- 无 `XCLI_TODO_DIR` 和 `XDG_DATA_HOME`

**When**:
- 启动 `x todo list`

**Then**:
- 实际读 `~/.local/share/x-cli/todo/任务/`（新建）

---

## 场景 4：设了 `XCLI_TODO_DIR`，向后兼容

**Given**:
- `XCLI_TODO_DIR=/tmp/custom-todo`

**When**:
- 启动 `x todo list`

**Then**:
- 实际读 `/tmp/custom-todo/任务/`
- 即使用户目录里有 `<xcli_todo_dir>/`，也**不**读

> **兼容性说明**：这个 env var 名字历史遗留（叫 `XCLI_TODO_DIR`），但 x-cli's 视角就是"覆盖默认路径"，跟 legacy TODO system无关。改名（→ `XCLI_TODO_DIR`）是 P2 项，本期不动。

---

## 场景 5：默认路径不存在，自动创建

**Given**:
- `XCLI_TODO_DIR` 未设
- `%LOCALAPPDATA%\x-cli\todo\` 不存在

**When**:
- 启动 `x todo list`

**Then**:
- 自动 `mkdir(parents=True, exist_ok=True)` 创建 `%LOCALAPPDATA%\x-cli\todo\` + 子目录 `任务\` + `归档\`
- 不报错
- 输出 `📭 没有任务（试试 x todo add "任务名" 创建第一个）`

---

## 场景 6：默认路径有文件权限问题

**Given**:
- `XCLI_TODO_DIR` 未设
- `%LOCALAPPDATA%\x-cli\todo\` 父目录只读

**When**:
- 启动 `x todo list`

**Then**:
- 退出码非 0
- stderr 含 `❌ 无法创建 TODO 目录：...`
- 不读任何 legacy TODO system目录

---

## 不变量

| 项 | 值 |
|---|---|
| 真实 `<xcli_todo_dir>/` | **永不**被 `x todo` 默认行为读取或写入 |
| 环境变量 `XCLI_TODO_DIR` | 保留，向后兼容 |
| 默认路径跨平台 | `%LOCALAPPDATA%\x-cli\todo\` (Win) / `~/.local/share/x-cli/todo/` (Unix) |
| 目录权限 | 600（Unix） / 继承父目录 (Windows) |
| 自动创建 | 是（mkdir parents=True, exist_ok=True）|
| 加密 | 无（明文 + 文件权限）|

---

## 退出码速查

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 默认路径无法创建（权限 / IO 错误）|
| 2 | 参数错误（保留） |
| 3 | 任务不存在（保留）|
| 4 | 已归档（保留）|
| 5 | 数据完整性（保留）|

---

## 跨模块合约

```python
# core/paths.py
def xcli_todo_dir() -> Path:
    """Return the x-cli's TODO root (independent of any external system).
    
    - Honours XCLI_TODO_DIR env var (legacy compat)
    - Defaults to %LOCALAPPDATA%/x-cli/todo/ (Win) or ~/.local/share/x-cli/todo/ (Unix)
    - mkdir(parents=True, exist_ok=True) on first call
    - NEVER returns <xcli_todo_dir>/ (use x todo import --from to migrate)
    """

# core/storage.py
def _default_todo_dir() -> Path:
    """Delegate to xcli_todo_dir(). Old impl removed (used a hard-coded legacy path)."""
```

---

## 不做（v0.4.0）

- ❌ 自动从 `<xcli_todo_dir>/` 迁移（用户主动调 `x todo import`）
- ❌ 重命名 `XCLI_TODO_DIR` → `XCLI_TODO_DIR`（向后兼容优先）
- ❌ 加密 TODO 数据（跟 secret 一致，MVP 不加密）
- ❌ 在 x-cli's TODO 里反向写到源（解耦的代价，用户手动管理迁移）

---

*本文档是活文档，路径解析规则扩展同步更新。*