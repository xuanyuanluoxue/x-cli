# CLI 延迟分发行为规范

> 状态：已实现
> 范围：顶层入口、内建插件注册、版本依赖方向

## 背景

`x.py` 是用户每次执行 `x` 都会经过的入口。顶层帮助、版本查询和未知命令不需要加载 TODO、Secret、Web 等完整子系统；具体插件只应在用户选择对应子命令后加载。

## Scenario 1：导入入口不导入插件

**Given** 一个尚未导入 `x` 的全新 Python 进程

**When** 执行 `import x`

**Then** 导入成功

**And** `sys.modules` 中不存在 `plugins.todo`、`plugins.secret`、`plugins.diary`、`plugins.note`、`plugins.web`

## Scenario 2：版本查询走最短路径

**Given** 一个全新 Python 进程

**When** 执行 `x --version`

**Then** 输出 `core.version.__version__` 对应的版本

**And** 退出码为 0

**And** 不加载任何具体插件

## Scenario 3：顶层帮助不加载插件

**Given** 一个全新 Python 进程

**When** 执行 `x --help` 或 `x help`

**Then** 显示全部已注册子命令

**And** 退出码为 0

**And** 不加载任何具体插件

## Scenario 4：只加载被选择的插件

**Given** 一个全新 Python 进程

**When** 执行 `x note --help`

**Then** 分发给 `plugins.note.run`

**And** 不预加载 `plugins.todo`、`plugins.secret`、`plugins.diary`、`plugins.web`

## Scenario 5：未知命令不触发导入

**Given** 用户输入未注册子命令 `x unknown`

**When** 顶层入口校验子命令

**Then** 向 stderr 输出未知命令和支持列表

**And** 返回退出码 1

**And** 不尝试导入 `plugins.unknown` 或其他具体插件

## Scenario 6：插件契约损坏时明确失败

**Given** 注册表中的模块可以导入，但没有 callable `run`

**When** 分发器加载该插件

**Then** 抛出包含模块名与 `callable run` 的 `TypeError`

**And** 不静默忽略配置错误

## Scenario 7：core 不反向导入入口

**Given** Web health handler 需要返回版本

**When** handler 构造响应

**Then** 版本直接来自 `core.version`

**And** `core/**/*.py` 不导入 `x`

## 不变量

- 内建插件名单是静态白名单，不根据用户输入拼接任意模块路径。
- 延迟加载不得改变现有 help、stdout/stderr、退出码或配置初始化顺序。
- PyInstaller 必须显式收集延迟导入模块，不能为了打包方便恢复 eager imports。
