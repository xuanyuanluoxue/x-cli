// views/secret-view.js — 单个密钥查看（含 value）
//
// 重要安全流程：
//   1. 进入页面先弹 ⚠️ 警告 modal（用户必须点确认）
//   2. 确认后才调 GET /api/secrets/:name 拉 value
//   3. value 默认以 password 形式显示，眼睛按钮可切换可见
//   4. 复制按钮 → navigator.clipboard.writeText
//   5. 离开页面 / 刷新 = 重新走警告流程（不缓存 value）
//
// 切记：此 view 是整个 app 唯一会拉明文 value 的地方。

import { api } from "../api.js";
import {
  escapeHtml, formatTimestamp, toast, copyToClipboard, confirmModal, navigate,
} from "../utils.js";

export function render(name) {
  const root = document.createElement("div");
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>🔐 查看密钥</h1>
        <div class="subtitle">明文 value 仅在此页显示，请确认环境安全</div>
      </div>
    </div>
    <div class="secret-view-card card" id="view-card">
      <div class="empty">
        <div class="empty-icon">⏳</div>
        <div class="empty-title">准备就绪…</div>
        <div class="empty-hint">请先确认查看警告</div>
      </div>
    </div>
  `;

  // 异步：先警告 → 用户确认 → 拉数据
  queueMicrotask(() => showWarningThenLoad(name));
  return Promise.resolve(root);
}

async function showWarningThenLoad(name) {
  const ok = await confirmModal({
    title: "⚠️ 你正在查看明文密钥",
    body:
      "value 会在浏览器内存中显示，可能被屏幕录制 / 浏览器历史 / 调试工具捕获。\n\n" +
      "请确认你处于安全环境，且离开时已关闭此页。\n\n" +
      "是否继续？",
    confirmText: "我已了解，继续查看",
    cancelText: "取消",
  });
  if (!ok) {
    navigate("#secrets");
    return;
  }

  const card = document.getElementById("view-card");
  if (!card) return;
  card.innerHTML = `<div class="empty"><div class="empty-icon">⏳</div><div class="empty-title">加载中…</div></div>`;

  try {
    const secret = await api.getSecret(name);
    renderSecret(secret);
  } catch (e) {
    if (e.code === "not_found") {
      card.innerHTML = `
        <div class="error-page">
          <div class="error-icon">🔍</div>
          <h2>密钥不存在</h2>
          <p>name = <code>${escapeHtml(name)}</code> 在密钥库里找不到。</p>
          <a class="btn" href="#secrets">返回列表</a>
        </div>
      `;
    } else if (e.code === "unauthorized") {
      // api.js 处理跳转
    } else {
      card.innerHTML = `
        <div class="error-page">
          <div class="error-icon">💥</div>
          <h2>加载失败</h2>
          <p>${escapeHtml(e.message)}</p>
          <a class="btn" href="#secrets">返回列表</a>
        </div>
      `;
    }
  }
}

function renderSecret(s) {
  const card = document.getElementById("view-card");
  if (!card) return;
  const cat = s.category || "default";

  card.innerHTML = `
    <div class="secret-header">
      <h2>${escapeHtml(s.name)}</h2>
      <span class="category-badge">${escapeHtml(cat)}</span>
    </div>

    ${s.note ? `<div class="note-block">${escapeHtml(s.note)}</div>` : ""}

    <div class="value-block">
      <div class="value-label">🔑 Value</div>
      <div class="value-display">
        <input type="password" class="value" id="secret-value" value="${escapeHtml(s.value || "")}" readonly autocomplete="off">
        <div class="value-actions">
          <button type="button" class="icon-btn" id="toggle-btn" title="显示 / 隐藏">👁️</button>
          <button type="button" class="icon-btn" id="copy-btn" title="复制到剪贴板">📋</button>
        </div>
      </div>
    </div>

    <dl class="meta">
      <dt>名称</dt><dd>${escapeHtml(s.name)}</dd>
      <dt>分组</dt><dd>${escapeHtml(cat)}</dd>
      <dt>创建</dt><dd>${escapeHtml(formatTimestamp(s.created_at))}</dd>
      <dt>更新</dt><dd>${escapeHtml(formatTimestamp(s.updated_at))}</dd>
    </dl>

    <div class="form-actions">
      <button type="button" class="btn btn-danger" id="delete-btn">删除</button>
      <div class="right">
        <a class="btn" href="#secrets">返回</a>
        <a class="btn btn-primary" href="#secrets/${encodeURIComponent(s.name)}/edit">编辑</a>
      </div>
    </div>
  `;

  const valueInput = document.getElementById("secret-value");
  const toggleBtn = document.getElementById("toggle-btn");
  const copyBtn = document.getElementById("copy-btn");
  const deleteBtn = document.getElementById("delete-btn");

  // 切换显示
  let visible = false;
  toggleBtn.addEventListener("click", () => {
    visible = !visible;
    valueInput.type = visible ? "text" : "password";
    toggleBtn.textContent = visible ? "🙈" : "👁️";
    toggleBtn.title = visible ? "隐藏" : "显示";
  });

  // 复制
  copyBtn.addEventListener("click", async () => {
    const ok = await copyToClipboard(s.value || "");
    if (ok) toast("✅ 已复制到剪贴板", "success");
    else toast("❌ 复制失败，请手动复制", "error");
  });

  // 删除
  deleteBtn.addEventListener("click", async () => {
    const ok = await confirmModal({
      title: "删除密钥",
      body: `确定要删除「${s.name}」吗？此操作不可撤销。`,
      confirmText: "确认删除",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteSecret(s.name);
      toast("✅ 已删除", "success");
      navigate("#secrets");
    } catch (e) {
      toast("❌ 删除失败：" + e.message, "error");
    }
  });
}
