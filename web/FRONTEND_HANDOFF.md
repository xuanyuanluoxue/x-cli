# x web 前端重写后端交接计划书

> 目标读者：接手重写 `x web` 页面的人或前端 AI agent  
> 视角：后端交接，不规定前端怎么实现  
> 日期：2026-07-11  
> 前端工作区：项目根目录 `web/`

---

## 1. 目标

把现有 `x web` 页面重写成一个可用的本地 Web 前端，用浏览器管理 x-cli 的两个后端子系统：

- `todo`：任务列表、任务详情、新建、更新、归档、统计。
- `secret`：密钥列表、新建、查看明文、更新、删除。

前端可以自由选择实现方式，但最终必须能被后端以静态文件形式托管。后端当前只提供 HTTP API 和静态文件服务，不提供 SSR、不提供前端构建能力、不提供 WebSocket。

---

## 2. 前后端边界

### 前端负责

- `web/` 目录下的所有页面、样式、脚本、静态资源和前端说明文档。
- 登录态、路由、表单、加载态、错误态、空状态、确认弹窗、复制密钥等交互。
- 调用后端 REST API，并正确处理 `401`、`404`、`409`、`400` 等错误。
- 保护敏感信息：密钥 value 不进入列表页、不长期缓存、不写日志。

### 后端负责

- `x web` 启动本地 HTTP 服务。
- token 鉴权。
- TODO 文件系统读写。
- Secret JSON DB 读写。
- API 错误响应和状态码。

### 前端不要改

- `plugins/web.py`
- `core/web/server.py`
- `core/web/auth.py`
- `core/web/handlers/*.py`
- `core/storage.py`
- `core/secrets.py`
- `x.py`
- `tests/test_web_api.py`

如果前端发现 API 不够用，先记录缺口，不要直接改后端契约。

---

## 3. 当前后端事实

### 启动方式

```powershell
x web
x web --token test
x web --token test --no-browser
x web --token test --auto-token-url
```

实际行为：

- 默认监听：`http://127.0.0.1:8421`
- 默认 token：启动时随机生成，打印在终端。
- 默认会尝试打开浏览器。
- `--no-browser`：不自动打开浏览器。
- `--auto-token-url` / `-A`：打开 `/?token=<token>`，用于前端自动读取 token；前端读完后必须清理 URL。

### 静态文件托管

后端当前静态目录是：

```text
core/web/static/
```

本次重写先把前端工作放在根目录：

```text
web/
```

后续接入有两种方案，前端不需要现在决定：

1. 后端把静态目录从 `core/web/static/` 切到 `web/`。
2. 前端产物从 `web/` 复制/同步到 `core/web/static/`。

交付时需要明确最终产物入口：`index.html` 以及相关 CSS/JS/assets。

---

## 4. 认证规则

除健康检查外，所有 `/api/*` 请求都必须带：

```http
X-Web-Token: <启动时打印的 token>
```

不需要 Cookie，不需要 Session，不需要 CSRF token。

### 登录建议流程

1. 用户打开页面。
2. 如果 URL 有 `?token=xxx`：
   - 读取 token。
   - 保存到前端登录态。
   - 立刻用 `history.replaceState` 清理地址栏，避免 token 留在浏览器历史。
3. 调 `GET /api/health` 判断后端是否启动。
4. 调 `GET /api/tasks` 验证 token 是否正确。
5. 成功进入主界面；失败显示 token 错误。

### 401 处理

任意 API 返回：

```json
{"error": "...", "code": "missing_token"}
```

或：

```json
{"error": "...", "code": "invalid_token"}
```

前端应清除当前 token，并回到登录页。

---

## 5. API 总览

Base URL 与页面同源：

```text
http://127.0.0.1:8421
```

后端不做 CORS。开发时如果前端起独立 dev server，需要自行代理，或最终用同源静态文件方式验证。

### 健康检查

| 方法 | 路径 | 鉴权 | 用途 |
|---|---|---:|---|
| `GET` | `/api/health` | 否 | 检查后端是否在线 |

响应：

```json
{
  "status": "ok",
  "version": "0.6.0",
  "subsystems": ["todo", "secret"]
}
```

### TODO

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/tasks` | 列出任务 |
| `POST` | `/api/tasks` | 新建任务 |
| `GET` | `/api/tasks/<id>` | 获取单个任务 |
| `PATCH` | `/api/tasks/<id>` | 更新任务 |
| `POST` | `/api/tasks/<id>/archive` | 归档任务 |
| `GET` | `/api/tasks/stats` | 获取统计 |

### Secret

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/secrets` | 列出密钥摘要，不含 value |
| `POST` | `/api/secrets` | 新建密钥 |
| `GET` | `/api/secrets/<name>` | 获取单个密钥，含 value |
| `PATCH` | `/api/secrets/<name>` | 更新密钥 |
| `DELETE` | `/api/secrets/<name>` | 删除密钥 |

---

## 6. TODO API 细节

### Task 数据结构

```json
{
  "id": "kemu1",
  "name": "科目一模拟考",
  "status": "pending",
  "priority": "high",
  "deadline": "2026-08-31",
  "tags": ["驾照", "暑假"],
  "created": "2026-07-11",
  "updated": "2026-07-11",
  "folder": "任务/科目一模拟考",
  "archived": false,
  "reason": null
}
```

枚举：

- `status`：`pending` / `in_progress` / `blocked` / `waiting` / `archived`
- `priority`：`high` / `medium` / `low`
- `reason`：`done` / `cancelled` / `expired` / `failed`

### `GET /api/tasks`

Query：

- `include_archived=true`：包含已归档任务，默认不包含。
- `status=pending`：按状态过滤。
- `priority=high`：按优先级过滤。
- `tag=xxx`：按标签精确匹配。

响应：

```json
{
  "tasks": [],
  "count": 0
}
```

注意：当前后端 query parser 很简单，不做 URL decode。中文 tag 过滤可能不可靠。前端如果需要中文标签筛选，建议先拉列表后在客户端过滤。

### `POST /api/tasks`

请求：

```json
{
  "name": "新任务",
  "priority": "medium",
  "deadline": "2026-08-31",
  "tags": ["标签1", "标签2"]
}
```

规则：

- `name` 必填。
- `priority` 可省略，默认 `medium`。
- `deadline` 可省略，必须是字符串。
- `tags` 可省略，必须是数组。

响应：

```json
{"task": {"id": "..."}}
```

### `PATCH /api/tasks/<id>`

请求字段可部分提交：

```json
{
  "status": "in_progress",
  "priority": "high",
  "deadline": null,
  "tags": ["新标签"]
}
```

规则：

- 至少提交一个字段。
- `deadline: null` 表示清除 deadline。
- `tags` 是完全替换，不是追加。
- 已归档任务不能更新，会返回 `409 duplicate`。

### `POST /api/tasks/<id>/archive`

请求：

```json
{"reason": "done"}
```

规则：

- body 可省略。
- `reason` 省略时默认 `done`。
- 已归档任务再次归档返回 `409 duplicate`。

### `GET /api/tasks/stats`

响应由后端 `TaskStore.stats()` 直接返回，典型结构：

```json
{
  "total": 0,
  "by_status": {
    "pending": 0,
    "in_progress": 0,
    "blocked": 0,
    "waiting": 0,
    "archived": 0
  },
  "by_priority": {
    "high": 0,
    "medium": 0,
    "low": 0
  },
  "due_within_7_days": 0,
  "high_priority_active": 0
}
```

前端应容忍后端未来新增字段。

---

## 7. Secret API 细节

### 列表摘要结构

`GET /api/secrets` 只返回摘要：

```json
{
  "secrets": [
    {
      "name": "minimax",
      "category": "API",
      "updated_at": "2026-07-11T12:00:00"
    }
  ],
  "count": 1
}
```

硬约束：列表页绝不能展示、缓存或推断 `value`。

### 完整密钥结构

`GET /api/secrets/<name>`、`POST /api/secrets`、`PATCH /api/secrets/<name>` 返回：

```json
{
  "secret": {
    "name": "minimax",
    "category": "API",
    "value": "sk-test",
    "note": "",
    "created_at": "2026-07-11T12:00:00",
    "updated_at": "2026-07-11T12:00:00"
  }
}
```

后端每次返回完整密钥都会在服务端 stderr 打警告。前端仍然要在用户查看 value 前主动弹确认。

### `POST /api/secrets`

请求：

```json
{
  "name": "minimax",
  "value": "sk-test",
  "category": "API",
  "note": "备注"
}
```

规则：

- `name` 必填。
- `value` 必填。
- `category` 可省略，默认 `default`。
- `note` 可省略。

### `PATCH /api/secrets/<name>`

请求字段可部分提交：

```json
{
  "value": "sk-new",
  "category": "API",
  "note": "新备注"
}
```

规则：

- 至少提交一个字段。
- 不想修改的字段必须省略，不要传空字符串占位。
- 修改 value 后，后端会返回完整 secret。

### `DELETE /api/secrets/<name>`

成功返回：

```http
204 No Content
```

无响应 body。前端删除前必须二次确认。

---

## 8. 错误格式

所有非 2xx API 错误统一是 JSON：

```json
{
  "error": "human readable message",
  "code": "machine_readable_code"
}
```

常见状态码：

| HTTP | code | 含义 |
|---:|---|---|
| `400` | `validation_error` | 参数或 JSON body 不合法 |
| `401` | `missing_token` | 缺少 `X-Web-Token` |
| `401` | `invalid_token` | token 错误 |
| `404` | `not_found` | 资源不存在 |
| `405` | `method_not_allowed` | 方法不允许 |
| `409` | `duplicate` | 重名、已归档、冲突 |
| `500` | `internal_error` | 后端未预期错误 |

前端展示建议：

- `400`：显示字段级或表单级错误。
- `401`：清 token，回登录页。
- `404`：显示资源不存在，并提供返回按钮。
- `409`：显示冲突原因，让用户刷新或改名。
- `500`：显示后端错误摘要，不要吞掉。

---

## 9. 页面建议

这不是强制 UI 方案，只是后端视角下最小可用功能拆分。

### 登录页

- 输入 token。
- 支持 `?token=xxx` 自动填入。
- 后端未启动和 token 错误要分开提示。

### 任务页

- 列表：显示 name、id、status、priority、deadline、tags。
- 过滤：status、priority、是否包含 archived。
- 搜索：建议客户端搜索 name/id/tags，因为后端没有搜索端点。
- 操作：新建、编辑、归档。

### 任务详情/编辑页

- 新建时可编辑 name。
- 编辑时 name 建议只读，因为后端 PATCH 不支持改名。
- tags 用数组提交，输入框可以用逗号分隔再转换。
- 归档必须二次确认。

### 统计页

- 直接使用 `/api/tasks/stats`。
- 如需“过期任务列表”等更细展示，额外拉 `/api/tasks?include_archived=true` 后在客户端算。

### 密钥列表页

- 只调用 `/api/secrets`。
- 不显示 value 列。
- 支持按 name/category 客户端搜索。

### 密钥详情页

- 进入前弹明文查看警告。
- 用户确认后再调用 `/api/secrets/<name>`。
- value 默认隐藏，提供显示/隐藏和复制。
- 离开页面后丢弃 value，不要缓存到全局 store/localStorage。

### 密钥编辑页

- 新建：name、value、category、note。
- 编辑：name 只读。
- 编辑时 value 留空应表示“不修改”，因此 PATCH 时直接省略 `value` 字段。
- 删除必须二次确认。

---

## 10. 安全和数据处理要求

- 渲染所有后端返回的用户内容前做 HTML escape。
- token 不写入 URL；如果从 `?token=` 读取，立刻清理。
- 不把 secret value 写入 console、localStorage、sessionStorage、URL、错误日志。
- secret value 只在用户确认查看后请求。
- secret 列表页永远只用 `/api/secrets`，不要为了展示列表去批量请求详情。
- 所有写操作成功后重新拉列表或更新本地状态，避免显示旧数据。
- 前端要容忍后端响应新增字段。

---

## 11. 当前后端没有的能力

前端不要假设这些已存在：

- 没有 todo 搜索 API。
- 没有 todo restore API。
- 没有 todo done 快捷 API。
- 没有编辑 TODO Markdown 正文的 API。
- 没有 secret search/import/export API。
- 没有批量操作 API。
- 没有 WebSocket 或实时推送。
- 没有 CORS。
- 没有文件上传。
- 没有用户系统。

需要这些能力时，先写成“后端需求清单”，不要在前端硬模拟会破坏数据一致性的写操作。

---

## 12. 验收建议

后端最小启动：

```powershell
x web --token test --no-browser
```

如果 CLI 启动异常，可直接用 Python 启服务：

```powershell
.venv\Scripts\python.exe -c "from core.web.server import WebServer; import time; s=WebServer(host='127.0.0.1', port=8421, token='test'); s.start(); print('http://127.0.0.1:8421 token=test'); time.sleep(999999)"
```

手动验收：

- 打开 `http://127.0.0.1:8421`。
- 输入 token 后能进入。
- 能列出、新建、编辑、归档任务。
- 能查看统计。
- 密钥列表不显示 value。
- 查看密钥前有警告。
- 查看密钥后能复制 value。
- 能新建、编辑、删除密钥。
- token 错误时回登录页。
- 刷新页面后仍能恢复可用状态。

后端回归测试：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_web_api.py -q
```

---

## 13. 交付物

前端交付时至少说明：

- `web/` 下的入口文件是什么。
- 是否需要构建；如果需要，构建命令是什么。
- 最终静态产物目录是什么。
- 如何把产物接到后端当前静态服务。
- 已手测通过哪些流程。
- 需要后端补哪些 API。

---

## 14. 后端参考文件

- `plugins/web.py`：`x web` 命令参数、token、启动浏览器逻辑。
- `core/web/server.py`：HTTP 路由、静态文件服务、鉴权。
- `core/web/handlers/tasks.py`：TODO API 实现。
- `core/web/handlers/secrets.py`：Secret API 实现。
- `core/web/response.py`：JSON 响应和错误格式。
- `tests/test_web_api.py`：后端行为回归测试。
- `docs/behaviors/web-api-behavior.md`：BDD 行为规格。
- `docs/web-api.md`：旧 API 文档，可能存在过时描述；以实际 handler 和测试为准。
