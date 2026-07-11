# x web 行为规格

> **目标读者**：接续开发的 AI agent
> **范围**：`x web` 子命令 — stdlib HTTP server + REST API + token auth
> **对应测试**：`tests/test_web_api.py`（单元 + 端到端）
> **状态**：🚧 开发中（feature/web-backend，2026-06-27）

---

## 存储与配置

**路径**：
- 静态资源：`core/web/static/`（前端 branch 会替换此目录）
- 配置：`xcli_data_dir()/web-token.txt`（v0.7.0 MVP **不持久化**，每次启动重新生成）

**Token 生成**：`secrets.token_urlsafe(32)`（32 字节 = 43 字符 base64）

**默认绑定**：`127.0.0.1:8421`（端口 8421 = "x-cli web" 键盘记忆）

---

## 场景 1：启动服务

**When**：
- `x web`

**Then**：
- 启动 HTTP server 在 127.0.0.1:8421
- stdout 打印服务地址 + token
- 不自动打开浏览器（用 `--no-browser=false` 才自动打开）

---

## 场景 2：访问健康检查无需 token

**Given**：服务已启动

**When**：
- `GET /api/health`（无 X-Web-Token header）

**Then**：
- 退出码 0
- HTTP 200
- Body: `{"status": "ok", "version": "0.6.0", "subsystems": ["todo", "secret"]}`

---

## 场景 3：API 请求缺 token → 401

**Given**：服务已启动，token = `abc123`

**When**：
- `GET /api/tasks`（无 X-Web-Token header）

**Then**：
- HTTP 401
- Body: `{"error": "missing token", "code": "missing_token"}`

---

## 场景 4：API 请求错 token → 401

**Given**：服务已启动，token = `abc123`

**When**：
- `GET /api/tasks` 带 `X-Web-Token: wrong`

**Then**：
- HTTP 401
- Body: `{"error": "invalid token", "code": "invalid_token"}`

---

## 场景 5：API 请求正确 token → 200

**Given**：服务已启动，token = `abc123`，仓库空

**When**：
- `GET /api/tasks` 带 `X-Web-Token: abc123`

**Then**：
- HTTP 200
- Body: `{"tasks": [], "count": 0}`

---

## 场景 6：列出任务 + 过滤

**Given**：仓库有 3 个任务（kemu1 pending / zizhushixi in_progress / old archived）

**When**：
- `GET /api/tasks?status=pending` 带正确 token

**Then**：
- HTTP 200
- Body 的 tasks 数组只含 kemu1
- count = 1

---

## 场景 7：获取单个任务

**Given**：仓库有任务 kemu1

**When**：
- `GET /api/tasks/kemu1` 带正确 token

**Then**：
- HTTP 200
- Body 含 task 对象，id = "kemu1"

---

## 场景 8：获取不存在的任务 → 404

**When**：
- `GET /api/tasks/nonexistent`

**Then**：
- HTTP 404
- Body: `{"error": "task not found", "code": "not_found", "id": "nonexistent"}`

---

## 场景 9：创建任务

**When**：
- `POST /api/tasks` body `{"name": "新任务", "priority": "high"}`

**Then**：
- HTTP 201
- Body 含新 task 对象
- 物理文件已创建在 `任务/新任务/TODO.md`

---

## 场景 10：创建任务缺 name → 400

**When**：
- `POST /api/tasks` body `{"priority": "high"}`

**Then**：
- HTTP 400
- Body: `{"error": "name is required", "code": "validation_error"}`

---

## 场景 11：创建任务重名 → 409

**Given**：仓库有任务 "kemu1"

**When**：
- `POST /api/tasks` body `{"name": "kemu1"}`

**Then**：
- HTTP 409
- Body: `{"error": "task already exists", "code": "duplicate", "name": "kemu1"}`

---

## 场景 12：更新任务字段

**Given**：仓库有任务 kemu1（status=pending）

**When**：
- `PATCH /api/tasks/kemu1` body `{"status": "in_progress"}`

**Then**：
- HTTP 200
- Body 的 task.status = "in_progress"
- 物理文件已更新

---

## 场景 13：归档任务

**Given**：仓库有任务 kemu1

**When**：
- `POST /api/tasks/kemu1/archive` body `{"reason": "done"}`

**Then**：
- HTTP 200
- Body 的 task.status = "archived", task.reason = "done"
- 物理文件已从 `任务/kemu1/` 移到 `归档/<date>-kemu1/`

---

## 场景 14：归档已归档任务 → 409

**Given**：任务 kemu1 已归档

**When**：
- `POST /api/tasks/kemu1/archive`

**Then**：
- HTTP 409
- Body: `{"error": "task already archived", "code": "duplicate"}`

---

## 场景 15：获取统计

**When**：
- `GET /api/tasks/stats`

**Then**：
- HTTP 200
- Body 含 total / by_status / by_priority / due_within_7_days / high_priority_active

---

## 场景 16：列出密钥（不含 value）

**Given**：DB 有 minimax 和 openai

**When**：
- `GET /api/secrets`

**Then**：
- HTTP 200
- Body 的 secrets 数组只含 name + category + updated_at
- **不含** value 字段（硬性约束）

---

## 场景 17：获取单个密钥（含 value + stderr 警告）

**Given**：DB 有 minimax，value = `sk-test`

**When**：
- `GET /api/secrets/minimax`

**Then**：
- HTTP 200
- Body 含完整对象（含 value）
- 服务端 stderr 输出 `🔐 警告：密钥已通过 Web API 输出到客户端`

---

## 场景 18：创建密钥

**When**：
- `POST /api/secrets` body `{"name": "minimax", "value": "sk-test", "category": "API"}`

**Then**：
- HTTP 201
- DB 新增 minimax 条目
- 文件已写入

---

## 场景 19：删除密钥 → 204

**Given**：DB 有 minimax

**When**：
- `DELETE /api/secrets/minimax`

**Then**：
- HTTP 204（无 body）
- DB 中 minimax 不存在

---

## 场景 20：路径穿越防护

**When**：
- `GET /../etc/passwd`（试图读后端系统文件）

**Then**：
- HTTP 404（或 403）
- **不**返回 `etc/passwd` 内容

---

## 场景 21：方法不允许

**When**：
- `DELETE /api/tasks`（该端点不允许 DELETE）

**Then**：
- HTTP 405
- Body: `{"error": "method not allowed", "code": "method_not_allowed"}`

---

## 场景 22：JSON 解析失败

**When**：
- `POST /api/tasks` body 不是合法 JSON

**Then**：
- HTTP 400
- Body: `{"error": "invalid JSON body", "code": "validation_error"}`

---

## 场景 23：服务优雅关闭（Ctrl+C）

**When**：
- 用户按 Ctrl+C

**Then**：
- HTTP server 停止接受新连接
- 已建立的连接处理完请求后关闭
- 进程退出码 0

---

## 不变量

| 项 | 值 |
|---|---|
| **默认 host** | `127.0.0.1`（绝不默认 0.0.0.0）|
| **默认 port** | `8421` |
| **token 长度** | 32 字节（base64 后 43 字符）|
| **token 持久化** | 不（每次启动重新生成；MVP 不写盘）|
| **静态资源根** | `core/web/static/` |
| **静态资源白名单** | 不限制（前端目录所有文件都可访问）|
| **路径穿越防护** | 必须：拒绝任何含 `..` 的路径 |
| **JSON 编码** | UTF-8 + `ensure_ascii=False`（中文不转义）|
| **Content-Type** | 所有 API 返回 `application/json; charset=utf-8` |
| **CORS** | MVP 不实现（同源：前后端同 8421 端口）|
| **HTTPS** | MVP 不实现（仅 localhost，明文即可）|

---

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 正常退出（Ctrl+C / 显式 stop）|
| 1 | 端口被占用 / 启动失败 |
| 2 | 参数错误 |

---

## 不做（v0.7.0）

- ❌ HTTPS / TLS（仅 localhost）
- ❌ 多用户支持 / 用户管理
- ❌ Session / Cookie（每次请求带 X-Web-Token 即可）
- ❌ 速率限制（个人工具，无滥用风险）
- ❌ WebSocket（只用 REST）
- ❌ CORS（前后端同源）
- ❌ token 持久化（每次启动重生成；要持久化用 `--token <固定值>`）
- ❌ 实时通知（前端轮询即可）

---

*本文件由 feature/web-backend 任务生成（2026-06-27），覆盖 `x web` 服务端的所有场景。前端 AI 实现前应理解但不实现本文件的端点（端点已实现）。*