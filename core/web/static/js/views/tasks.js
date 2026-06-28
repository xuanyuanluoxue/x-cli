// views/tasks.js — 任务列表
//
// 工具栏：搜索 / 状态过滤 / 优先级过滤 / 显示已归档 开关 / + 新建
// 表格：图标 / 任务名(+id) / 状态 / 优先级 / 截止 / 标签 / 操作
// 关键：deadline 过期 = 红色，即将到期（≤3天） = 黄色

import { api, ApiError } from "../api.js";
import {
  escapeHtml, formatDate, statusMeta, priorityMeta,
  deadlineState, toast, navigate, debounce, confirmModal,
} from "../utils.js";

const STATUS_OPTIONS = [
  { value: "",            label: "全部状态" },
  { value: "pending",     label: "⏳ 待办" },
  { value: "in_progress", label: "▶ 进行中" },
  { value: "blocked",     label: "⛔ 阻塞" },
  { value: "waiting",     label: "⌛ 等待" },
];

const PRIORITY_OPTIONS = [
  { value: "",       label: "全部优先级" },
  { value: "high",   label: "🔥 高" },
  { value: "medium", label: "⚡ 中" },
  { value: "low",    label: "🐢 低" },
];

// ---- 当前过滤状态（hash 同步） ----
function readFiltersFromHash() {
  const h = window.location.hash;
  const q = h.includes("?") ? h.split("?")[1] : "";
  const params = new URLSearchParams(q);
  return {
    q:         params.get("q")         || "",
    status:    params.get("status")    || "",
    priority:  params.get("priority")  || "",
    tag:       params.get("tag")       || "",
    archived:  params.get("archived")  === "1",
  };
}

function writeFiltersToHash(filters) {
  const params = new URLSearchParams();
  if (filters.q)        params.set("q", filters.q);
  if (filters.status)   params.set("status", filters.status);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.tag)      params.set("tag", filters.tag);
  if (filters.archived) params.set("archived", "1");
  const qs = params.toString();
  const newHash = "#tasks" + (qs ? "?" + qs : "");
  if (window.location.hash !== newHash) {
    // 不触发 hashchange（用 replaceState 形式）
    history.replaceState(null, "", newHash);
  }
}

// ---- 渲染 ----

export function render() {
  const root = document.createElement("div");
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>📋 任务</h1>
        <div class="subtitle" id="tasks-summary">加载中…</div>
      </div>
      <div class="actions">
        <a class="btn btn-primary" href="#tasks/new">+ 新建任务</a>
      </div>
    </div>

    <div class="toolbar">
      <div class="toolbar-group">
        <input type="text" id="filter-q" placeholder="搜索任务名 / 标签…" autocomplete="off">
      </div>
      <div class="toolbar-group">
        <select id="filter-status">
          ${STATUS_OPTIONS.map(o => `<option value="${o.value}">${escapeHtml(o.label)}</option>`).join("")}
        </select>
        <select id="filter-priority">
          ${PRIORITY_OPTIONS.map(o => `<option value="${o.value}">${escapeHtml(o.label)}</option>`).join("")}
        </select>
        <label class="switch">
          <input type="checkbox" id="filter-archived">
          <span>显示已归档</span>
        </label>
      </div>
      <div class="toolbar-spacer"></div>
      <div class="toolbar-group">
        <button class="btn btn-ghost btn-sm" id="reset-filters" title="清空所有过滤条件">重置</button>
      </div>
    </div>

    <div id="tasks-container">
      <div class="empty"><div class="empty-icon">⏳</div><div class="empty-title">加载中…</div></div>
    </div>
  `;
  return Promise.resolve(root);
}

export async function afterMount() {
  const filters = readFiltersFromHash();
  // 把过滤值回填到 UI
  document.getElementById("filter-q").value        = filters.q;
  document.getElementById("filter-status").value   = filters.status;
  document.getElementById("filter-priority").value = filters.priority;
  document.getElementById("filter-archived").checked = filters.archived;

  // 事件绑定
  const reload = debounce(() => loadAndRender(), 150);
  document.getElementById("filter-q").addEventListener("input", () => { syncFiltersFromUI(); reload(); });
  document.getElementById("filter-status").addEventListener("change", () => { syncFiltersFromUI(); loadAndRender(); });
  document.getElementById("filter-priority").addEventListener("change", () => { syncFiltersFromUI(); loadAndRender(); });
  document.getElementById("filter-archived").addEventListener("change", () => { syncFiltersFromUI(); loadAndRender(); });
  document.getElementById("reset-filters").addEventListener("click", () => {
    document.getElementById("filter-q").value = "";
    document.getElementById("filter-status").value = "";
    document.getElementById("filter-priority").value = "";
    document.getElementById("filter-archived").checked = false;
    syncFiltersFromUI();
    loadAndRender();
  });

  await loadAndRender();
}

function syncFiltersFromUI() {
  const filters = {
    q:        document.getElementById("filter-q").value.trim(),
    status:   document.getElementById("filter-status").value,
    priority: document.getElementById("filter-priority").value,
    tag:      "",  // 暂未做 tag 过滤 UI
    archived: document.getElementById("filter-archived").checked,
  };
  writeFiltersToHash(filters);
}

async function loadAndRender() {
  const container = document.getElementById("tasks-container");
  if (!container) return;
  container.innerHTML = `<div class="empty"><div class="empty-icon">⏳</div><div class="empty-title">加载中…</div></div>`;

  const filters = readFiltersFromHash();
  try {
    const params = {};
    if (filters.status)   params.status = filters.status;
    if (filters.priority) params.priority = filters.priority;
    if (filters.tag)      params.tag = filters.tag;
    if (filters.archived) params.include_archived = "true";

    const { tasks } = await api.listTasks(params);
    renderTasks(tasks, filters);
  } catch (e) {
    if (e.code === "unauthorized") return;  // api.js 已跳
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

function renderTasks(tasks, filters) {
  const container = document.getElementById("tasks-container");
  const summary = document.getElementById("tasks-summary");

  // 客户端二次过滤：搜索 q（任务名 / 标签）
  let visible = tasks;
  if (filters.q) {
    const q = filters.q.toLowerCase();
    visible = tasks.filter(t => {
      if ((t.name || "").toLowerCase().includes(q)) return true;
      if ((t.id || "").toLowerCase().includes(q)) return true;
      if (Array.isArray(t.tags) && t.tags.some(tag => (tag || "").toLowerCase().includes(q))) return true;
      return false;
    });
  }

  summary.textContent = visible.length === tasks.length
    ? `共 ${tasks.length} 个任务${filters.archived ? "（含已归档）" : ""}`
    : `显示 ${visible.length} / ${tasks.length} 个任务`;

  if (visible.length === 0) {
    container.innerHTML = `
      <div class="card">
        <div class="empty">
          <div class="empty-icon">📭</div>
          <div class="empty-title">没有任务</div>
          <div class="empty-hint">点 "+ 新建任务" 创建第一个</div>
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
            <th>任务</th>
            <th>状态</th>
            <th>优先级</th>
            <th>截止</th>
            <th>标签</th>
            <th class="text-right">操作</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;

  // 行点击跳详情（操作按钮区域不触发）
  container.querySelectorAll("tbody tr.task-row").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target.closest(".actions-cell")) return;
      const id = tr.getAttribute("data-id");
      navigate("#tasks/" + encodeURIComponent(id));
    });
  });

  // 归档按钮（仅未归档行有）
  container.querySelectorAll("[data-archive]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const id = btn.getAttribute("data-archive");
      const ok = await confirmModal({
        title: "归档任务",
        body: `确认归档任务「${id}」？归档后可在已归档开关下查看。`,
        confirmText: "确认归档",
        danger: true,
      });
      if (!ok) return;
      try {
        await api.archiveTask(id, "done");
        toast("✅ 已归档", "success");
        await loadAndRender();
      } catch (err) {
        if (err.code === "duplicate") {
          toast("⚠️ 任务已归档", "warning");
        } else {
          toast("❌ 归档失败：" + err.message, "error");
        }
      }
    });
  });
}

function renderRow(t) {
  const sMeta = statusMeta(t.status);
  const pMeta = priorityMeta(t.priority);
  const ds = deadlineState(t.deadline);
  const deadlineClass = ds === "overdue" ? "overdue" : ds === "soon" ? "soon" : "";
  const isArchived = t.archived || t.status === "archived";
  const tags = Array.isArray(t.tags) ? t.tags : [];
  const tagsHtml = tags.length
    ? tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join("")
    : `<span class="muted text-sm">—</span>`;
  // 后端有时给 deadline = "none" / {} 等奇怪值，formatDate 失败时显示 —
  const deadlineText = t.deadline ? formatDate(t.deadline) : "";
  const deadlineDisplay = deadlineText || "—";

  return `
    <tr class="task-row ${isArchived ? "archived" : ""}" data-id="${escapeHtml(t.id)}">
      <td class="name-cell">
        <span>${escapeHtml(t.name)}</span>
        <span class="task-id">${escapeHtml(t.id)}</span>
      </td>
      <td class="status-cell">
        <span class="badge status-${escapeHtml(t.status || "pending")}">
          <span>${sMeta.icon}</span><span>${escapeHtml(sMeta.label)}</span>
        </span>
      </td>
      <td class="priority-cell">
        <span class="badge priority-${escapeHtml(t.priority || "low")}">
          <span>${pMeta.icon}</span><span>${escapeHtml(pMeta.label)}</span>
        </span>
      </td>
      <td><span class="deadline ${deadlineClass}">${escapeHtml(deadlineDisplay)}</span></td>
      <td class="tags-cell">${tagsHtml}</td>
      <td class="actions-cell">
        <a class="btn btn-sm" href="#tasks/${encodeURIComponent(t.id)}">编辑</a>
        ${!isArchived ? `<button class="btn btn-sm btn-danger" data-archive="${escapeHtml(t.id)}">归档</button>` : ""}
      </td>
    </tr>
  `;
}
