// stores/auth.js — token 状态（localStorage 单一真相）
//
// localStorage["x_web_token"] 是唯一持久化位置。
// store 只是它的响应式镜像，便于路由守卫和组件订阅。
import { defineStore } from "pinia";

const TOKEN_KEY = "x_web_token";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY),
    authRequired: null,
    secretConfirmationRequired: true,
    initialized: false,
  }),
  getters: {
    isAuthed: (s) => s.authRequired === false || !!s.token,
  },
  actions: {
    setAuthRequired(required) {
      this.authRequired = !!required;
      this.initialized = true;
      if (!this.authRequired) this.clearToken();
    },
    setToken(token) {
      this.token = token;
      localStorage.setItem(TOKEN_KEY, token);
    },
    clearToken() {
      this.token = null;
      localStorage.removeItem(TOKEN_KEY);
    },
    setSecretConfirmationRequired(required) {
      this.secretConfirmationRequired = required !== false;
    },
  },
});
