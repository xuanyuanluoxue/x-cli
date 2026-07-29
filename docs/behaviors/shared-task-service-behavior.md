# CLI / Web 共享任务服务行为

## 功能：两个入口共用任务业务后端

### 场景 1：CLI 与 Web 使用相同的应用服务

Given `x todo` 与 `x web` 同时提供任务操作
When 任一入口执行列表、详情、创建、更新、归档或统计
Then 入口应调用 `TaskService`
And `TaskService` 应调用 `TaskStore` 完成持久化
And Web handler 不应重新实现任务构造、ID 生成或领域默认值

### 场景 2：CLI 不依赖 Web 进程

Given Web 服务没有启动
When 用户执行 `x todo`
Then CLI 仍应直接调用本进程中的 `TaskService`
And CLI 不应请求 localhost HTTP API

### 场景 3：Web 不执行 CLI 子进程

Given Web 收到任务 API 请求
When handler 执行对应操作
Then Web 应直接调用本进程中的 `TaskService`
And Web 不应执行 `x todo` 子进程
And HTTP 状态码与 JSON 映射仍由 Web adapter 负责

### 场景 4：Web 可以落后于 CLI 独立交付

Given CLI 已通过 `TaskService` 增加新的任务能力
And Web 尚未提供该能力的页面或路由
When CLI 发布该功能
Then CLI 功能不应依赖 Web 同期实现
And 后续 Web 分支应复用已有 `TaskService` API
And 不应在 Web handler 中复制该业务规则

### 场景 5：保持旧的 WebServer 存储注入兼容

Given 测试或调用方只向 `WebServer` 传入 `store`
When WebServer 初始化
Then WebServer 应基于该 store 创建 `TaskService`
And `server.store` 应继续引用同一个 store

### 场景 6：拒绝冲突的依赖注入

Given 调用方同时传入 `store` 与 `task_service`
And 两者引用的 TaskStore 不相同
When WebServer 初始化
Then 应拒绝该配置
And 不应在未知存储上执行任务操作
