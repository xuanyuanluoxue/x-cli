// api/client.js — 后端 REST API 客户端（13 端点，见 docs/web-api.md）
//
// 401 → 清 token + 跳 #/login（通过注入的 onUnauthorized 回调，避免直接依赖 router）
// 非 2xx → 抛 ApiError
import { useAuthStore } from "@/stores/auth.js";

export class ApiError extends Error {
  constructor(message, code, status) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

// 由 router 安装时注入，避免循环依赖
let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

async function apiFetch(path, options = {}) {
  const auth = useAuthStore();
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };
  if (auth.token) headers["X-Web-Token"] = auth.token;

  let resp;
  try {
    resp = await fetch(path, { ...options, headers });
  } catch (e) {
    throw new ApiError(`网络错误：${e.message}`, "network_error", 0);
  }

  if (resp.status === 401) {
    auth.setAuthRequired(true);
    auth.clearToken();
    onUnauthorized();
    throw new ApiError("未授权，请输入 token", "unauthorized", 401);
  }

  if (resp.status === 204) return null;

  const data = await resp.json().catch(() => ({}));

  if (!resp.ok) {
    throw new ApiError(
      data.error || resp.statusText || "请求失败",
      data.code || "http_error",
      resp.status,
    );
  }
  return data;
}

function qs(params = {}) {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === "") continue;
    usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? "?" + s : "";
}

function unwrapResource(data, key) {
  if (data && typeof data === "object" && data[key]) return data[key];
  return data;
}

export const api = {
  health: () => apiFetch("/api/health"),

  // tasks
  listTasks: (filters = {}) => apiFetch("/api/tasks" + qs(filters)),
  getTask: (id) =>
    apiFetch(`/api/tasks/${encodeURIComponent(id)}`)
      .then((d) => unwrapResource(d, "task")),
  createTask: (data) =>
    apiFetch("/api/tasks", { method: "POST", body: JSON.stringify(data) })
      .then((d) => unwrapResource(d, "task")),
  updateTask: (id, data) =>
    apiFetch(`/api/tasks/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then((d) => unwrapResource(d, "task")),
  archiveTask: (id, reason) =>
    apiFetch(`/api/tasks/${encodeURIComponent(id)}/archive`, {
      method: "POST",
      body: JSON.stringify({ reason: reason || "done" }),
    }).then((d) => unwrapResource(d, "task")),
  stats: () => apiFetch("/api/tasks/stats"),

  // secrets
  listSecrets: () => apiFetch("/api/secrets"),
  getSecret: (name) =>
    apiFetch(`/api/secrets/${encodeURIComponent(name)}`)
      .then((d) => unwrapResource(d, "secret")),
  createSecret: (data) =>
    apiFetch("/api/secrets", { method: "POST", body: JSON.stringify(data) })
      .then((d) => unwrapResource(d, "secret")),
  updateSecret: (name, data) =>
    apiFetch(`/api/secrets/${encodeURIComponent(name)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then((d) => unwrapResource(d, "secret")),
  deleteSecret: (name) =>
    apiFetch(`/api/secrets/${encodeURIComponent(name)}`, { method: "DELETE" }),
};
