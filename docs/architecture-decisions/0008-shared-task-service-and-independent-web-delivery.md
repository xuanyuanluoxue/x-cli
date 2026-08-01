# ADR 0008：共享任务服务与 Web 独立交付

- 状态：已接受
- 日期：2026-07-29

## 背景

CLI 的任务能力远多于 Web。现有 Web task handler 直接调用 `TaskStore`，
并自行实现任务构造、ID 生成、字段校验、过滤和归档默认值。CLI 同时在
`plugins/todo_*.py` 中维护相同或更完整的规则。继续按入口分别实现会造成
默认值、校验和错误语义漂移。

Web 需要允许落后于 CLI 并在短期分支中独立开发，但“独立交付”不能变成
“独立复制一套后端”。CLI 也不能依赖 Web 服务是否启动。

## 决策

1. 新增 `core.task_service.TaskService`，依赖方向固定为：

   ```text
   CLI adapter ─┐
                ├─> TaskService ─> TaskStore ─> TODO.md
   Web adapter ─┘
   ```

2. `TaskService` 是协议无关的应用服务。它负责任务对象构造、ID 与默认值、
   查询过滤以及存储操作的统一入口；不包含 argparse、stdout、CLI 退出码、
   HTTP 状态码或 JSON 响应。
3. `TaskStore` 继续负责 Markdown/frontmatter 解析、未知字段往返、目录布局
   和原子文件操作。
4. CLI 新任务能力应先形成可测试的 `TaskService` API，再由 CLI adapter
   映射参数和输出。Web 可以不在同一版本提供页面或路由。
5. Web 后续实现该能力时，直接复用已有 `TaskService` API；Web 分支只新增
   HTTP adapter、前端页面和必要的协议测试，不复制业务规则。
6. WebServer 支持注入 `TaskService`；保留 `store` 别名以兼容既有调用方和
   测试。若同时注入的 service 与 store 不一致，应立即报错。

## 备选方案

- **Web 执行 `x todo` 子进程**：依赖 stdout、退出码和命令行转义，性能与错误
  映射脆弱，否决。
- **CLI 调用 Web REST API**：CLI 会依赖后台进程、端口与认证，否决。
- **CLI 与 Web 分别直接调用 TaskStore**：入口会继续复制应用规则，否决。
- **立即让 Web 追平全部 CLI 功能**：扩大本次风险，且违背 Web 可独立交付的
  目标，否决。
- **更换为独立 Web 框架或数据库**：无法解决业务规则重复，并引入不必要迁移，
  否决。

## 影响

- CLI 和 Web 继续使用同一套 Python stdlib-only 后端。
- Web 功能数量可以少于 CLI，但已实现功能与 CLI 共用业务入口。
- 新 CLI 功能需要区分应用逻辑和终端展示，早期改动略多，后续 Web 接入更简单。
- 现有复杂 TODO handler 可按功能逐步迁移；任何新功能不得继续把业务规则只写在
  Web handler 中。

## 不变量

- CLI 无需启动 Web；Web 不执行 CLI 子进程。
- `core` 不导入 `plugins` 或 `x`。
- HTTP 状态码与 CLI 退出码分别属于各自 adapter。
- 未知 frontmatter 字段继续通过 `Task.extra` 往返保留。
- 不改变用户数据格式、默认存储位置或 Python 零运行时依赖。
