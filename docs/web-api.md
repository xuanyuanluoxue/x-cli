# x-cli Web API 规格（v0.7.0）

> **目标读者**：前端 AI（实现） + 后端实现者 + 集成者
> **范围**：`x web` 子命令的 REST API
> **状态**：🚧 开发中（feature/web-backend，2026-06-27）
> **基础**：v0.6.0 的 `x todo` + `x secret` CLI 命令全部 API 化

---

## 1. 总览

`x web` 启动一个 stdlib HTTP server（**0 第三方依赖**），把 `TaskStore` + `SecretStore` 暴露为 REST API。浏览器前端通过这些端点读写数据。

**安全模型**：
- 默认绑定 `127.0.0.1`（仅本机可访问）
- 启动时生成 **一次性随机 token**（32 字节 base64），打印到 stdout
- 浏览器必须输入 token → 存 `localStorage` → 后续请求带 `X-Web-Token` header
- 后端校验所有 `/api/*` 请求的 header；缺失/错误 → 401
- 可选 `--host 0.0.0.0` + `--port 8421` 暴露给局域网（仍需 token）

**⚠️ 高风险**：`GET /api/secrets/<name>` 返回明文 value。每次调用 stdout 打警告（与 `x secret get` 一致）。

---

## 2. 启动

```bash
x web                              # 默认 127.0.0.1:8421
x web --host 0.0.0.0               # 暴露给局域网（需 token）
x web --port 9000                  # 自定义端口
x web --token my-secret-token      # 自定义 token（默认随机生成）
x web --no-browser                 # 不自动打开浏览器
```

启动后输出：

```
🌐 x web 服务已启动
   地址:  http://127.0.0.1:8421
   Token: a1b2c3d4e5f6...（32 字节）
   停止:  Ctrl+C

🔐 请在浏览器输入上面的 Token（首次访问会提示）
```

---

## 3. 认证

所有 `/api/*` 端点要求请求头：

```
X-Web-Token: <token>
```

校验失败返回 `401 Unauthorized` + JSON body：

```json
{"error": "invalid or missing token"}
```

**例外**（不需要 token）：
- `GET /api/health` — 健康检查
- `GET /` 或 `GET /static/*` — 前端静态资源（HTML/CSS/JS）

---

## 4. 端点清单（11 个）

### 4.1 系统

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/health` | 健康检查（无需 token）|

### 4.2 任务（todo）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/tasks` | 列出任务（支持 `?status=in_progress&priority=high&tag=驾照`）|
| `GET` | `/api/tasks/<id>` | 获取单个任务 |
| `POST` | `/api/tasks` | 创建任务（body: `{name, priority?, deadline?, tags?}`）|
| `PATCH` | `/api/tasks/<id>` | 更新任务字段（body: `{status?, priority?, deadline?, tags?}`）|
| `POST` | `/api/tasks/<id>/archive` | 归档任务（body: `{reason?}`）|
| `GET` | `/api/tasks/stats` | 统计信息 |

### 4.3 密钥（secret）

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/secrets` | 列出密钥（**不含 value**）|
| `GET` | `/api/secrets/<name>` | 获取 value（**明文** + stderr 警告）|
| `POST` | `/api/secrets` | 创建密钥（body: `{name, value, category?, note?}`）|
| `PATCH` | `/api/secrets/<name>` | 更新密钥（body: `{value?, category?, note?}`）|
| `DELETE` | `/api/secrets/<name>` | 删除密钥 |

---

## 5. 端点详细规格

### 5.1 `GET /api/health`

**Request**：无 body，无 header 要求。

**Response 200**：
```json
{
  "status": "ok",
  "version": "0.6.0",
  "subsystems": ["todo", "secret"]
}
```

---

### 5.2 `GET /api/tasks`

**Query 参数**（全部可选）：
- `status` — 过滤状态（pending / in_progress / blocked / waiting）
- `priority` — 过滤优先级（high / medium / low）
- `tag` — 精确匹配标签
- `include_archived` — `true` 包含已归档（默认 false）

**Response 200**：
```json
{
  "tasks": [
    {
      "id": "kemu1",
      "name": "科目一模拟考",
      "status": "pending",
      "priority": "high",
      "deadline": "2026-08-31",
      "tags": ["驾照", "暑假"],
      "created": "2026-03-27",
      "updated": "2026-06-15",
      "folder": "任务/科目一模拟考",
      "archived": false,
      "reason": null
    }
  ],
  "count": 1
}
```

**错误**：
- `400` — 非法 status / priority 值
- `401` — 缺/错 token

---

### 5.3 `GET /api/tasks/<id>`

**Response 200**：单个 task 对象（同上结构但不带 `count` 包装）。

**错误**：
- `404` — 任务不存在（body: `{"error": "task not found", "id": "kemu1"}`）
- `401` — 缺/错 token

---

### 5.4 `POST /api/tasks`

**Request body**：
```json
{
  "name": "新任务",
  "priority": "high",      // 可选，默认 medium
  "deadline": "2026-09-01", // 可选
  "tags": ["标签1", "标签2"] // 可选
}
```

**Response 201**：新创建的 task 对象。

**错误**：
- `400` — name 为空 / 非法 priority / 非法 deadline
- `409` — name 已存在
- `401` — 缺/错 token

---

### 5.5 `PATCH /api/tasks/<id>`

**Request body**（至少 1 个字段）：
```json
{
  "status": "in_progress",
  "priority": "low",
  "deadline": null,         // null = 清除
  "tags": ["新标签"]        // 完全替换
}
```

**Response 200**：更新后的 task 对象。

**错误**：
- `400` — body 空 / 非法字段值
- `404` — 任务不存在
- `401` — 缺/错 token

---

### 5.6 `POST /api/tasks/<id>/archive`

**Request body**（可选）：
```json
{"reason": "done"}  // 默认 done，可选 cancelled/expired/failed
```

**Response 200**：归档后的 task 对象（status=archived, reason=<reason>）。

**错误**：
- `400` — 非法 reason
- `404` — 任务不存在
- `409` — 任务已归档
- `401` — 缺/错 token

---

### 5.7 `GET /api/tasks/stats`

**Response 200**：
```json
{
  "total": 34,
  "by_status": {
    "pending": 2,
    "in_progress": 2,
    "blocked": 0,
    "waiting": 0,
    "archived": 30
  },
  "by_priority": {
    "high": 17,
    "medium": 2,
    "low": 15
  },
  "due_within_7_days": 1,
  "high_priority_active": 3
}
```

---

### 5.8 `GET /api/secrets`

**Response 200**：
```json
{
  "secrets": [
    {
      "name": "minimax",
      "category": "接口密钥",
      "updated_at": "2026-06-21T12:34:56"
    }
  ],
  "count": 1
}
```

**关键约束**：`value` 字段**绝不**返回（与 CLI `x secret list` 一致）。

---

### 5.9 `GET /api/secrets/<name>`

**Response 200**：
```json
{
  "name": "minimax",
  "category": "接口密钥",
  "value": "sk-test1234",
  "note": "Migrated from 接口密钥.md",
  "created_at": "2026-06-21T12:34:56",
  "updated_at": "2026-06-21T12:34:56"
}
```

**副作用**：每次调用 stderr 打警告（与 `x secret get` 一致）：
```
🔐 警告：密钥已通过 Web API 输出到客户端
```

**错误**：
- `404` — 不存在
- `401` — 缺/错 token

---

### 5.10 `POST /api/secrets`

**Request body**：
```json
{
  "name": "minimax",
  "value": "sk-test1234",
  "category": "接口密钥",   // 可选，默认 "default"
  "note": "备注"             // 可选
}
```

**Response 201**：新创建的 secret 对象（同 GET 单个结构）。

**错误**：
- `400` — name 为空 / value 为空
- `409` — name 已存在
- `401` — 缺/错 token

---

### 5.11 `PATCH /api/secrets/<name>`

**Request body**（至少 1 个字段）：
```json
{"value": "sk-new", "category": "新分组", "note": null}
```

**Response 200**：更新后的 secret 对象。

**错误**：
- `400` — body 空
- `404` — 不存在
- `401` — 缺/错 token

---

### 5.12 `DELETE /api/secrets/<name>`

**Response 204**：无 body。

**错误**：
- `404` — 不存在
- `401` — 缺/错 token

---

## 6. 静态资源

`GET /` → 返回 `core/web/static/index.html`

`GET /<path>` → 返回 `core/web/static/<path>`（防止路径穿越）

静态文件目录在 backend 阶段是占位的 `index.html`（"Frontend coming soon"）。前端 branch 替换整个 `core/web/static/` 目录。

---

## 7. 错误格式

所有非 2xx 响应统一返回 JSON：

```json
{
  "error": "<human readable message>",
  "code": "<machine readable error code>"
}
```

常见 error code：
- `missing_token` — 缺 X-Web-Token header
- `invalid_token` — token 不匹配
- `not_found` — 资源不存在
- `validation_error` — 参数校验失败
- `duplicate` — 资源已存在（创建时）
- `internal_error` — 服务端异常

---

## 8. CORS

默认 `Access-Control-Allow-Origin: http://127.0.0.1:8421`（仅本机）。

如果要跨域访问（比如前端 dev server 在不同端口），需要：
- 启动时加 `--cors-origin <url>` 参数（v0.7.x 不实现，先记 TODO）

**MVP 阶段**：前后端同源（同 8421 端口），不需要 CORS。

---

## 9. 版本与向后兼容

- API URL 不带版本号（`/api/tasks`，不是 `/api/v1/tasks`）
- 字段添加 = 非破坏性（前端忽略未知字段）
- 字段重命名/删除 = 破坏性，需要 v2
- 第一个稳定版本是 v0.7.0

---

## 10. 实施阶段拆分

| 阶段 | 分支 | 内容 |
|------|------|------|
| **Backend (本次)** | `feature/web-backend` | 上述所有后端代码 + 测试 + 占位 `index.html` |
| Frontend (另议) | `feature/web-frontend`（基于 feature/web-backend）| 替换 `core/web/static/`，见 `docs/web-frontend-plan.md` |

---

*本文件由 feature/web-backend 任务生成（2026-06-27）。前端 AI 实现前必读。*