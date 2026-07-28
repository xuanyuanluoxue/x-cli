<script setup>
import { ref, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { api, ApiError } from "@/api/client.js";
import { useAuthStore } from "@/stores/auth.js";
import { toast } from "@/utils/ui.js";

const router = useRouter();
const auth = useAuthStore();

const token = ref("");
const error = ref("");
const busy = ref(false);
const inputEl = ref(null);

// URL token 一次性消费（?token=xxx → 存 localStorage → 立即从 history 清除）
function consumeUrlToken() {
  const urlToken = new URLSearchParams(window.location.search).get("token");
  if (!urlToken) return false;
  auth.setToken(urlToken);
  const cleanSearch = window.location.search
    .replace(/[?&]token=[^&]*/g, "")
    .replace(/^&/, "?");
  const cleanUrl =
    window.location.pathname +
    (cleanSearch && cleanSearch !== "?" ? cleanSearch : "") +
    window.location.hash;
  window.history.replaceState({}, document.title, cleanUrl);
  return true;
}

onMounted(async () => {
  consumeUrlToken();
  if (auth.isAuthed) {
    try {
      await api.listTasks();
      router.replace({ name: "tasks" });
      return;
    } catch {
      auth.clearToken();
    }
  }
  await nextTick();
  inputEl.value?.focus();
});

async function submit() {
  error.value = "";
  const t = token.value.trim();
  if (!t) {
    error.value = "请输入 token";
    return;
  }
  busy.value = true;
  try {
    // 先 health（无需 token）确认服务在线，错误信息更准
    try {
      await api.health();
    } catch {
      throw new ApiError("后端服务未启动或不可达，请先在终端运行 `x web`", "backend_down", 0);
    }
    auth.setToken(t);
    await api.listTasks();
    toast("登录成功", "success");
    router.replace({ name: "tasks" });
  } catch (err) {
    auth.clearToken();
    error.value = err instanceof ApiError ? err.message : String(err) || "Token 无效";
    inputEl.value?.select();
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="login-stage">
    <div class="login-card">
      <div class="login-brand">
        <span class="brand-mark" aria-hidden="true">x</span>
        <span class="brand-name">console</span>
      </div>

      <h1 id="login-title">验证本地会话</h1>
      <p class="login-sub">输入启动 <code>x web</code> 时终端显示的 Token。</p>

      <form class="login-form" autocomplete="off" @submit.prevent="submit">
        <div class="field">
          <label for="token-input">Web Token</label>
          <input
            id="token-input"
            ref="inputEl"
            v-model="token"
            type="password"
            placeholder="粘贴 token"
            required
            autocomplete="current-password"
            aria-describedby="token-help login-error"
          >
          <div class="help" id="token-help">认证开启时默认每次启动重新生成；也可用 <code>--token</code> 固定。</div>
          <div class="error" id="login-error" role="alert">{{ error }}</div>
        </div>
        <button class="btn btn-primary w-full" type="submit" :disabled="busy">
          {{ busy ? "验证中…" : "进入控制台" }}
        </button>
      </form>

      <p class="login-foot">Token 仅保存在当前浏览器的 localStorage 中，不上传任何服务器。</p>
    </div>
  </div>
</template>

<style scoped>
.login-stage {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: var(--s6);
  background: var(--bg);
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  padding: var(--s8);
}

.login-brand {
  display: flex;
  align-items: center;
  gap: var(--s2);
  margin-bottom: var(--s8);
}
.brand-mark {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 700;
  color: var(--on-accent);
  background: var(--accent);
  border-radius: 7px;
}
.brand-name {
  font-size: var(--text-md);
  font-weight: 600;
}

h1 {
  font-size: var(--text-xl);
  margin-bottom: var(--s2);
}
.login-sub {
  font-size: var(--text-sm);
  color: var(--ink-3);
  margin-bottom: var(--s6);
}

.login-form .field { margin-bottom: var(--s5); }

.login-foot {
  margin-top: var(--s6);
  padding-top: var(--s4);
  border-top: 1px solid var(--line);
  font-size: var(--text-xs);
  color: var(--ink-4);
  line-height: var(--leading-normal);
}
</style>
