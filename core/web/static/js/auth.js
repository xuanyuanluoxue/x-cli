// auth.js — token 管理（localStorage 持久化）
//
// 单一真相：localStorage["x_web_token"]
// 注意：localStorage 不是加密存储，但这是个人工具 + 本机 localhost，可接受。
// 服务端仍校验 X-Web-Token 头（详见 docs/web-api.md §3）。

const TOKEN_KEY = "x_web_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function hasToken() {
  return !!getToken();
}
