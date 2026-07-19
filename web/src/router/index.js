// router/index.js — hash 路由 + 登录守卫
//
// 路由形态与旧版一致（#/tasks 等），无需服务端 history fallback。
import { createRouter, createWebHashHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth.js";
import { api, setUnauthorizedHandler } from "@/api/client.js";

const routes = [
  { path: "/login", name: "login", component: () => import("@/views/LoginView.vue"), meta: { public: true, label: "认证" } },
  { path: "/tasks", name: "tasks", component: () => import("@/views/TaskListView.vue"), meta: { label: "任务" } },
  { path: "/tasks/new", name: "task-new", component: () => import("@/views/TaskEditView.vue"), meta: { label: "任务" } },
  { path: "/tasks/:id", name: "task-edit", component: () => import("@/views/TaskEditView.vue"), meta: { label: "任务" } },
  { path: "/secrets", name: "secrets", component: () => import("@/views/SecretListView.vue"), meta: { label: "密钥" } },
  { path: "/secrets/new", name: "secret-new", component: () => import("@/views/SecretEditView.vue"), meta: { label: "密钥" } },
  { path: "/secrets/:name", name: "secret-view", component: () => import("@/views/SecretView.vue"), meta: { label: "密钥" } },
  { path: "/secrets/:name/edit", name: "secret-edit", component: () => import("@/views/SecretEditView.vue"), meta: { label: "密钥" } },
  { path: "/stats", name: "stats", component: () => import("@/views/StatsView.vue"), meta: { label: "统计" } },
  { path: "/", redirect: "/tasks" },
  { path: "/:pathMatch(.*)*", name: "not-found", component: () => import("@/views/NotFoundView.vue"), meta: { label: "控制台" } },
];

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.initialized) {
    try {
      const health = await api.health();
      // Older backends omit this field and therefore stay protected.
      auth.setAuthRequired(health.auth_required !== false);
      auth.setSecretConfirmationRequired(
        health.secret_confirmation_required !== false,
      );
    } catch {
      // Service unreachable/unknown: fail closed and keep the login screen.
      auth.setAuthRequired(true);
      auth.setSecretConfirmationRequired(true);
    }
  }
  if (!auth.isAuthed && !to.meta.public) {
    return { name: "login" };
  }
  if (auth.isAuthed && to.name === "login") {
    return { name: "tasks" };
  }
  return true;
});

router.afterEach((to) => {
  const label = to.meta.label || "控制台";
  document.title = to.name === "login" ? "认证 · x console" : `${label} · x console`;
  document.body.dataset.route = to.path.replace(/^\//, "") || "tasks";
});

// API 401 → 跳登录（router 已就绪后注入，避免循环依赖）
setUnauthorizedHandler(() => {
  if (router.currentRoute.value.name !== "login") {
    router.push({ name: "login" });
  }
});
