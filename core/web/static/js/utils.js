// utils.js — 通用 helper
//
// escapeHtml / formatDate / toast / modal / showConfirm / 状态-优先级映射
// 所有 view 共用。0 依赖。

/** 转义用户输入的字符串（防 XSS） */
export function escapeHtml(value) {
  if (value == null) return "";
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

/** 解析日期字符串（YYYY-MM-DD 或 ISO），返回 Date 或 null */
function parseDate(s) {
  if (!s) return null;
  if (s instanceof Date) return s;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

/** 格式化日期为 YYYY-MM-DD（用于 task.deadline） */
export function formatDate(s) {
  const d = parseDate(s);
  if (!d) return "";
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

/** 格式化 ISO timestamp 为人类可读（用于 secret.updated_at） */
export function formatTimestamp(s) {
  if (!s) return "—";
  const d = parseDate(s);
  if (!d) return String(s);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

/** 相对时间（"3 天前" / "刚刚"） */
export function formatRelative(s) {
  const d = parseDate(s);
  if (!d) return "—";
  const diffMs = Date.now() - d.getTime();
  const sec = Math.floor(diffMs / 1000);
  if (sec < 60) return "刚刚";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  return formatDate(s);
}

/** 计算 deadline 状态：'overdue' / 'soon' / 'ok' / 'none' */
export function deadlineState(deadline) {
  if (!deadline) return "none";
  const d = parseDate(deadline);
  if (!d) return "none";
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const diffDays = Math.floor((d.getTime() - now.getTime()) / 86400000);
  if (diffDays < 0) return "overdue";
  if (diffDays <= 3) return "soon";
  return "ok";
}

/** 状态 / 优先级 → 图标 + 中文标签 */
const STATUS_META = {
  pending:      { icon: "⏳", label: "待办" },
  in_progress:  { icon: "▶",  label: "进行中" },
  blocked:      { icon: "⛔", label: "阻塞" },
  waiting:      { icon: "⌛", label: "等待" },
  archived:     { icon: "✅", label: "已归档" },
};

const PRIORITY_META = {
  high:   { icon: "🔥", label: "高" },
  medium: { icon: "⚡", label: "中" },
  low:    { icon: "🐢", label: "低" },
};

export function statusMeta(s) {
  return STATUS_META[s] || { icon: "•", label: String(s || "") };
}

export function priorityMeta(p) {
  return PRIORITY_META[p] || { icon: "•", label: String(p || "") };
}

export const ARCHIVE_REASONS = {
  done:      "完成",
  cancelled: "取消",
  expired:   "过期",
  failed:    "失败",
};

// ============================================================
//  toast
// ============================================================

/** 触发 toast 通知（自动消失） */
export function toast(message, type = "info", duration = 2400) {
  const container = document.getElementById("toast-container");
  if (!container) {
    console.log(`[toast:${type}]`, message);
    return;
  }
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 200ms";
    setTimeout(() => el.remove(), 220);
  }, duration);
}

// ============================================================
//  modal
// ============================================================

/**
 * 弹一个 modal，返回 close 回调。
 * 用户点 backdrop / × 关闭 / Escape 关闭。
 */
export function openModal(contentEl) {
  const container = document.getElementById("modal-container");
  if (!container) return () => {};

  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const modal = document.createElement("div");
  modal.className = "modal";
  modal.appendChild(contentEl);
  backdrop.appendChild(modal);
  container.appendChild(backdrop);

  const close = () => {
    backdrop.remove();
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (e) => {
    if (e.key === "Escape") close();
  };
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) close();
  });
  document.addEventListener("keydown", onKey);

  return close;
}

/**
 * 二次确认 modal，返回 Promise<boolean>。
 * @param {Object} opts
 * @param {string} opts.title
 * @param {string} opts.body
 * @param {string} opts.confirmText - 默认 "确认"
 * @param {string} opts.cancelText - 默认 "取消"
 * @param {string} opts.danger - true 显示红色确认按钮
 */
export function confirmModal({
  title,
  body,
  confirmText = "确认",
  cancelText = "取消",
  danger = false,
}) {
  return new Promise((resolve) => {
    const content = document.createElement("div");
    content.innerHTML = `
      <h3>${escapeHtml(title)}</h3>
      <div class="modal-body">${escapeHtml(body)}</div>
      <div class="modal-actions">
        <button class="btn cancel-btn">${escapeHtml(cancelText)}</button>
        <button class="btn ${danger ? "btn-danger-solid" : "btn-primary"} confirm-btn">${escapeHtml(confirmText)}</button>
      </div>
    `;
    const close = openModal(content);
    content.querySelector(".cancel-btn").onclick = () => { close(); resolve(false); };
    content.querySelector(".confirm-btn").onclick = () => { close(); resolve(true); };
  });
}

// ============================================================
//  misc
// ============================================================

/** 通用 navigate */
export function navigate(hash) {
  if (window.location.hash === hash) {
    // 强制刷新（hash 不变的情况）
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    window.location.hash = hash;
  }
}

/** 防抖 */
export function debounce(fn, delay = 200) {
  let timer = null;
  return function (...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

/** 安全复制到剪贴板 */
export async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    // fallback
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (e) {
    console.error("copy failed", e);
    return false;
  }
}
