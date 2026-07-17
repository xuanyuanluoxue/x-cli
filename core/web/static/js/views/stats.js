// views/stats.js — 统计 dashboard
//
// 顶部卡片：total / 各 status 计数（含图标 + 颜色）
// 下面：
//   - 高优先级任务列表（priority=high，调 /api/tasks）
//   - 即将到期任务（≤7 天，客户端过滤 deadline）
//   - 过期任务（红色警示）

import { api } from "../api.js";
import {
  escapeHtml, statusMeta, priorityMeta, formatDate, deadlineState, navigate,
} from "../utils.js";

export function render() {
  const root = document.createElement("div");
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>📊 统计</h1>
        <div class="subtitle">任务总量 + 高优先级 + 即将到期 + 过期</div>
      </div>
    </div>
    <div id="stats-container">
      <div class="empty"><div class="empty-icon">⏳</div><div class="empty-title">加载中…</div></div>
    </div>
  `;
  queueMicrotask(() => loadAndRender());
  return Promise.resolve(root);
}

async function loadAndRender() {
  const container = document.getElementById("stats-container");
  if (!container) return;
  try {
    const [stats, allTasksRes] = await Promise.all([
      api.stats(),
      api.listTasks({ include_archived: "true" }),
    ]);
    const tasks = allTasksRes.tasks || [];
    renderStats(container, stats, tasks);
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

function renderStats(container, stats, tasks) {
  const bs = stats.by_status || {};
  const bp = stats.by_priority || {};

  // 即将到期（≤7 天）+ 过期
  const now = Date.now();
  const in7days = new Date(); in7days.setHours(0,0,0,0); in7days.setDate(in7days.getDate() + 7);
  const upcoming = [];
  const overdue = [];
  for (const t of tasks) {
    if (t.archived || t.status === "archived") continue;
    if (!t.deadline) continue;
    const d = new Date(t.deadline);
    if (isNaN(d.getTime())) continue;
    if (d.getTime() < now) overdue.push(t);
    else if (d.getTime() <= in7days.getTime()) upcoming.push(t);
  }
  upcoming.sort((a, b) => new Date(a.deadline) - new Date(b.deadline));
  overdue.sort((a, b) => new Date(a.deadline) - new Date(b.deadline));

  // 高优先级（active）
  const highPriority = tasks
    .filter(t => t.priority === "high" && !t.archived && t.status !== "archived")
    .sort((a, b) => {
      // 状态排序：in_progress > blocked > waiting > pending
      const order = { in_progress: 0, blocked: 1, waiting: 2, pending: 3 };
      return (order[a.status] ?? 9) - (order[b.status] ?? 9);
    });

  container.innerHTML = `
    <!-- 概览卡片 -->
    <div class="stats-grid">
      ${statCard("📦", "总任务", stats.total, "var(--text-primary)", "所有任务（含已归档）")}
      ${statCard("▶", "进行中", bs.in_progress || 0, "var(--status-in_progress)", "")}
      ${statCard("⏳", "待办", bs.pending || 0, "var(--status-pending)", "")}
      ${statCard("⛔", "阻塞", bs.blocked || 0, "var(--status-blocked)", "")}
      ${statCard("⌛", "等待", bs.waiting || 0, "var(--status-waiting)", "")}
      ${statCard("✅", "已归档", bs.archived || 0, "var(--status-archived)", "")}
    </div>

    <!-- 高优先级 / 即将到期 / 过期 -->
    <div class="stats-sections">
      ${sectionCard(
        "🔥 高优先级",
        highPriority,
        (t) => taskItemHtml(t, true),
        "没有高优先级任务 ✨",
      )}
      ${sectionCard(
        "⚠️ 即将到期（≤7 天）",
        upcoming,
        (t) => taskItemHtml(t, false, "soon"),
        "未来 7 天无任务到期",
      )}
      ${sectionCard(
        "🚨 已过期",
        overdue,
        (t) => taskItemHtml(t, false, "overdue"),
        "无过期任务 🎉",
      )}
    </div>
  `;

  // 行点击跳详情
  container.querySelectorAll(".stats-task-row").forEach((tr) => {
    tr.addEventListener("click", () => {
      const id = tr.getAttribute("data-id");
      navigate("#tasks/" + encodeURIComponent(id));
    });
  });
}

function statCard(icon, label, value, color, hint) {
  return `
    <div class="stat-card">
      <div class="stat-icon" style="background:${color}15; color:${color};">${icon}</div>
      <div class="stat-body">
        <div class="stat-label">${escapeHtml(label)}</div>
        <div class="stat-value" style="color:${color};">${value}</div>
        ${hint ? `<div class="stat-hint">${escapeHtml(hint)}</div>` : ""}
      </div>
    </div>
  `;
}

function sectionCard(title, tasks, rowFn, emptyHint) {
  const rows = tasks.length
    ? `<div class="stats-task-list">${tasks.map(rowFn).join("")}</div>`
    : `<div class="empty" style="padding:var(--space-8) var(--space-4);">
         <div class="empty-title">${escapeHtml(emptyHint)}</div>
       </div>`;
  return `
    <div class="card section-card">
      <div class="section-header">
        <h3>${title}</h3>
        <span class="muted text-sm">${tasks.length} 个</span>
      </div>
      ${rows}
    </div>
  `;
}

function taskItemHtml(t, showStatus, deadlineCls) {
  const ds = deadlineState(t.deadline);
  const cls = deadlineCls || (ds === "overdue" ? "overdue" : ds === "soon" ? "soon" : "");
  const sMeta = statusMeta(t.status);
  return `
    <div class="stats-task-row" data-id="${escapeHtml(t.id)}">
      <div class="st-name">
        <span>${escapeHtml(t.name)}</span>
        <span class="task-id">${escapeHtml(t.id)}</span>
      </div>
      <div class="st-meta">
        ${showStatus ? `<span class="badge status-${escapeHtml(t.status)}"><span>${sMeta.icon}</span><span>${escapeHtml(sMeta.label)}</span></span>` : ""}
        <span class="deadline ${cls}">${t.deadline ? escapeHtml(formatDate(t.deadline)) : "—"}</span>
      </div>
    </div>
  `;
}
