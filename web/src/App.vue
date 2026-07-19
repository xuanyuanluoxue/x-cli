<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.js";
import AppToast from "@/components/AppToast.vue";
import AppModal from "@/components/AppModal.vue";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const navOpen = ref(false);

const NAV = [
  { to: "/tasks", label: "任务", key: "tasks" },
  { to: "/secrets", label: "密钥", key: "secrets" },
  { to: "/stats", label: "统计", key: "stats" },
];

const isLogin = computed(() => route.name === "login");
const routeLabel = computed(() => route.meta.label || "控制台");

function isActive(item) {
  return route.path === item.to || route.path.startsWith(item.to + "/");
}

function logout() {
  auth.clearToken();
  navOpen.value = false;
  router.push({ name: "login" });
}

// 路由变化时收起移动端抽屉
watch(() => route.fullPath, () => { navOpen.value = false; });
</script>

<template>
  <!-- 登录页：全屏，无壳 -->
  <router-view v-if="isLogin" />

  <!-- 已登录：应用壳 -->
  <div v-else class="shell" :class="{ 'nav-open': navOpen }">
    <aside class="sidebar" aria-label="主导航">
      <router-link class="brand" to="/tasks" aria-label="x console 首页">
        <span class="brand-mark" aria-hidden="true">x</span>
        <span class="brand-name">console</span>
      </router-link>

      <nav class="nav">
        <router-link
          v-for="item in NAV"
          :key="item.key"
          :to="item.to"
          class="nav-link"
          :class="{ active: isActive(item) }"
          :aria-current="isActive(item) ? 'page' : undefined"
        >{{ item.label }}</router-link>
      </nav>

      <div class="sidebar-foot">
        <div class="session">
          <span class="session-dot" aria-hidden="true"></span>
          <span class="session-text">本机会话</span>
        </div>
        <button v-if="auth.authRequired" class="btn btn-ghost btn-sm logout" type="button" @click="logout">退出</button>
      </div>
    </aside>

    <div class="backdrop" aria-hidden="true" @click="navOpen = false"></div>

    <div class="main-col">
      <header class="topbar">
        <button
          class="btn btn-ghost btn-sm menu-btn"
          type="button"
          :aria-expanded="navOpen"
          aria-label="打开导航"
          @click="navOpen = !navOpen"
        >☰</button>
        <div class="crumb">
          <span class="crumb-root">x console</span>
          <span class="crumb-sep" aria-hidden="true">/</span>
          <strong>{{ routeLabel }}</strong>
        </div>
      </header>

      <main class="main" tabindex="-1">
        <router-view v-slot="{ Component }">
          <component :is="Component" :key="route.fullPath" />
        </router-view>
      </main>
    </div>
  </div>

  <AppToast />
  <AppModal />
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: var(--sidebar-w) 1fr;
  min-height: 100vh;
}

/* ---- 侧边栏 ---- */
.sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--s6);
  padding: var(--s5) var(--s4);
  background: var(--surface);
  border-right: 1px solid var(--line);
  position: sticky;
  top: 0;
  height: 100vh;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--s2);
  padding: 0 var(--s2);
  text-decoration: none;
  color: var(--ink);
}
.brand:hover { text-decoration: none; }
.brand-mark {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 700;
  color: var(--on-accent);
  background: var(--accent);
  border-radius: 7px;
}
.brand-name {
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: -0.01em;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}
.nav-link {
  display: flex;
  align-items: center;
  height: 34px;
  padding: 0 var(--s3);
  font-size: var(--text-base);
  color: var(--ink-2);
  border-radius: var(--r-md);
  text-decoration: none;
  transition: color var(--t-fast), background var(--t-fast);
}
.nav-link:hover {
  color: var(--ink);
  background: var(--bg-subtle);
  text-decoration: none;
}
.nav-link.active {
  color: var(--accent);
  background: var(--accent-soft);
  font-weight: 500;
}

.sidebar-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s2);
  padding-top: var(--s4);
  border-top: 1px solid var(--line);
}
.session {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-xs);
  color: var(--ink-3);
}
.session-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
}

/* ---- 顶栏 ---- */
.topbar {
  display: flex;
  align-items: center;
  gap: var(--s3);
  height: var(--topbar-h);
  padding: 0 var(--s6);
  background: var(--bg);
  border-bottom: 1px solid var(--line);
  position: sticky;
  top: 0;
  z-index: 10;
}
.menu-btn { display: none; }
.crumb {
  display: flex;
  align-items: baseline;
  gap: var(--s2);
  font-size: var(--text-sm);
  color: var(--ink-3);
}
.crumb strong {
  color: var(--ink);
  font-weight: 600;
}
.crumb-sep { color: var(--ink-4); }

/* ---- 主区 ---- */
.main-col {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.main {
  flex: 1;
  padding: var(--s8) var(--s6) var(--s16);
  outline: none;
}
.main > * {
  max-width: var(--content-max);
  margin: 0 auto;
}

.backdrop { display: none; }

/* ---- 移动端 ---- */
@media (max-width: 760px) {
  .shell { grid-template-columns: 1fr; }

  .sidebar {
    position: fixed;
    z-index: 60;
    left: 0;
    top: 0;
    bottom: 0;
    width: var(--sidebar-w);
    height: 100dvh;
    transform: translateX(-100%);
    transition: transform var(--t-norm);
    box-shadow: var(--shadow-pop);
  }
  .shell.nav-open .sidebar { transform: translateX(0); }

  .backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 50;
    background: rgba(26, 26, 24, 0.3);
    opacity: 0;
    pointer-events: none;
    transition: opacity var(--t-norm);
  }
  .shell.nav-open .backdrop {
    opacity: 1;
    pointer-events: auto;
  }

  .menu-btn { display: inline-flex; }
  .topbar { padding: 0 var(--s4); }
  .main { padding: var(--s5) var(--s4) var(--s12); }
}
</style>
