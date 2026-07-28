# x-cli Web API 规格（v0.7.0）

> **目标读者**：前端 AI（实现） + 后端实现者 + 集成者
> **范围**：`x web` 子命令的 REST API
> **状态**：✅ 已实现（Web 前后端，2026-07-18）
> **基础**：v0.6.0 的 `x todo` + `x secret` CLI 命令全部 API 化

---

## 1. 总览

`x web` 启动一个 stdlib HTTP server（**0 第三方依赖**），把 `TaskStore` 与共享的 `SecretService` 暴露为 REST API。密钥 service 与 CLI 共用同一个 `SecretStore` 持久化边界，浏览器前端通过这些端点读写数据。

**安全模型**：
- 默认绑定 `127.0.0.1`（仅本机可访问）
- 默认 `web_auth: false`，不生成 Token，浏览器直接访问 API
- 配置 `web_auth: true` 时生成一次性随机 Token（32 字节 base64）并打印到 stderr
- 认证开启时，浏览器保存 Token 到 `localStorage`，请求携带 `X-Web-Token`
- 认证开启时，后端校验所有受保护的 `/api/*` 请求；缺失/错误 → 401
- 显式 `--token <value>` 会忽略关闭状态并为本次运行开启认证
- 可用 `--host 0.0.0.0` 暴露给局域网；无认证模式会打印风险警告
- 密钥查看/编辑安全确认默认开启；可保存“不再提示”，再通过配置文件恢复

**⚠️ 高风险**：`GET /api/secrets/<name>` 返回全部字段明文。每次调用 stderr 打警告（与 `x secret get` 一致）。

---

## 2. 启动

```bash
x web                              # 默认 127.0.0.1:8421，无认证
x web --host 0.0.0.0               # 暴露给局域网（建议先开启认证）
x web --port 9000                  # 自定义端口
x web --token my-secret-token      # 本次运行显式开启认证
x web --no-browser                 # 不自动打开浏览器
x web --auto-token-url             # 认证开启时自动把 Token 交给浏览器
```

启动后输出：

```
🌐 x web 服务已启动
   地址: http://127.0.0.1:8421
   认证: 关闭（浏览器可直接访问）
   停止: Ctrl+C

🌐 已关闭 Token 验证；任务和密钥可由本机浏览器直接访问
```

要默认开启认证，编辑 `%LOCALAPPDATA%\x-cli\config.yaml`（Unix 为
`~/.local/share/x-cli/config.yaml`）：

```yaml
web_auth: true
```

密钥确认偏好使用同一个配置文件：

```yaml
# true = 查看/编辑密钥明文前弹出安全确认
web_secret_confirmation: true
```

在确认框勾选“不再提示”会把它保存为 `false` 并立即生效。要恢复，改回
`true` 后重启 `x web`。

---

## 3. 认证

默认模式不要求认证。`web_auth: true` 或显式 `--token` 开启认证后，除健康检查
和静态资源外的 `/api/*` 端点要求请求头：

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

## 4. 端点清单（13 个）

### 4.1 系统

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/health` | 健康检查（无需 token；返回能力字段）|
| `PATCH` | `/api/preferences` | 保存受限的 Web 偏好（认证开启时需要 token）|

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
| `GET` | `/api/secrets` | 列出密钥（**不含 fields/value**）|
| `GET` | `/api/secrets/<name>` | 获取全部 fields（**明文** + stderr 警告）|
| `POST` | `/api/secrets` | 创建密钥（`fields` 或兼容 `value`，二选一）|
| `PATCH` | `/api/secrets/<name>` | 整体替换 `fields`，或兼容更新主密钥 `value` |
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
  "subsystems": ["todo", "secret"],
  "auth_required": false,
  "secret_confirmation_required": true
}
```

### 5.2 `PATCH /api/preferences`

只允许保存密钥安全确认偏好，不是通用配置写入接口。

**Request**：

```json
{"secret_confirmation_required": false}
```

**Response 200**：

```json
{"preferences": {"secret_confirmation_required": false}}
```

后端原子更新当前有效配置文件中的 `web_secret_confirmation`，保留注释、未知字段和其他设置，并立即更新当前服务状态。

**错误**：
- `400` — body 缺字段、存在额外字段或值不是 JSON boolean
- `401` — 认证开启时缺少或提供错误 token
- `500` — 配置写入失败；运行时状态不变

> 后续章节编号保持历史兼容；本端点是新增的系统端点。

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

**关键约束**：`fields` 和 `value` 字段**绝不**返回（与 CLI `x secret list` 一致）。

---

### 5.9 `GET /api/secrets/<name>`

**Response 200**：
```json
{
  "secret": {
    "name": "123pan.webdav",
    "category": "123pan",
    "fields": [
      {"label": "URL", "kind": "text", "value": "https://webdav.example.test", "primary": false},
      {"label": "账号", "kind": "text", "value": "user@example.test", "primary": false},
      {"label": "密码", "kind": "secret", "value": "example-password", "primary": true}
    ],
    "value": "example-password",
    "note": "WebDAV",
    "created_at": "2026-07-19T12:34:56",
    "updated_at": "2026-07-19T12:34:56"
  }
}
```

`value` 是主密钥的向后兼容别名；新客户端应读取 `fields`。字段约束：1–50 个，
`label` 长度 1–64 且忽略大小写后唯一，`kind` 只能是 `text` / `secret`，值不能为空；
必须且只能有一个 `primary: true`，且该字段必须是 `secret`。

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
  "name": "123pan.webdav",
  "category": "123pan",
  "note": "WebDAV",
  "fields": [
    {"label": "URL", "kind": "text", "value": "https://webdav.example.test", "primary": false},
    {"label": "密码", "kind": "secret", "value": "example-password", "primary": true}
  ]
}
```

兼容旧客户端的单值请求仍可使用：
```json
{"name": "minimax", "value": "sk-test1234", "category": "接口密钥"}
```

`fields` 与 `value` 不可同时提供。`value` 会映射为一个名为“密钥”的主密钥字段。

**Response 201**：新创建的 secret 对象（同 GET 单个结构）。

**错误**：
- `400` — name 为空、未提供 `fields/value`、同时提供二者或字段校验失败；错误响应不回显字段值
- `409` — name 已存在
- `401` — 缺/错 token

---

### 5.11 `PATCH /api/secrets/<name>`

**Request body**（至少 1 个受支持字段）：
```json
{
  "fields": [
    {"label": "Endpoint", "kind": "text", "value": "https://new.example.test", "primary": false},
    {"label": "Token", "kind": "secret", "value": "new-token", "primary": true}
  ],
  "category": "新分组"
}
```

传 `fields` 时会进行完整校验并原子替换整组字段，顺序按数组保留；校验失败时旧记录
完全不变。兼容请求 `{"value": "sk-new"}` 只更新当前主密钥，不删除其他字段。
`fields` 与 `value` 同样不可同时提供。

**Response 200**：更新后的 secret 对象。

**错误**：
- `400` — body 空、无受支持字段、同时提供 `fields/value` 或字段校验失败；错误响应不回显字段值
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

静态目录包含由 `web/` 下 Vue 3 + Vite 源码生成的前端产物：
`index.html` 提供 app shell，`assets/` 保存带内容哈希的 JavaScript 和 CSS。
构建产物不请求 CDN、Web Font 或第三方脚本，因此安装后的正常运行只依赖
`x web` 自身的静态服务，不要求用户安装 Node.js。

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
- `missing_token` — 认证开启时缺 X-Web-Token header
- `invalid_token` — 认证开启时 token 不匹配
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

## 10. 当前实现位置

| 部分 | 位置 | 状态 |
|------|------|------|
| Backend | `core/web/` + `core/web/handlers/` | 已实现并由 `tests/test_web_api.py` 覆盖 |
| Frontend | `core/web/static/` | 已实现登录、任务、密钥和统计视图 |

---

*本文件最初由 Web backend 任务生成，现作为 API 与前后端边界的永久文档维护。*
