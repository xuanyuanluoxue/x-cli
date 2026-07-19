<script setup>
// SecretView — 查看单个密钥（含明文 value）
//
// 安全流程（硬约束）：
//   1. 进入页面先弹警告 confirm，用户确认后才调 getSecret
//   2. value 默认 password 掩码显示，SHOW 按钮切换
//   3. COPY 复制到剪贴板
//   4. 不缓存：离开/刷新重新走警告流程
// 这是整个 app 唯一会拉明文 value 的视图。
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/api/client.js";
import { formatTimestamp } from "@/utils/format.js";
import { copyToClipboard } from "@/utils/dom.js";
import { toast, confirmDialog } from "@/utils/ui.js";
import AppLoader from "@/components/AppLoader.vue";

const route = useRoute();
const router = useRouter();
const name = String(route.params.name);

const stage = ref("confirm"); // confirm | loading | ready | not_found | error
const loadError = ref("");
const secret = ref(null);
const valueVisible = ref(false);

onMounted(async () => {
  const ok = await confirmDialog({
    title: "你正在查看明文密钥",
    body:
      "value 会在浏览器内存中显示，可能被屏幕录制 / 浏览器历史 / 调试工具捕获。\n\n" +
      "请确认你处于安全环境，且离开时已关闭此页。\n\n" +
      "是否继续？",
    confirmText: "我已了解，继续查看",
    cancelText: "取消",
  });
  if (!ok) {
    router.replace({ name: "secrets" });
    return;
  }

  stage.value = "loading";
  try {
    secret.value = await api.getSecret(name);
    stage.value = "ready";
  } catch (e) {
    if (e.code === "unauthorized") return;
    if (e.code === "not_found") stage.value = "not_found";
    else {
      loadError.value = e.message || "加载失败";
      stage.value = "error";
    }
  }
});

function toggleValue() {
  valueVisible.value = !valueVisible.value;
}

async function copyValue() {
  const ok = await copyToClipboard(secret.value?.value || "");
  toast(ok ? "已复制到剪贴板" : "复制失败，请手动复制", ok ? "success" : "error");
}

async function remove() {
  const ok = await confirmDialog({
    title: "删除密钥",
    body: `确定要删除「${secret.value.name}」吗？此操作不可撤销。`,
    confirmText: "确认删除",
    danger: true,
  });
  if (!ok) return;
  try {
    await api.deleteSecret(secret.value.name);
    toast("已删除", "success");
    router.push({ name: "secrets" });
  } catch (e) {
    toast("删除失败：" + e.message, "error");
  }
}
</script>

<template>
  <div class="view-root">
    <div class="page-header">
      <div>
        <h1>查看密钥</h1>
        <div class="subtitle">明文只在当前页面内存中短暂存在</div>
      </div>
    </div>

    <div v-if="stage === 'confirm'" class="card">
      <div class="empty">
        <div class="empty-title">等待安全确认</div>
        <div class="empty-hint">确认后才会向本地 API 请求明文</div>
      </div>
    </div>

    <AppLoader v-else-if="stage === 'loading'" label="读取加密记录" />

    <div v-else-if="stage === 'not_found'" class="error-page">
      <h2>密钥不存在</h2>
      <p>name = <code>{{ name }}</code> 在密钥库里找不到。</p>
      <router-link class="btn" :to="{ name: 'secrets' }">返回列表</router-link>
    </div>

    <div v-else-if="stage === 'error'" class="error-page">
      <h2>加载失败</h2>
      <p>{{ loadError }}</p>
      <router-link class="btn" :to="{ name: 'secrets' }">返回列表</router-link>
    </div>

    <div v-else-if="secret" class="card detail-card">
      <div class="secret-head">
        <h2>{{ secret.name }}</h2>
        <span class="category-badge">{{ secret.category || "default" }}</span>
      </div>

      <div v-if="secret.note" class="note-block">{{ secret.note }}</div>

      <div class="value-block">
        <div class="value-label">SECRET VALUE</div>
        <div class="value-row">
          <input
            :type="valueVisible ? 'text' : 'password'"
            class="value-input mono"
            :value="secret.value || ''"
            readonly
            autocomplete="off"
            aria-label="密钥明文"
          >
          <button
            type="button"
            class="btn btn-sm"
            :aria-pressed="valueVisible"
            :aria-label="valueVisible ? '隐藏明文' : '显示明文'"
            @click="toggleValue"
          >{{ valueVisible ? "HIDE" : "SHOW" }}</button>
          <button type="button" class="btn btn-sm" aria-label="复制到剪贴板" @click="copyValue">COPY</button>
        </div>
      </div>

      <dl class="meta">
        <div class="meta-row"><dt>名称</dt><dd>{{ secret.name }}</dd></div>
        <div class="meta-row"><dt>分组</dt><dd>{{ secret.category || "default" }}</dd></div>
        <div class="meta-row"><dt>创建</dt><dd>{{ formatTimestamp(secret.created_at) }}</dd></div>
        <div class="meta-row"><dt>更新</dt><dd>{{ formatTimestamp(secret.updated_at) }}</dd></div>
      </dl>

      <div class="form-actions">
        <button type="button" class="btn btn-danger" @click="remove">删除</button>
        <div class="right">
          <router-link class="btn" :to="{ name: 'secrets' }">返回</router-link>
          <router-link class="btn btn-primary" :to="{ name: 'secret-edit', params: { name: secret.name } }">编辑</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-card { max-width: 640px; }

.secret-head {
  display: flex;
  align-items: center;
  gap: var(--s3);
  margin-bottom: var(--s4);
}
.secret-head h2 {
  font-size: var(--text-xl);
  letter-spacing: -0.01em;
}

.note-block {
  padding: var(--s3) var(--s4);
  margin-bottom: var(--s5);
  font-size: var(--text-sm);
  color: var(--ink-2);
  background: var(--bg-subtle);
  border-radius: var(--r-md);
  white-space: pre-line;
}

.value-block { margin-bottom: var(--s6); }
.value-label {
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink-3);
  margin-bottom: var(--s2);
}
.value-row {
  display: flex;
  gap: var(--s2);
}
.value-input {
  flex: 1;
  height: 38px;
  padding: 0 var(--s3);
  font-size: var(--text-base);
  background: var(--bg-subtle);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-md);
  color: var(--ink);
}

.meta {
  display: flex;
  flex-direction: column;
  gap: var(--s2);
  margin: 0 0 var(--s2);
  padding: var(--s4) 0;
  border-top: 1px solid var(--line);
}
.meta-row {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: var(--s3);
  font-size: var(--text-sm);
}
.meta dt { color: var(--ink-3); }
.meta dd { margin: 0; color: var(--ink-2); }
</style>
