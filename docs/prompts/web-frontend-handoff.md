# 任务交接：x web 前端实现（feature/web-frontend）

> **目标读者**：接续开发的 AI agent
> **来源**：原 agent 已完成第一版（17 文件 / 2955 行 / 4 commits），但你拿到任务时**应视为全新任务** — 先读本文档 + 计划书，再决定要不要复用已有代码。
> **日期**：2026-06-28

---

## 1. TL;DR

实现 `x web` 的浏览器前端，让用户能在本地 http://127.0.0.1:8421 看到任务列表 / 密钥管理 / 统计 dashboard，**通过后端 REST API 读写数据**。

后端代码已就位（`feature/web-backend` 分支，含 11 端点 + token 鉴权）。你的任务范围**仅前端**。

---

## 2. 必读（按顺序读完再动手）

| 顺序 | 文档 | 读什么 |
|---|---|---|
| 1 | `AGENTS.md` | 项目规约（commit 规范 / 命名 / 禁忌） |
| 2 | `docs/web-frontend-plan.md` | **唯一 spec 源**（UI 设计 / 文件结构 / view 详细规格） |
| 3 | `docs/web-api.md` | API 契约（11 端点 + auth + 错误格式）— **不要改** |
| 4 | `docs/behaviors/web-api-behavior.md` | BDD 行为规格（23 场景，理解后端行为） |
| 5 | `core/web/server.py` | 静态文件服务 + 路由逻辑 |

**未读完直接动手 = 失败率高**。文档没写的 → **先问用户**，不要猜。

---

## 3. 上下文

- **项目**：x-cli（个人 CLI 工具集，Phase 1 MVP 已完成 v0.2.0，目前 v0.4.x）
- **后端**：`x web` 子命令已实现（`plugins/web.py` + `core/web/server.py`），11 REST 端点 + 32 字节随机 token 鉴权
- **前端**：`core/web/static/` 当前是 `feature/web-backend` 分支的占位 index.html
- **目标**：在前端分支替换整个 `core/web/static/` 目录

⚠️ **已知后端 bug**（**不在你修复范围内**）：`x.py` 的 `SUBCOMMAND_HANDLERS` 字典没注册 `"web"`，所以 `x web` 命令跑不起来。前端无需关心此 bug；测后端时直接 `python -c "from core.web.server import WebServer; WebServer(host='127.0.0.1', port=18421, token='test').start()"` 启动。

---

## 4. 交付物

11 个文件，约 1600 行，**全部在 `core/web/static/` 内**：

```
core/web/static/
├── index.html               # 单页入口（view 切换在这里完成）
├── css/
│   ├── base.css             # 颜色变量 / 间距 / 字号 / 字体栈 / reset
│   ├── layout.css           # 顶部 nav + main 容器
│   ├── components.css       # button / input / table / card / modal / toast / tag / badge
│   ├── tasks.css            # 任务行 / 编辑表单 / 归档 modal
│   └── secrets.css          # 密钥行 / value 块 / 复制 / 编辑
└── js/
    ├── api.js               # 11 端点封装 + ApiError + 401 自动跳登录
    ├── auth.js              # token localStorage 管理
    ├── router.js            # hash router（9 路由 + 登录拦截）
    ├── utils.js             # escapeHtml / 格式化 / toast / modal / confirmModal
    └── views/
        ├── login.js         # 登录页（输入 token 验证）
        ├── tasks.js         # 任务列表 + 过滤 + 工具栏
        ├── task-edit.js     # 任务编辑 / 归档（新建复用）
        ├── secrets.js       # 密钥列表（绝不含 value）
        ├── secret-view.js   # 单个密钥查看（含 value + 警告 modal）
        ├── secret-edit.js   # 新建 / 编辑密钥
        └── stats.js         # 统计 dashboard
```

---

## 5. 技术栈约束（必须遵守）

| 项 | 必须 | 禁止 |
|---|---|---|
| HTML | HTML5 vanilla | — |
| CSS | 纯 CSS（CSS 变量驱动） | ❌ Tailwind / Bootstrap / 任何 UI 库 |
| JS | Vanilla JS（ES2020+，ES modules） | ❌ React / Vue / Svelte / jQuery / 任何框架 |
| HTTP | `fetch` API | ❌ axios / superagent |
| 构建 | 无 | ❌ webpack / vite / rollup / 任何 bundler |
| 包管理 | 无 | ❌ npm / yarn / pnpm |
| CDN | 无 | ❌ 任何 CDN（含 jQuery / lodash / 字体图标） |

**理由**：x-cli 是 0 第三方依赖项目，前端保持同样风格。

---

## 6. 关键设计决策

### 6.1 路由

- **hash router**（无 History API，避免与后端静态文件服务冲突）
- 路由表（9 条）：
  - `#login` — views/login.js
  - `#tasks` — views/tasks.js
  - `#tasks/new` — views/task-edit.js (空)
  - `#tasks/:id` — views/task-edit.js (id)
  - `#secrets` — views/secrets.js
  - `#secrets/new` — views/secret-edit.js (空)
  - `#secrets/:name` — views/secret-view.js
  - `#secrets/:name/edit` — views/secret-edit.js (name)
  - `#stats` — views/stats.js
- 未登录访问任何非 `#login` → 跳 `#login`
- 401 → 清 token + 跳 `#login`

### 6.2 设计 token（CSS 变量）

完整 token 见 `docs/web-frontend-plan.md` §4.1。这里是关键几个：

```css
--bg-primary: #ffffff;
--bg-secondary: #f5f7fa;
--text-primary: #1a1a1a;
--text-secondary: #6b7280;
--border: #e5e7eb;
--accent: #3b82f6;       /* 蓝 */
--success: #10b981;
--warning: #f59e0b;
--danger: #ef4444;
--status-pending: #6b7280;
--status-in_progress: #3b82f6;
--status-blocked: #ef4444;
--status-waiting: #f59e0b;
--status-archived: #9ca3af;
--priority-high: #ef4444;
--priority-medium: #f59e0b;
--priority-low: #6b7280;
```

字体：`-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif`

### 6.3 状态 / 优先级 图标（与 CLI 一致）

| status | 图标 | priority | 图标 |
|---|---|---|---|
| pending | ⏳ | high | 🔥 |
| in_progress | ▶ | medium | ⚡ |
| blocked | ⛔ | low | 🐢 |
| waiting | ⌛ | | |
| archived | ✅ | | |

### 6.4 布局

- 顶部 nav：56px fixed，左 brand / 中 nav-links / 右 退出
- main：`max-width: 960px` 居中，`padding: 24px`
- 表格：`sticky header` + hover 高亮 + 行可点
- 响应式：< 640px 缩小 padding、stats grid 转 2 列

---

## 7. API 端点（11 个，详细规格见 `docs/web-api.md`）

```js
// tasks
api.health()                       // GET  /api/health            (无需 token)
api.listTasks(filters)             // GET  /api/tasks
api.getTask(id)                    // GET  /api/tasks/:id
api.createTask(data)               // POST /api/tasks
api.updateTask(id, data)           // PATCH /api/tasks/:id
api.archiveTask(id, reason)        // POST /api/tasks/:id/archive
api.stats()                        // GET  /api/tasks/stats

// secrets
api.listSecrets()                  // GET  /api/secrets           (不含 value)
api.getSecret(name)                // GET  /api/secrets/:name     (含 value + stderr 警告)
api.createSecret(data)             // POST /api/secrets
api.updateSecret(name, data)       // PATCH /api/secrets/:name
api.deleteSecret(name)             // DELETE /api/secrets/:name
```

所有 `/api/*`（除 `/api/health`）要求 `X-Web-Token` header。

---

## 8. View 关键实现要点

### 8.1 login view

- 居中卡片（max-width 420px）
- 验证流程：先 `health()`（确认后端在）→ 再 `listTasks()`（确认 token 对）
- 错误分级：后端未启动 vs token 错误，给用户不同提示
- 如果 `localStorage` 已有 token，尝试用其验证后自动跳 `#tasks`

### 8.2 tasks list view

- 工具栏：搜索 / 状态过滤 / 优先级过滤 / "显示已归档" 开关 / 重置
- 表格：图标 / 任务名(+id) / 状态 / 优先级 / 截止 / 标签 / 操作
- deadline 配色：过期 = 红、≤3 天 = 黄
- 行点击跳详情，操作按钮事件独立
- 客户端二次过滤（搜索 q 匹配 name / id / tags）
- hash 同步（`?q=...&status=...`）

### 8.3 task-edit view

- 复用：编辑 + 新建都用 `renderForm()`，传入 `isNew` 和 `secret`/`task`
- name 字段：新建可填，编辑只读
- 归档流程：弹 modal → 选 reason（done/cancelled/expired/failed）→ 确认 → POST

### 8.4 secrets list view

- 表格：name / category / updated_at / 操作
- **硬约束：绝不含 value**（与 CLI `x secret list` 一致）
- 行点击跳 view，按钮独立事件

### 8.5 secret-view view

- **安全流程**：进入前必弹警告 modal（"你正在查看明文密钥..."）→ 用户确认后才拉 value
- value 用 `password` input + 👁️ 切换 + 📋 复制（`navigator.clipboard.writeText` 含 fallback）
- 离开页面 / 刷新 = 重新走警告流程（不缓存 value）

### 8.6 secret-edit view

- 复用：新建 + 编辑共用
- 编辑时 value 留空 = 不修改（PATCH 语义）

### 8.7 stats view

- 6 个 stat-card：total / 各 status 计数
- 3 段：🔥 高优先级 / ⚠️ 即将到期（≤7 天）/ 🚨 已过期
- 并行拉 `stats()` + `listTasks({include_archived: true})`
- 客户端二次过滤 deadline

---

## 9. 硬约束（不能做的事）

来自 `docs/web-frontend-plan.md` §9.3：

- ❌ **不改后端**：不动 `core/web/server.py` / `core/web/handlers/*.py` / `core/web/auth.py` / `plugins/web.py` / `x.py`
- ❌ **不改 API 契约**：`docs/web-api.md` / `docs/behaviors/web-api-behavior.md`
- ❌ **不改后端测试**：`tests/test_web_api.py`
- ❌ **不引入第三方依赖**（任何 npm / CDN 都不行）
- ❌ **不合并**到 dev / main（用户处理）
- ❌ **不 push**（用户处理）

v0.7.0 前端**不做**：

- 暗色模式 / 拖拽排序 / 批量操作 / WebSocket 实时推送 / 搜索高亮 / 键盘快捷键 / i18n / PWA / 打印导出 / 头像主题切换 / 富文本编辑器 / 多 tab 同步

---

## 10. 验收（plan §10）

完成后用户会跑：

```bash
# 1. 启后端（直接 Python，因为 x web 命令在 x.py 没注册）
python -c "from core.web.server import WebServer; s=WebServer(host='127.0.0.1', port=8421, token='test'); s.start()"

# 2. 浏览器手动测清单
# - [ ] 打开 http://127.0.0.1:8421 看到 login 页
# - [ ] 输入 token 进入
# - [ ] 看到任务列表（如果有任务）
# - [ ] 新建任务
# - [ ] 编辑任务状态
# - [ ] 归档任务
# - [ ] 切到 secrets 视图，看到列表（不含 value）
# - [ ] 查看密钥 + 警告 modal
# - [ ] 复制 value 到剪贴板
# - [ ] 编辑密钥
# - [ ] 删除密钥（带确认）
# - [ ] 看 stats
# - [ ] 退出登录

# 3. 后端测试仍通过
.venv\Scripts\python.exe -m pytest tests/test_web_api.py -q
```

---

## 11. Git 工作流

```bash
# 基于 feature/web-backend（不是 dev，后端未合并）
git checkout feature/web-backend
git pull origin feature/web-backend
git checkout -b feature/web-frontend

# 写 + 测 + commit（per-subsystem 或 per-view，按你的判断）
git add core/web/static/
git commit -m "feat(web-frontend): <范围>"

# 完成后不要 push / merge
```

Commit 规范（plan §9.2）：

- `feat(web-frontend): <view 或功能名>`
- `fix(web-frontend): <bug>`
- `refactor(web-frontend): <重构>`

---

## 12. 已有参考实现（可选复用）

之前有 agent 写过一版完整实装，落在 `feature/web-frontend` 分支（4 commits）：

```
f1bdb06 feat(web-frontend): stats dashboard
3c6f122 feat(web-frontend): secret subsystem (list + view + edit)
06a5834 feat(web-frontend): task subsystem (login + list + edit + archive)
f33091e feat(web-frontend): scaffold + design system + core modules
```

**是否复用由你决定**：
- ✅ 复用：直接 `git checkout feature/web-frontend` 看代码，按 plan §10 验收清单手测
- ❌ 重写：基于 `feature/web-backend` 重新建分支

如果复用，注意 review 一下：
1. `tasks.js` 中 deadline `formatDate` 对 "none" / `{}` 的处理
2. `task-edit.js` 的归档 reason 选择 modal（用 `pickArchiveReason()`）
3. `secret-view.js` 的警告 modal 流程（不缓存 value）
4. XSS：`escapeHtml` 是否覆盖所有用户输入
5. 401 流程：`api.js` 是否正确清 token + 跳 login

---

## 13. 关联文档

- 计划书（**唯一 spec**）：`docs/web-frontend-plan.md`
- API 契约：`docs/web-api.md`
- 后端 BDD：`docs/behaviors/web-api-behavior.md`
- 项目规约：`AGENTS.md`
- 命令清单：`COMMANDS.md`（user-only，别动）
- 架构总览：`docs/architecture.md`

---

## 14. 答疑

**Q：plan §9.1 说基于 dev，但 feature/web-backend 没合并到 dev 怎么办？**
A：基于 `feature/web-backend` 建 `feature/web-frontend`，per plan §12 Q&A。merge 顺序：web-backend → dev → web-frontend → dev，由 user 处理。

**Q：后端有 bug（`x web` 子命令没注册），要不要顺手修？**
A：**不要**。这违反 plan §9.3 后端文件不动约束。要修就让用户自己开 issue / 分支。

**Q：测试在哪？**
A：前端 MVP **不写自动化测试**（plan §12）。手测用 plan §10 清单。如果你觉得必要，优先用 `js/utils.js` 里的纯函数做单测。

**Q：发现 API 不足怎么办？**
A：commit message 加 `NOTE:` 说明，告知 user，由 user 决定是否改 API。

---

*本交接文档由完成首版的 agent 生成（2026-06-28），交给其他 AI 同事使用。*
