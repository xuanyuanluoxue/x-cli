// utils/format.js — 日期 / 状态 / 优先级 显示逻辑（纯函数，无副作用）

function parseDate(s) {
  if (!s) return null;
  if (s instanceof Date) return s;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

export function formatDate(s) {
  const d = parseDate(s);
  if (!d) return "";
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

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

export function formatRelative(s) {
  const d = parseDate(s);
  if (!d) return "—";
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return "刚刚";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  return formatDate(s);
}

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

const STATUS_META = {
  pending:     { icon: "○", label: "待办" },
  in_progress: { icon: "↗", label: "进行中" },
  blocked:     { icon: "×", label: "阻塞" },
  waiting:     { icon: "…", label: "等待" },
  archived:    { icon: "✓", label: "已归档" },
};

const PRIORITY_META = {
  high:   { icon: "↑", label: "高" },
  medium: { icon: "—", label: "中" },
  low:    { icon: "↓", label: "低" },
};

export function statusMeta(s) {
  return STATUS_META[s] || { icon: "•", label: String(s || "") };
}

export function priorityMeta(p) {
  return PRIORITY_META[p] || { icon: "•", label: String(p || "") };
}

export const ARCHIVE_REASONS = {
  done: "完成",
  cancelled: "取消",
  expired: "过期",
  failed: "失败",
};
