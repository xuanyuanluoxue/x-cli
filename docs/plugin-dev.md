# Plugin Development Guide（v0.6.0）

> **目标读者**：想给 x-cli 加新子命令（如 `x skill` / `x agent` / `x system`）的人
> **前置阅读**：[AGENTS.md](../AGENTS.md)、[docs/architecture.md](architecture.md)
> **状态**：v0.6.0 有 3 个插件（todo / secret / web），本指南总结模式

---

## 1. 插件契约（Plugin Contract）

x-cli v0.4.0 起所有子命令都走插件机制。每个 plugin 是一个**单文件 Python 模块**，满足两个约定：

### 1.1 强制接口

```python
# plugins/<name>.py

def register(parser: argparse._SubParsersAction) -> None:
    """在 ``x`` 主入口上注册本插件的子命令。
    
    Args:
        parser: ``x`` 顶层 subparsers。所有 ``add_parser`` 调用
            都用 ``parser.add_parser(name, ...)``，name 必须是插件名。
    
    约定：
    - 在此函数里定义所有 action 的 subparser + 参数
    - **不要**直接调 ``parser.parse_args()``
    - 多个 action 通过 if/elif 分发
    """
    sp = parser.add_parser("todo", help="TODO 任务管理")
    todo_sp = sp.add_subparsers(dest="todo_action", required=True)
    
    sp_list = todo_sp.add_parser("list", help="列出 TODO 任务")
    # ... 定义参数
    

def run(args: argparse.Namespace) -> int:
    """执行子命令并返回退出码。
    
    Args:
        args: ``x`` 主入口的 Namespace（顶层有 todo / secret / web 等）
            + ``register`` 阶段注入的子参数
    
    Returns:
        退出码（0 成功 / 2 参数错 / 3 不存在 / 4 已归档 / 5 数据完整性问题）
        见 [AGENTS.md §6.4 退出码约定](../AGENTS.md)
    """
    # 1. 分发到具体 action
    if args.todo_action == "list":
        return _todo_list(args)
    if args.todo_action == "add":
        return _todo_add(args)
    # ...
    
    # 2. 未知 action（理论上 argparse 必填挡住了，但保险）
    return _not_implemented(args.todo_action)
```

### 1.2 注册到主入口

在 `x.py` 顶部加 import + `SUBCOMMAND_HANDLERS` 字典加一条目（**仅 2 行**）：

```python
# x.py
from plugins import todo as _todo_plugin
from plugins import secret as _secret_plugin
from plugins import web as _web_plugin    # 新插件

SUBCOMMAND_HANDLERS: dict[str, Callable[[Sequence[str]], int]] = {
    "todo": _todo_plugin.run,
    "secret": _secret_plugin.run,
    "web": _web_plugin.run,    # 新插件
}
```

**关键**：`SUBCOMMAND_HANDLERS` 的 **key** 必须跟 `register()` 里 `add_parser(name, ...)` 的 **name** 一致。

### 1.3 不要做的事

- ❌ 不要 import `x.py` 内部（会循环依赖）。需要全局配置 / 日志，**直接** import `core.config` / `core.logging`
- ❌ 不要在 `register()` 里写实现逻辑（只定义 argparse）
- ❌ 不要在 `run()` 里调 `sys.exit()`，**返回**退出码
- ❌ 不要打印到 stdout 用于错误（**用 stderr** + emoji 标记）
- ❌ 不要吞异常（让调用者看到 traceback 才知道哪里炸了）

---

## 2. 加新插件的 Checklist（6 步）

> 跟 [docs/testing.md §6](testing.md) 的 BDD+TDD 6 步流程同步

| Step | 操作 | 文件 | Commit 前缀 |
|---|---|---|---|
| 1 | 在 `COMMANDS.md` ⏳ 区加新子命令（标 P0/P1/P2/P3）| `COMMANDS.md` | `docs` |
| 2 | 写 BDD 行为规格 | `docs/behaviors/<name>-<action>-behavior.md` | `docs(behaviors)` |
| 3 | 写 TDD 测试（先 Red）| `tests/test_<name>_<action>.py` | `test(<name>)` |
| 4 | 写 `plugins/<name>.py`（`register` + `run` + handlers）| `plugins/<name>.py` | `feat(<name>)` |
| 5 | 在 `x.py:SUBCOMMAND_HANDLERS` 注册（1 行 + 1 import）| `x.py` | `fix(x)` or `feat(x)` |
| 6 | 写 e2e 测试 + e2e 帮助列名 test | `tests/test_e2e_<name>.py` | `test(e2e)` |

**禁止**：
- ❌ **不要**在 `COMMANDS.md` 加命令（user-only 文件）
- ❌ **不要**跳过 BDD / TDD Red 阶段
- ❌ **不要**实现完不改 `COMMANDS.md` ⏳ → ✅

### 2.1 命名约定

| 元素 | 约定 | 示例 |
|---|---|---|
| plugin 文件 | 全小写 + 下划线 | `plugins/my_feature.py` |
| 顶层子命令 | 单数名词 | `todo` / `secret` / `web`（不是 `todos`）|
| action | 动词（单数）| `list` / `add` / `archive` / `tag`（不是 `listing`）|
| 内部 handler | `_todo_<action>` | `_todo_add` / `_todo_tag` |
| BDD 文件 | `<top>-<action>-behavior.md` | `todo-add-behavior.md` |
| 测试文件 | `test_<top>_<action>.py` | `test_todo_add.py` |

---

## 3. 真实案例：3 个插件的演进

### 3.1 `x todo`（v0.2.0 出生，最复杂）

**出生**（v0.2.0，Phase 1 MVP）：
- 5 个 action（list / add / update / archive / stats）
- **直接 inline 在 `x.py`**（约 500 行）
- YAML frontmatter 手写 parser（`core/parser.py`）
- 文件系统存储（`core/storage.py`）

**演进**：
- v0.4.0：拆出 `plugins/todo.py`，`x.py` 只剩 dispatch
- v0.4.x：加 4 个 action（restore / search / done / import）— **所有 action 走 `TaskStore` 同一个存储路径**
- v0.4.x：`x todo init` — bootstrap 独立 TODO dir
- v0.6.0 P1：加 `x todo tag`（本次 backend-polish 加的）
- v0.6.0：`x todo list --auto-archive`（opt-in 过期自动归档）

**经验**：
- YAML frontmatter 手写 parser 是关键决策（不引 PyYAML，未知字段 round-trip 不丢）
- 单一存储路径（`TaskStore.update_task`）让加 action 容易（`tag` 复用同一个 update 路径）
- 退出码约定（0/2/3/4/5）在 v0.2.0 就定，**所有 action 复用** — 避免每个 action 自己定错码

### 3.2 `x secret`（v0.3.0 出生，独立性最强）

**出生**（v0.3.0，Phase 3）：
- 独立 JSON DB（`%LOCALAPPDATA%\x-cli\secrets.json`）— **不**跟 todo 共用存储
- 8 个 action（list / get / set / update / rm / search / import / export）
- 核心隔离：跟 legacy TODO system 目录完全解耦

**经验**：
- **独立性优先**：secret 数据有自己的存储，不复用 todo 的 TaskStore
- `get` 命令含剪贴板复制（pyperclip）+ stderr 警告
- value 字段默认不输出到 stdout（安全）

**教训**：
- Phase 3 拆太多并行 task（5 个 worker 同时改 x.py），有 merge 冲突
- 1 个 task 搞定 4 个 cold-start + 4 个 verify

### 3.3 `x web`（v0.6.0 出生，最年轻）

**出生**（v0.6.0）：
- 3 个 action（start / stop / status）— 跟 HTTP server 控制
- 后端：基于 `http.server`（stdlib-only）做的内嵌 HTTP server
- 鉴权：Bearer token（跟 `core.web.auth` 配合）
- 路由：health + tasks REST + secrets REST + 静态前端
- **本次 backend-polish 修了 v0.6.0 的注册 bug**

**经验**：
- web 是 v0.6.0 **第一个** 走"前端 / 后端两个分支并行开发"的子命令
- 前端分支（feature/web-frontend）在 `.design/preview/x-web-preview/` + `docs/prompts/web-frontend-handoff.md` 出设计稿
- 后端分支（feature/web-backend）实装 `core/web/*` + `plugins/web.py`
- 最后 `dev` 分支 merge 两次（`f1bdb06` 前端 + `c065c6b` 后端）

**教训**：
- **前端 / 后端分支** 模式有效，但需要明确"前端 / 后端"边界（写进 `docs/prompts/web-frontend-handoff.md`）
- **注册 bug 没在原 PR 修**：因为插件在 `plugins/web.py` 写好但**没人加 `SUBCOMMAND_HANDLERS` 条目** — 是 dev merge 时的疏忽。本次 backend-polish 收口

---

## 4. 关键模式总结

### 4.1 单文件插件结构

```
plugins/<name>.py
├── 模块 docstring（说明插件用途、版本、相关 BDD）
├── imports（stdlib first, 第三方, core, 同 package 内的 plugin）
├── 常量（Xxx_ACTIONS tuple、退出码 helper）
├── register(parser)  ←── 唯一对外接口 1
├── run(args)         ←── 唯一对外接口 2
│   └── if/elif 分发到具体 action
├── _xxx_<action>(args)  ←── 内部 handler（每个 action 一个）
│   ├── 参数校验
│   ├── 调 core 库
│   ├── 错误处理（exit code + stderr 友好提示）
│   └── 输出（stdout 成功 + emoji）
└── 私有 helper（_format_xxx / _validate_xxx）
```

### 4.2 退出码约定

| 码 | 含义 | 用法 |
|---|---|---|
| 0 | 成功 | 所有 action 默认 |
| 1 | 通用错误 | 未知子命令（x 主入口用）|
| 2 | 参数错误 | argparse 标准 + handler 自定义（缺参 / 非法值 / 互斥）|
| 3 | 资源不存在 | 任务 / 配置项 / 文件不存在 |
| 4 | 资源已存在或不可改 | 已归档 / 重复 set / 已删除 |
| 5 | 数据完整性问题 | YAML 解析失败 / 归档碰撞 / checksum 不匹配 |

### 4.3 stdout vs stderr

| 类型 | 通道 | 例子 |
|---|---|---|
| 成功结果 | stdout | `✅ 任务已创建：kemu1（ID: kemu1）` |
| 错误 | stderr | `❌ 任务不存在：nonexistent-id` |
| 提示（次要）| stderr | `💡 提示：运行 'x todo list' 查看现有任务 ID` |
| 警告 | stderr | `⚠️  任务已归档` |
| debug | logging（不是 print）| `logging.debug("TaskStore.update_task called for %s", id)` |

---

## 5. 反模式（不要这样写）

```python
# ❌ 反模式 1：sys.exit() 而不是 return
def _my_action(args):
    if not args.id:
        print("❌ 缺 id", file=sys.stderr)
        sys.exit(2)  # 错！应该 return 2

# ✅ 正确
def _my_action(args):
    if not args.id:
        print("❌ 缺 id", file=sys.stderr)
        return 2
```

```python
# ❌ 反模式 2：循环 import x
# plugins/foo.py
from x import SUBCOMMAND_HANDLERS  # 错！循环依赖

# ✅ 正确：直接 import 自己需要的东西
# plugins/foo.py
from core.config import load_config
```

```python
# ❌ 反模式 3：注册到 SUBCOMMAND_HANDLERS 但 name 不一致
# plugins/foo.py
def register(parser):
    parser.add_parser("foo", help="...")  # name="foo"

# x.py
SUBCOMMAND_HANDLERS = {
    "fooo": _foo_plugin.run,  # 错！typo
}
# 结果：x foo 报"未知子命令"

# ✅ 正确：name 跟 key 完全一致
```

```python
# ❌ 反模式 4：handler 跨层调 core 的同时改 storage
# plugins/foo.py
def _foo_action(args):
    store = TaskStore()
    # 调 core/storage 的 update_task
    store.update_task(args.id, tags=args.tags)
    # 然后**手写文件**（破坏手写 parser round-trip）
    (store.active_dir / args.id / "TODO.md").write_text(custom_text)

# ✅ 正确：所有写入走 core/storage
```

---

*Last updated: 2026-06-28*
