# ADR-0001：保留模块化单体并采用延迟插件分发

- **状态：** Accepted
- **日期：** 2026-07-17
- **决策者：** Xavier / Codex

## 背景

x-cli 是单用户、本地优先的 Windows CLI，目前包含 todo、secret、diary、note 和 web 五个内建子系统。运行代码约 354 KB，第三方运行依赖为零；当前规模不需要跨进程服务或微服务。

现有 `x.py` 在模块导入阶段加载所有插件，并为历史测试重导出大量插件私有函数。因此，即使用户只执行 `x --version`，也会加载 TODO 存储、Secret 和本地 HTTP 服务等无关模块。`core.web.handlers.health` 还从 `x` 读取版本，形成 core → entry point 的反向依赖。

## 决策

1. 保持 Python 3.10+、stdlib-only 的模块化单体。
2. 在 `core.dispatch` 维护“子命令 → 完整模块名”的静态白名单。
3. `x.py` 只在确认子命令合法且完成全局配置后，通过 `importlib.import_module` 加载选中的插件。
4. 插件继续以 callable `run(args) -> int` 作为稳定入口。
5. `core` 不得导入 `x`；测试私有实现时直接从所属模块导入，不再依赖 `x.py` 的兼容重导出。
6. PyInstaller 通过 spec 的 hidden imports / collection 配置发现内建插件。

## 选择理由

- 静态白名单阻止根据不可信输入导入任意 Python 模块。
- 延迟导入让 `--version`、`--help` 和未知命令保持轻量。
- 单进程模块边界足以支撑个人 CLI，部署和故障面远小于后台服务拆分。
- 保留插件 `run` 契约，不改变用户命令或数据格式。

## 被拒绝的方案

### Go/Rust 全量重写

可能得到更小的原生启动延迟，但需要重新实现 YAML frontmatter、Windows 路径、Web UI、Secret 行为和 700 多个测试所覆盖的契约。当前收益不足以覆盖迁移风险。

### 扫描 `plugins/` 自动发现

减少一行手工注册，但模块顺序、打包发现、错误提示和安全审计更复杂。只有五个内建插件，静态注册更清楚。

### 拆成常驻后台服务

未来提醒或同步功能可能需要守护进程，但当前命令仍适合直接本地执行。后台能力应作为可选进程，通过稳定的 core API 复用逻辑，而不是把现有 CLI 变成远程客户端。

## 后果

### 正面

- 顶层入口更轻，依赖方向变为 entry point → dispatch → selected plugin → core。
- 插件故障只在调用对应命令时暴露。
- `x.py` 更接近项目规范要求的纯入口。

### 负面

- 静态分析工具和 PyInstaller 不一定自动发现字符串形式的导入，需要发行测试保护。
- 插件模块名或 `run` 契约错误会从导入期推迟到命令执行期。
- 现有直接从 `x` 导入私有函数的测试需要迁移。

## 失败模式与缓解

- **模块不存在：** 保留原始 `ModuleNotFoundError` 上下文，发行测试逐个执行插件 help。
- **缺少 callable run：** 分发器抛出带模块名的明确 `TypeError`。
- **PyInstaller 漏包：** spec 显式收集 `plugins`，EXE 冒烟覆盖 `--version`、note help 和 Web 首页。
- **循环依赖：** 架构测试禁止 `core` 导入 `x`，禁止 `x.py` 静态导入具体插件。

## 后续复审条件

只有当出现严格的原生冷启动目标、跨平台单文件体积目标，或常驻后台成为产品核心且 Python 运行成本被实测证明不可接受时，才重新评估语言重写。
