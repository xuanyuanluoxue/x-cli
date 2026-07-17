// router.js — 简单 hash router
//
// 路由表：
//   #login                 → views/login.js
//   #tasks                 → views/tasks.js
//   #tasks/new             → views/task-edit.js (空)
//   #tasks/:id             → views/task-edit.js (id)
//   #secrets               → views/secrets.js
//   #secrets/new           → views/secret-edit.js (空)
//   #secrets/:name         → views/secret-view.js (name)
//   #secrets/:name/edit    → views/secret-edit.js (name)
//   #stats                 → views/stats.js
//
// 规则：未登录访问任何非 #login 路由 → 跳 #login。
// 401 由 api.js 处理（fetch 失败时清 token + 跳 login）。

import { hasToken, clearToken } from "./auth.js";

const routes = [
  { pattern: /^#login$/,                  loader: () => import("./views/login.js"),        pickParams: () => [] },
  { pattern: /^#tasks$/,                  loader: () => import("./views/tasks.js"),         pickParams: () => [] },
  { pattern: /^#tasks\/new$/,             loader: () => import("./views/task-edit.js"),    pickParams: () => ["new"] },
  { pattern: /^#tasks\/([^/]+)$/,         loader: () => import("./views/task-edit.js"),    pickParams: (m) => [m[1]] },
  { pattern: /^#secrets$/,                loader: () => import("./views/secrets.js"),      pickParams: () => [] },
  { pattern: /^#secrets\/new$/,           loader: () => import("./views/secret-edit.js"),  pickParams: () => ["new"] },
  { pattern: /^#secrets\/([^/]+)\/edit$/, loader: () => import("./views/secret-edit.js"),  pickParams: (m) => [m[1]] },
  { pattern: /^#secrets\/([^/]+)$/,       loader: () => import("./views/secret-view.js"),  pickParams: (m) => [m[1]] },
  { pattern: /^#stats$/,                  loader: () => import("./views/stats.js"),        pickParams: () => [] },
];

function matchRoute(hash) {
  for (const r of routes) {
    const m = hash.match(r.pattern);
    if (m) return { route: r, params: r.pickParams(m) };
  }
  return null;
}

function setActiveNav(hash) {
  // 高亮顶部 nav：精确匹配 + 子路径都算
  document.querySelectorAll("#topbar .nav-link").forEach((a) => {
    a.classList.remove("active");
    const target = a.getAttribute("data-route");
    if (!target || target === "#login") return;
    if (hash === target || hash.startsWith(target + "/")) {
      a.classList.add("active");
    }
  });
}

function setAuthClass() {
  document.body.classList.toggle("is-authed", hasToken());
}

async function renderRoute() {
  let hash = window.location.hash || "#tasks";
  // 未登录且非 login 路由 → 跳 login
  if (!hasToken() && hash !== "#login") {
    window.location.hash = "#login";
    return;  // hashchange 会重新触发
  }
  // 已登录且在 login 页 → 跳 tasks
  if (hasToken() && hash === "#login") {
    window.location.hash = "#tasks";
    return;
  }

  const match = matchRoute(hash);
  const main = document.getElementById("main");
  if (!main) return;

  if (!match) {
    main.innerHTML = `
      <div class="error-page">
        <div class="error-icon">🚧</div>
        <h2>页面不存在</h2>
        <p>找不到路径 <code>${hash}</code>，试试侧栏导航？</p>
        <a href="#tasks" class="btn btn-primary">返回任务列表</a>
      </div>
    `;
    setActiveNav("#tasks");
    setAuthClass();
    return;
  }

  setActiveNav(hash);
  setAuthClass();

  try {
    const mod = await match.route.loader();
    const factory = mod.render || mod.default;
    if (typeof factory !== "function") {
      throw new Error("view module must export render()");
    }
    const node = await factory(...match.params);
    if (!node) {
      console.warn(`[router] view ${hash} returned null/undefined`);
      return;
    }
    main.innerHTML = "";
    main.appendChild(node);
    // 调用 view 的 afterMount（如有）— 让 view 可以在挂载后做事件绑定
    if (typeof mod.afterMount === "function") {
      try { mod.afterMount(...match.params); } catch (e) { console.error(e); }
    }
    // 滚到顶
    window.scrollTo({ top: 0, behavior: "instant" });
  } catch (e) {
    console.error(`[router] failed to render ${hash}`, e);
    if (e && e.code === "unauthorized") {
      // api.js 已经处理跳转，这里不重复渲染
      return;
    }
    main.innerHTML = `
      <div class="error-page">
        <div class="error-icon">💥</div>
        <h2>页面加载失败</h2>
        <p>${escapeHtml(e.message || String(e))}</p>
        <a href="#tasks" class="btn">返回任务列表</a>
      </div>
    `;
  }
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = String(s == null ? "" : s);
  return d.innerHTML;
}

// ---- 初始化 ----

function initNavActions() {
  // 退出登录
  document.querySelectorAll('[aria-label="退出登录"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      clearToken();
      window.location.hash = "#login";
    });
  });
}

window.addEventListener("hashchange", renderRoute);
window.addEventListener("DOMContentLoaded", () => {
  initNavActions();
  renderRoute();
});
