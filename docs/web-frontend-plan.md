# x web 前端开发计划书（v0.7.0）

> **目标读者**：前端 AI agent（接收任务后按本文档实装）
> **后端**：已就绪，见 `feature/web-backend` 分支（merge 后） + `docs/web-api.md`
> **本次任务范围**：仅前端实现 + 后端测试
> **独立 git**：前端代码必须独立在 `feature/web-frontend` 分支（基于 `feature/web-backend` merge 后的 dev）
> **日期**：2026-06-27

---

## 0. TL;DR（一分钟看完）

你要做的事：
1. 在 `core/web/static/` 目录下实现一个**单页 Web 应用**（HTML + CSS + JS）
2. 提供 4 个页面/视图：登录页 / 任务列表 / 任务编辑 / 密钥管理
3. 通过 `X-Web-Token` header 鉴权调用后端 REST API（11 个端点）
4. **不**改后端代码 / **不**改后端测试 / **不**改 docs/web-api.md
5. 在 `feature/web-frontend` 分支开发 + commit，**不**合并到 dev（等后端 merge 后再合并）

---

## 1. 必读（开工前）

1. **`docs/web-api.md`** — 后端 API 完整规格（11 端点 + auth + 错误格式）。**这是契约，不要改它**。
2. **`docs/behaviors/web-api-behavior.md`** — BDD 行为规格（23 个场景）。
3. 后端根目录：`core/web/server.py`（`WebHandler._dispatch` 路由表）+ `core/web/handlers/`（业务逻辑）。
4. 启动方式：`x web` → http://127.0.0.1:8421（首次访问提示输入 token）。

---

## 2. 技术栈约束（必须遵守）

| 项 | 必须 | 禁止 |
|---|---|---|
| **HTML** | HTML5（vanilla，无框架）| — |
| **CSS** | 纯 CSS（vanilla）| ❌ Tailwind / Bootstrap / UI 库 |
| **JS** | Vanilla JS（ES2020+）| ❌ React / Vue / Svelte / jQuery |
| **构建工具** | 无（直接编辑 .html/.css/.js 文件）| ❌ webpack / vite / rollup |
| **HTTP 客户端** | `fetch` API（stdlib 浏览器）| ❌ axios / superagent |
| **包管理** | 无（不需要 `npm install`）| ❌ npm / yarn / pnpm |
| **第三方 CDN** | **可选**：`fetch` / `Promise` / `localStorage` 都已 built-in | ❌ 任何 CDN（jQuery, lodash 等）|

**理由**：x-cli 是 0 第三方依赖项目，前端保持同样风格。**整个 `core/web/static/` 目录 = 静态文件 = 直接 HTTP 服务**。

---

## 3. 文件结构（要创建的文件）

```
core/web/static/
├── index.html               ← 入口（单页应用的所有 view 在这里切换）
├── css/
│   ├── base.css             ← 重置 + 字体 + 颜色变量
│   ├── layout.css           ← 顶部 nav + 主内容区
│   ├── tasks.css            ← 任务列表 / 编辑表单样式
│   ├── secrets.css          ← 密钥列表 / 编辑表单样式
│   └── components.css       ← button / input / table / modal 共用
├── js/
│   ├── api.js               ← fetch wrapper：所有后端调用集中在这里
│   ├── auth.js              ← token 管理（localStorage + prompt）
│   ├── router.js            ← 简单 hash router（#tasks / #secrets / #stats）
│   ├── views/
│   │   ├── login.js         ← 登录页（输入 token）
│   │   ├── tasks.js         ← 任务列表 + 过滤 + 添加
│   │   ├── task-edit.js     ← 单个任务编辑 / 归档
│   │   ├── secrets.js       ← 密钥列表（不含 value）
│   │   ├── secret-view.js   ← 单个密钥查看（含 value + 警告）
│   │   ├── secret-edit.js   ← 新增 / 编辑密钥
│   │   └── stats.js         ← 统计 dashboard
│   └── utils.js             ← 格式化日期、escape HTML、toast 通知
```

**总计约 11 个文件，每个文件 ≤ 200 行**。

---

## 4. UI 设计规范

### 4.1 配色

```css
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f7fa;
  --text-primary: #1a1a1a;
  --text-secondary: #6b7280;
  --border: #e5e7eb;
  --accent: #3b82f6;       /* blue */
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --priority-high: #ef4444;
  --priority-medium: #f59e0b;
  --priority-low: #6b7280;
  --status-pending: #6b7280;
  --status-in_progress: #3b82f6;
  --status-blocked: #ef4444;
  --status-waiting: #f59e0b;
  --status-archived: #9ca3af;
}
```

**暗色模式**：MVP 不做（如果用户提需求再补）。

### 4.2 字体

```css
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; }
```

**中英文混排**，优先系统字体，无网络字体加载。

### 4.3 布局

```
┌─────────────────────────────────────────────┐
│ x web  [Tasks] [Secrets] [Stats]    [⚙️] │  ← 顶部 nav（登录后才显示）
├─────────────────────────────────────────────┤
│                                             │
│  （主内容区，按 hash 切换 view）              │
│                                             │
└─────────────────────────────────────────────┘
```

- 顶部 nav：固定高度 56px
- 主内容区：max-width 960px，水平居中，padding 24px
- 表格：sticky header，hover 高亮
- 表单：label 在 input 上方，error 在 input 下方（红色小字）

### 4.4 状态图标（emoji 风格，与 CLI 一致）

| Status | 显示 | Priority | 显示 |
|---|---|---|---|
| pending | ⏳ | high | 🔥 |
| in_progress | ▶ | medium | ⚡ |
| blocked | ⛔ | low | 🐢 |
| waiting | ⌛ | | |
| archived | ✅ | | |

---

## 5. View 详细规格

### 5.1 登录页（login view）

**触发**：`localStorage` 无 token 或 API 返回 401。

**UI**：
- 居中卡片（max-width 400px）
- 标题："🔐 x web 认证"
- 提示："请输入 `x web` 启动时打印的 Token"
- 输入框（type=password）+ "进入" 按钮
- 错误提示："❌ Token 无效，请检查后重试"

**交互**：
- 用户输入 token → 点 "进入" → 调用 `GET /api/health`（无需 token）验证 → 失败就 `GET /api/tasks`（需要 token）验证 → 成功存 localStorage 并跳 `#tasks`
- "忘记 token" 链接（可选）：提示用户看终端输出

### 5.2 任务列表（tasks view）

**API 调用**：
- 首次加载：`GET /api/tasks`（默认不含 archived）
- 过滤变化时：调 `GET /api/tasks?status=...&priority=...&tag=...&include_archived=...`

**UI**：
- 顶部工具栏：搜索框 / 状态过滤 / 优先级过滤 / "显示已归档" 开关 / "+ 新建" 按钮
- 表格：列 = 图标 / 任务名 / 状态 / 优先级 / 截止日期 / 标签 / 操作
- 点击行 → 跳 `#tasks/<id>`（task-edit view）
- 空状态："📭 没有任务，点 + 新建第一个"

**关键实现**：
- 标签显示：`<span class="tag">驾照</span>`
- 操作按钮：编辑 / 归档（archived 行隐藏）
- 截止日期过期 = 红色
- 不显示 value（这是 secret 子系统的）

### 5.3 任务编辑（task-edit view）

**API 调用**：
- 加载：`GET /api/tasks/<id>`
- 保存：`PATCH /api/tasks/<id>` body `{status?, priority?, deadline?, tags?}`
- 归档：`POST /api/tasks/<id>/archive` body `{reason?}`

**UI**：
- 表单字段：name（只读）/ status（select）/ priority（select）/ deadline（date input）/ tags（逗号分隔 input）
- 底部按钮：保存 / 取消 / 归档（危险按钮，红色）

**关键实现**：
- 加载失败（404）→ 显示错误页 + 返回按钮
- 保存成功后 → toast "✅ 已保存" + 返回列表
- 归档确认：modal 二次确认

### 5.4 密钥列表（secrets view）

**API 调用**：
- 加载：`GET /api/secrets`（**不含 value**）
- 删除：`DELETE /api/secrets/<name>`（带确认 modal）

**UI**：
- 顶部工具栏：搜索框 / "+ 新建" 按钮
- 表格：列 = 名称 / 分组 / 更新时间 / 操作（查看 / 编辑 / 删除）
- **绝不显示 value 列**（硬性约束）
- 空状态："📭 还没有密钥"

### 5.5 密钥查看（secret-view view）

**API 调用**：
- 加载：`GET /api/secrets/<name>`（**含 value**）

**⚠️ 安全警告**：
- 进入此页面前必须弹出 modal：「⚠️ 你正在查看明文密钥。value 可能被屏幕录制 / 浏览器历史记录。是否继续？」
- 用户确认后才显示 value
- value 区域用 `<input type="password">` 显示，旁边有 "👁️ 显示" 切换按钮（点击后切换为 text）
- 复制按钮：调用 `navigator.clipboard.writeText()`，toast "✅ 已复制到剪贴板"
- 显示时打 stderr... 等等，stderr 是后端的事，前端 console.log 提示用户

**UI**：
- 顶部：name / category
- 中部：value 显示框 + 复制按钮 + 显示/隐藏切换
- 底部：note / created_at / updated_at
- 操作：编辑 / 删除 / 返回

### 5.6 密钥编辑（secret-edit view）

**API 调用**：
- 新增：`POST /api/secrets` body `{name, value, category?, note?}`
- 更新：`PATCH /api/secrets/<name>` body `{value?, category?, note?}`

**UI**：
- 表单字段：name（新建时可填，编辑时只读）/ value（password input + 显示切换）/ category / note
- 保存按钮 + 取消按钮

### 5.7 统计（stats view）

**API 调用**：
- 加载：`GET /api/tasks/stats`

**UI**：
- 顶部卡片：总数 / pending / in_progress / blocked / waiting / archived（带图标 + 颜色）
- 高优先级任务列表：调 `GET /api/tasks?priority=high` 显示
- 即将到期（≤7 天）：调 `GET /api/tasks` 客户端过滤 deadline

---

## 6. 关键实现细节

### 6.1 API 调用封装（js/api.js）

```js
// 所有后端调用集中在这个模块
const API_BASE = "";  // 同源

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem("x_web_token");
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };
  if (token) headers["X-Web-Token"] = token;

  const resp = await fetch(API_BASE + path, {
    ...options,
    headers,
  });

  if (resp.status === 401) {
    localStorage.removeItem("x_web_token");
    window.location.hash = "#login";
    throw new Error("未授权");
  }

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new ApiError(data.error || resp.statusText, data.code, resp.status);
  }
  return data;
}

export class ApiError extends Error {
  constructor(message, code, status) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

// 各端点封装
export const api = {
  health: () => apiFetch("/api/health"),
  listTasks: (filters = {}) => {
    const qs = new URLSearchParams(filters).toString();
    return apiFetch(`/api/tasks${qs ? "?" + qs : ""}`);
  },
  getTask: (id) => apiFetch(`/api/tasks/${id}`),
  createTask: (data) => apiFetch("/api/tasks", { method: "POST", body: JSON.stringify(data) }),
  updateTask: (id, data) => apiFetch(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  archiveTask: (id, reason) => apiFetch(`/api/tasks/${id}/archive`, { method: "POST", body: JSON.stringify({ reason }) }),
  stats: () => apiFetch("/api/tasks/stats"),
  listSecrets: () => apiFetch("/api/secrets"),
  getSecret: (name) => apiFetch(`/api/secrets/${encodeURIComponent(name)}`),
  createSecret: (data) => apiFetch("/api/secrets", { method: "POST", body: JSON.stringify(data) }),
  updateSecret: (name, data) => apiFetch(`/api/secrets/${encodeURIComponent(name)}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteSecret: (name) => apiFetch(`/api/secrets/${encodeURIComponent(name)}`, { method: "DELETE" }),
};
```

### 6.2 Router（js/router.js）

```js
// 简单 hash router
const routes = {
  "#login": () => import("./views/login.js").then(m => m.render),
  "#tasks": () => import("./views/tasks.js").then(m => m.render),
  "#tasks/new": () => import("./views/task-edit.js").then(m => m.render),
  "#tasks/:id": (id) => import("./views/task-edit.js").then(m => m.render(id)),
  "#secrets": () => import("./views/secrets.js").then(m => m.render),
  // ... etc
};

export function navigate(hash) {
  window.location.hash = hash;
}

window.addEventListener("hashchange", renderRoute);
window.addEventListener("load", renderRoute);

async function renderRoute() {
  const hash = window.location.hash || "#tasks";
  const match = matchRoute(hash);
  if (!match) {
    navigate("#tasks");
    return;
  }
  // Auth check
  if (hash !== "#login" && !localStorage.getItem("x_web_token")) {
    navigate("#login");
    return;
  }
  const view = await match.handler(...match.params);
  document.getElementById("main").innerHTML = "";
  document.getElementById("main").appendChild(view);
}
```

### 6.3 转义（XSS 防护）

所有用户输入（任务名 / 标签 / 密钥名 / note / value）显示前必须 escape：

```js
// js/utils.js
export function escapeHtml(str) {
  if (str == null) return "";
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}
```

**禁止**用 `innerHTML = ...` 直接插入未转义的用户数据。

---

## 7. UI 流程图（用户视角）

```
启动 x web
   ↓
浏览器打开 http://127.0.0.1:8421
   ↓
无 token？→ 是 → #login（输入 token）→ 验证成功 → #tasks
   ↓ 否
#tasks（任务列表）
   ├─ 点击任务 → #tasks/<id>（编辑）
   ├─ + 新建 → #tasks/new
   ├─ 点击 [Secrets] → #secrets
   ├─ 点击 [Stats] → #stats
   └─ 点击 [⚙️] → 修改 token / 退出登录
```

---

## 8. 不做（v0.7.0 前端）

明确**禁止**实现：

- ❌ **暗色模式**（配色 `--bg-primary: #ffffff` 即可）
- ❌ **拖拽排序**（任务排序走服务端）
- ❌ **批量操作**（多选 + 批量归档）
- ❌ **实时推送 / WebSocket**（用 `setInterval` 5 秒轮询即可；MVP 不做轮询也 OK）
- ❌ **搜索高亮 / 模糊匹配**（精确包含即可）
- ❌ **键盘快捷键**（`?` 打开帮助 / `/` 搜索等）— 后续版本
- ❌ **国际化 i18n**（中文界面即可，英文标签可加）
- ❌ **PWA / 离线缓存**（不需要）
- ❌ **打印 / 导出**（CLI 的 `x secret export` 已支持）
- ❌ **头像 / 主题切换**（个人工具，没意义）
- ❌ **拖放上传 / 文件管理**（不在 v0.7.0 范围）
- ❌ **图片 / 富文本编辑器**（task body 是纯文本，textarea 即可）
- ❌ **多窗口 / 多 tab 同步**（localStorage 单 tab 够用）
- ❌ **第三方依赖**（任何 npm 包都不行）

**原则**：**less is more**。x-cli 是个人工具，前端是 CLI 的可视化补充，不是要做一个完整的 Trello。

---

## 9. Git 工作流（必须遵守）

### 9.1 分支

```bash
# 基于最新 dev（已包含 feature/web-backend merge 后的代码）
git checkout dev
git pull origin dev
git checkout -b feature/web-frontend

# 开发 + commit（每 view 一个 commit，commit message 用 conventional commits）
git add core/web/static/
git commit -m "feat(web-frontend): add login view + token auth"
git commit -m "feat(web-frontend): add tasks list + filter"
# ... etc

# 推送 + 开 PR（user 会 merge）
git push origin feature/web-frontend
```

### 9.2 Commit message 规范

```bash
feat(web-frontend): <view 或功能名>
fix(web-frontend): <bug>
refactor(web-frontend): <重构>
docs(web-frontend): <文档注释>
test(web-frontend): <如有测试>
```

### 9.3 不做的事

- ❌ **不要**修改 `core/web/server.py` / `core/web/handlers/*.py` / `core/web/auth.py`
- ❌ **不要**修改 `plugins/web.py`
- ❌ **不要**修改 `tests/test_web_api.py`（后端测试）
- ❌ **不要**修改 `docs/web-api.md`（API 契约）
- ❌ **不要**修改 `docs/behaviors/web-api-behavior.md`
- ❌ **不要**合并到 dev / main（user 会处理）

**唯一允许修改的文件**：
- `core/web/static/` 目录下所有新文件
- `docs/web-frontend-plan.md`（如有补充说明）

---

## 10. 验收标准

完成时，user 会在 dev 上 checkout feature/web-frontend 分支后跑：

```bash
# 1. 启动后端
x web

# 2. 浏览器手动测试清单
# - [ ] 打开 http://127.0.0.1:8421 看到 login 页
# - [ ] 输入 token 进入
# - [ ] 看到任务列表（如果仓库有任务）
# - [ ] 新建一个任务
# - [ ] 编辑任务状态
# - [ ] 归档任务
# - [ ] 切换到 secrets 视图，看到列表（不含 value）
# - [ ] 查看一个密钥（含 value）+ 警告 modal
# - [ ] 复制 value 到剪贴板
# - [ ] 编辑密钥
# - [ ] 删除密钥（带确认）
# - [ ] 查看 stats
# - [ ] 退出登录

# 3. 后端测试仍然通过（feature/web-frontend 不应破坏后端）
pytest tests/test_web_api.py -q
```

---

## 11. 估算

| 项 | 行数（估）|
|---|---|
| HTML 入口 | ~80 |
| CSS（5 文件）| ~400 |
| JS（api.js + auth.js + router.js + utils.js）| ~300 |
| JS（7 views）| ~800 |
| **合计** | **~1600 行** |

预计工作量：4-6 小时。

---

## 12. 答疑

**Q：后端 API 还没合并到 dev，我能在 feature/web-frontend 上测试吗？**
A：可以基于 `feature/web-backend` 分支 checkout 新分支 `feature/web-frontend`（不基于 dev）。merge 顺序：feature/web-backend → dev → 然后 feature/web-frontend → dev。user 会负责按顺序 merge。

**Q：能加暗色模式吗？**
A：不能，v0.7.0 范围限制。如果想加，开新的 feature/dark-mode 分支，独立实现。

**Q：能改后端 API 吗？**
A：不能。如发现 API 不足，在 commit message 里加 `NOTE:` 说明，并告知 user，由 user 决定是否改 API。

**Q：测试在哪？**
A：MVP 不写自动化测试（前端单页应用手动测试更快）。如果你想加，用 `js/utils.js` 里的纯函数方便单测。

**Q：能不能用 TypeScript？**
A：不能。要保持 stdlib-only 项目风格。Vanilla JS + JSDoc 注释已经够用。

---

## 13. 关联文档

- 后端 API 契约：`docs/web-api.md`
- 后端 BDD：`docs/behaviors/web-api-behavior.md`
- 项目主规约：`AGENTS.md`
- 命令清单：`COMMANDS.md`（**user 维护，不要 AI 改**）
- 架构总览：`docs/architecture.md`

---

*本文件由 feature/web-backend 任务生成（2026-06-27），交给前端 AI 使用。后端 merge 后即可开始。*