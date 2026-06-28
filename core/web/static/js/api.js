// api.js — 后端 REST API 客户端
//
// 11 端点封装（详见 docs/web-api.md）：
//   GET    /api/health
//   GET    /api/tasks        listTasks(filters)
//   GET    /api/tasks/:id    getTask(id)
//   POST   /api/tasks        createTask(data)
//   PATCH  /api/tasks/:id    updateTask(id, data)
//   POST   /api/tasks/:id/archive  archiveTask(id, reason)
//   GET    /api/tasks/stats  stats()
//   GET    /api/secrets      listSecrets()
//   GET    /api/secrets/:n   getSecret(name) — 含 value
//   POST   /api/secrets      createSecret(data)
//   PATCH  /api/secrets/:n   updateSecret(name, data)
//   DELETE /api/secrets/:n   deleteSecret(name)
//
// 401 → 清 token + 跳 #login
// 非 2xx → 抛 ApiError

import { getToken, clearToken } from "./auth.js";

const API_BASE = "";  // 同源

export class ApiError extends Error {
  constructor(message, code, status) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };
  if (token) headers["X-Web-Token"] = token;

  let resp;
  try {
    resp = await fetch(API_BASE + path, { ...options, headers });
  } catch (e) {
    // 网络层失败（断网 / 服务挂了）
    throw new ApiError(`网络错误：${e.message}`, "network_error", 0);
  }

  // 401 → 跳登录
  if (resp.status === 401) {
    clearToken();
    if (window.location.hash !== "#login") {
      window.location.hash = "#login";
    }
    throw new ApiError("未授权，请输入 token", "unauthorized", 401);
  }

  // 204 无 body
  if (resp.status === 204) {
    return null;
  }

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

export const api = {
  // health（无需 token）
  health: () => apiFetch("/api/health"),

  // tasks
  listTasks: (filters = {}) => apiFetch("/api/tasks" + qs(filters)),
  getTask: (id) => apiFetch(`/api/tasks/${encodeURIComponent(id)}`),
  createTask: (data) =>
    apiFetch("/api/tasks", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateTask: (id, data) =>
    apiFetch(`/api/tasks/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  archiveTask: (id, reason) =>
    apiFetch(`/api/tasks/${encodeURIComponent(id)}/archive`, {
      method: "POST",
      body: JSON.stringify({ reason: reason || "done" }),
    }),
  stats: () => apiFetch("/api/tasks/stats"),

  // secrets
  listSecrets: () => apiFetch("/api/secrets"),
  getSecret: (name) =>
    apiFetch(`/api/secrets/${encodeURIComponent(name)}`),
  createSecret: (data) =>
    apiFetch("/api/secrets", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateSecret: (name, data) =>
    apiFetch(`/api/secrets/${encodeURIComponent(name)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteSecret: (name) =>
    apiFetch(`/api/secrets/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
};
