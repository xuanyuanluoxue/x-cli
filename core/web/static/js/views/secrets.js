// views/secrets.js — 密钥列表（绝不含 value）
//
// 硬约束：此 view 任何路径都不向 DOM 注入 value 字段。
// 点击行 → #secrets/:name（view），不是直接 edit。

import { api } from "../api.js";
import {
  escapeHtml, formatRelative, toast, navigate, debounce, confirmModal,
} from "../utils.js";

export function render() {
  const root = document.createElement("div");
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>🔐 密钥</h1>
        <div class="subtitle" id="secrets-summary">加载中…</div>
      </div>
      <div class="actions">
        <a class="btn btn-primary" href="#secrets/new">+ 新建密钥</a>
      </div>
    </div>

    <div class="toolbar">
      <div class="toolbar-group">
        <input type="text" id="filter-q" placeholder="搜索名称 / 备注…" autocomplete="off">
      </div>
      <div class="toolbar-spacer"></div>
      <div class="toolbar-group">
        <span class="muted text-xs">🔒 列表不含 value（与 CLI <code>x secret list</code> 一致）</span>
      </div>
    </div>

    <div id="secrets-container">
      <div class="empty"><div class="empty-icon">⏳</div><div class="empty-title">加载中…</div></div>
    </div>
  `;
  return Promise.resolve(root);
}

export async function afterMount() {
  const input = document.getElementById("filter-q");
  const reload = debounce(() => loadAndRender(), 150);
  input.addEventListener("input", reload);

  await loadAndRender();
}

async function loadAndRender() {
  const container = document.getElementById("secrets-container");
  const summary = document.getElementById("secrets-summary");
  if (!container) return;
  container.innerHTML = `<div class="empty"><div class="empty-icon">⏳</div><div class="empty-title">加载中…</div></div>`;

  try {
    const { secrets } = await api.listSecrets();
    renderList(secrets);
  } catch (e) {
    if (e.code === "unauthorized") return;
    container.innerHTML = `
      <div class="error-page">
        <div class="error-icon">💥</div>
        <h2>加载失败</h2>
        <p>${escapeHtml(e.message)}</p>
        <button class="btn" onclick="location.reload()">重试</button>
      </div>
    `;
  }
}

function renderList(secrets) {
  const container = document.getElementById("secrets-container");
  const summary = document.getElementById("secrets-summary");
  const q = (document.getElementById("filter-q").value || "").toLowerCase().trim();

  const visible = q
    ? secrets.filter(s =>
        (s.name || "").toLowerCase().includes(q) ||
        (s.category || "").toLowerCase().includes(q)
      )
    : secrets;

  summary.textContent = q
    ? `显示 ${visible.length} / ${secrets.length} 个密钥`
    : `共 ${secrets.length} 个密钥`;

  if (secrets.length === 0) {
    container.innerHTML = `
      <div class="card">
        <div class="empty">
          <div class="empty-icon">📭</div>
          <div class="empty-title">还没有密钥</div>
          <div class="empty-hint">点 "+ 新建密钥" 创建第一个</div>
        </div>
      </div>
    `;
    return;
  }

  if (visible.length === 0) {
    container.innerHTML = `
      <div class="card">
        <div class="empty">
          <div class="empty-icon">🔍</div>
          <div class="empty-title">没有匹配项</div>
          <div class="empty-hint">试试别的关键词</div>
        </div>
      </div>
    `;
    return;
  }

  const rows = visible.map(renderRow).join("");
  container.innerHTML = `
    <div class="table-wrap">
      <table class="data">
        <thead>
          <tr>
            <th>名称</th>
            <th>分组</th>
            <th>更新时间</th>
            <th class="text-right">操作</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;

  container.querySelectorAll("tbody tr.secret-row").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target.closest(".actions-cell")) return;
      const name = tr.getAttribute("data-name");
      navigate("#secrets/" + encodeURIComponent(name));
    });
  });

  // 删除按钮
  container.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const name = btn.getAttribute("data-delete");
      const ok = await confirmModal({
        title: "删除密钥",
        body: `确认删除「${name}」？此操作不可撤销。`,
        confirmText: "确认删除",
        danger: true,
      });
      if (!ok) return;
      try {
        await api.deleteSecret(name);
        toast("✅ 已删除", "success");
        await loadAndRender();
      } catch (err) {
        toast("❌ 删除失败：" + err.message, "error");
      }
    });
  });
}

function renderRow(s) {
  const cat = s.category || "default";
  const catClass = cat === "default" ? "cat-default" : "";
  return `
    <tr class="secret-row" data-name="${escapeHtml(s.name)}">
      <td class="name-cell">${escapeHtml(s.name)}</td>
      <td><span class="category-badge ${catClass}">${escapeHtml(cat)}</span></td>
      <td class="updated-cell">${escapeHtml(formatRelative(s.updated_at))}</td>
      <td class="actions-cell">
        <a class="btn btn-sm" href="#secrets/${encodeURIComponent(s.name)}">查看</a>
        <a class="btn btn-sm" href="#secrets/${encodeURIComponent(s.name)}/edit">编辑</a>
        <button class="btn btn-sm btn-danger" data-delete="${escapeHtml(s.name)}">删除</button>
      </td>
    </tr>
  `;
}
