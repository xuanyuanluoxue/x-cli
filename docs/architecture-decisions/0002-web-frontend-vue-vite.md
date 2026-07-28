# ADR 0002: Web 前端迁移到 Vue 3 + Vite

- 状态：已接受
- 日期：2026-07-19
- 更新：2026-07-29（Vite 8 / Rolldown）

## 背景

原 Web 前端是零依赖的静态 HTML + 原生 JS modules + 手写 CSS，直接存放在 `core/web/static/` 下，由 Python `http.server` 直接服务。这套方案在只有两三个页面时很轻，但随着 `x` 命令功能持续增长（todo / secret / note / diary / config …），Web UI 需要长期跟进，手写 DOM 字符串模板、手动事件绑定、手动状态同步已经成为维护负担，且容易引入 XSS 与状态不一致问题。

用户明确决定：Web UI 要**一步到位**重写，长期维护，持续跟进 CLI 功能。

## 决策

1. 前端采用 **Vue 3（`<script setup>` SFC）+ Vue Router 4（hash 模式）+ Pinia**，用 **Vite** 构建。
2. 所有前端**源码**集中在仓库根目录的 `web/` 文件夹内（`web/src/**`、`web/vite.config.js`、`web/package.json`）。这是用户硬性要求：Web 实现只在 `web/` 文件夹。
3. Vite 的 `build.outDir` 指向 `../core/web/static`，`emptyOutDir: true`。`core/web/static/` 从此**只存放构建产物**，不再手写。
4. 构建产物**提交进 git**。理由：Python 包的分发模型要求 `pip install` 后无需 Node 即可 `x web`；产物入库保证源码安装、PyInstaller 打包、CI 冒烟测试都能直接拿到静态资源。
5. Python 运行时保持 stdlib-only：Node/Vite 仅是**开发期**工具链，不进入 `dependencies`。
6. `core/web/server.py` 不变：继续以 `core/web/static/` 为静态根，鉴权、路由、API 全部不动。前端通过同源 `fetch` 调 REST API。
7. 路由用 hash 模式（`#/tasks` 等），与原 `#tasks` 形态一致；无需服务端 history fallback。

## 备选方案

- **A. 保持原生 JS**：维护成本随功能增长失控，否决。
- **B. Vue 3 no-build（本地 vendor ESM runtime）**：无 SFC、无构建优化，长期维护体验差，且仍需 vendor 第三方文件，否决。
- **C. 产物不入库，发布流程里构建**：要求所有开发者与打包机装 Node，且源码安装场景（`pip install .`）会拿不到静态文件，否决。

## 影响

- 新增开发期前置条件：修改 Web 前端需 Node ≥ 20.19 或 ≥ 22.12，并运行
  `cd web && npm ci`。Vite 8 使用 Rolldown，删除了不再支持的对象形式
  `manualChunks`；路由级动态导入继续负责拆包。
- `tests/test_web_frontend.py` 从断言 JS 源码字符串改为断言构建产物契约（无外链、无明文泄露路径、产物结构完整）。
- 打包（PyInstaller spec、setuptools package-data）路径不变，继续收集 `core/web/static/**`。
- `.gitignore` 增加 `web/node_modules/` 与 `web/dist/`（如使用临时 dist）。

## 不变量（迁移后仍成立）

- `X-Web-Token` 鉴权与 401 → 登录页流程
- 密钥列表绝不加载明文 `value`；查看明文前必须警告确认
- 构建产物零外链（无 CDN）
- 登录页无障碍属性（`aria-describedby`、`role="alert"`、`autocomplete="current-password"`）
- 响应式断点、`prefers-reduced-motion`、`:focus-visible`
