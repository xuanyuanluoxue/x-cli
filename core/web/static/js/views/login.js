// views/login.js — 登录页
//
// 居中卡片 → 输入 token → 调 GET /api/tasks 验证 → 成功存 localStorage 跳 #tasks
// 验证策略：先调 /api/health（无需 token）确认服务在线，再用 token 调 /api/tasks 验证 token。
// 这样如果服务挂了，错误信息更准（"服务未启动" vs "token 错误"）。

import { api, ApiError } from "../api.js";
import { setToken, getToken, clearToken } from "../auth.js";
import { toast, escapeHtml } from "../utils.js";

export function render() {
  const root = document.createElement("div");
  root.className = "login-root";
  root.innerHTML = `
    <div class="login-card card">
      <div class="login-header">
        <div class="login-icon">🔐</div>
        <h1 class="login-title">x web 认证</h1>
        <p class="login-subtitle">请输入 <code>x web</code> 启动时终端打印的 Token</p>
      </div>
      <form class="login-form" autocomplete="off">
        <div class="field">
          <label for="token-input">Token</label>
          <input id="token-input" type="password" placeholder="32 字节 base64 字符串" required>
          <div class="help">默认每次启动重新生成；用 <code>--token &lt;固定值&gt;</code> 可固定</div>
          <div class="error" id="login-error"></div>
        </div>
        <div class="login-actions">
          <button class="btn btn-primary w-full" type="submit" id="login-submit">进入</button>
        </div>
      </form>
      <div class="login-foot">
        <p>忘了 token？回终端看 <code>x web</code> 的启动输出（每行会打一次）。</p>
      </div>
    </div>
  `;
  // 注入仅本 view 用的样式
  if (!document.getElementById("login-extra-style")) {
    const style = document.createElement("style");
    style.id = "login-extra-style";
    style.textContent = `
      .login-root { display: flex; align-items: center; justify-content: center; min-height: calc(100vh - 80px); padding: var(--space-6); }
      .login-card { width: 100%; max-width: 420px; }
      .login-header { text-align: center; margin-bottom: var(--space-6); }
      .login-icon { font-size: 44px; margin-bottom: var(--space-2); }
      .login-title { font-size: var(--text-2xl); font-weight: 600; margin-bottom: var(--space-1); }
      .login-subtitle { color: var(--text-secondary); font-size: var(--text-sm); line-height: var(--leading-relaxed); }
      .login-subtitle code { background: var(--bg-secondary); padding: 1px 6px; border-radius: var(--radius-sm); }
      .login-actions { margin-top: var(--space-5); }
      .login-foot { margin-top: var(--space-5); padding-top: var(--space-4); border-top: 1px solid var(--border); text-align: center; font-size: var(--text-xs); color: var(--text-tertiary); }
      .login-foot code { background: var(--bg-secondary); padding: 1px 5px; border-radius: var(--radius-sm); }
    `;
    document.head.appendChild(style);
  }
  return Promise.resolve(root);
}

export async function afterMount() {
  // 如果已经有 token 但用户在登录页，直接尝试一次验证
  // opt-in: CLI 启动时若带 --auto-token-url，URL 含 ?token=xxx。
  // 这里取一次 → 存 localStorage → 立即清掉 URL（防浏览器历史/同步泄露）→ 验证。
  const urlToken = new URLSearchParams(window.location.search).get("token");
  if (urlToken) {
    setToken(urlToken);
    // 关键：URL 里的 token 立刻清掉（history.replaceState 不进 history）
    const cleanSearch = window.location.search
      .replace(/[?&]token=[^&]*/g, "")
      .replace(/^&/, "?");
    const cleanUrl =
      window.location.pathname +
      (cleanSearch && cleanSearch !== "?" ? cleanSearch : "") +
      window.location.hash;
    window.history.replaceState({}, document.title, cleanUrl);
    try {
      await api.listTasks();
      window.location.hash = "#tasks";
      return;
    } catch (e) {
      // token 失效（server 重启）→ 清掉，让用户重新输入
      clearToken();
    }
  }

  if (getToken()) {
    try {
      await api.listTasks();
      window.location.hash = "#tasks";
      return;
    } catch (e) {
      clearToken();
    }
  }

  const form = document.querySelector(".login-form");
  const input = document.getElementById("token-input");
  const submitBtn = document.getElementById("login-submit");
  const errorEl = document.getElementById("login-error");
  input.focus();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const token = input.value.trim();
    errorEl.textContent = "";
    if (!token) {
      errorEl.textContent = "请输入 token";
      return;
    }
    submitBtn.disabled = true;
    const original = submitBtn.textContent;
    submitBtn.textContent = "验证中…";

    try {
      // 先 health（确认服务在）
      try {
        await api.health();
      } catch (e) {
        throw new ApiError("后端服务未启动或不可达，请先在终端运行 `x web`", "backend_down", 0);
      }
      // 用 token 调 /api/tasks 验证
      setToken(token);
      await api.listTasks();
      toast("✅ 登录成功", "success");
      window.location.hash = "#tasks";
    } catch (err) {
      clearToken();
      const msg = err instanceof ApiError ? err.message : String(err);
      errorEl.textContent = msg || "Token 无效";
      input.select();
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = original;
    }
  });
}
