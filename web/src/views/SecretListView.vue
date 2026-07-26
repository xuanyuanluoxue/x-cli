<script setup>
// SecretListView — 密钥列表
// 硬约束：此视图任何路径都不获取、不渲染明文 value（不调 getSecret）。
import { ref, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client.js";
import { formatRelative } from "@/utils/format.js";
import { debounce } from "@/utils/dom.js";
import { toast, confirmDialog } from "@/utils/ui.js";
import AppLoader from "@/components/AppLoader.vue";

const router = useRouter();

const secrets = ref([]);
const loading = ref(true);
const loadError = ref("");
const q = ref("");

const reloadDebounced = debounce(load, 150);
watch(q, () => reloadDebounced());

const visible = computed(() => {
  if (!q.value) return secrets.value;
  const needle = q.value.toLowerCase().trim();
  return secrets.value.filter((s) =>
    (s.name || "").toLowerCase().includes(needle) ||
    (s.category || "").toLowerCase().includes(needle),
  );
});

const summary = computed(() => {
  if (loading.value) return "加载中…";
  return q.value
    ? `显示 ${visible.value.length} / ${secrets.value.length} 个密钥`
    : `共 ${secrets.value.length} 个密钥`;
});

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    const { secrets: list } = await api.listSecrets();
    secrets.value = list || [];
  } catch (e) {
    if (e.code === "unauthorized") return;
    loadError.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

function openSecret(s) {
  router.push({ name: "secret-view", params: { name: s.name } });
}

async function remove(s) {
  const ok = await confirmDialog({
    title: "删除密钥",
    body: `确认删除「${s.name}」？此操作不可撤销。`,
    confirmText: "确认删除",
    danger: true,
  });
  if (!ok) return;
  try {
    await api.deleteSecret(s.name);
    toast("已删除", "success");
    await load();
  } catch (err) {
    toast("删除失败：" + err.message, "error");
  }
}

onMounted(load);
</script>

<template>
  <div class="view-root">
    <div class="page-header">
      <div>
        <h1>密钥</h1>
        <div class="subtitle">{{ summary }}</div>
      </div>
      <div class="actions">
        <router-link class="btn btn-primary" :to="{ name: 'secret-new' }">新建密钥</router-link>
      </div>
    </div>

    <div class="toolbar">
      <div class="toolbar-group search-field">
        <input v-model="q" type="text" placeholder="搜索名称 / 分组…" autocomplete="off" aria-label="搜索密钥">
      </div>
      <div class="toolbar-spacer"></div>
      <div class="toolbar-group">
        <span class="security-note">列表不加载明文</span>
      </div>
    </div>

    <AppLoader v-if="loading" label="读取密钥索引" />

    <div v-else-if="loadError" class="error-page">
      <h2>加载失败</h2>
      <p>{{ loadError }}</p>
      <button class="btn" type="button" @click="load">重试</button>
    </div>

    <div v-else-if="visible.length === 0" class="card">
      <div class="empty">
        <div class="empty-title">{{ secrets.length === 0 ? "还没有密钥" : "没有匹配项" }}</div>
        <div class="empty-hint">{{ secrets.length === 0 ? "创建第一个本地密钥记录。列表始终不显示明文。" : "试试别的关键词。" }}</div>
      </div>
    </div>

    <div v-else class="table-wrap">
      <table class="data">
        <thead>
          <tr>
            <th>名称</th>
            <th>分组</th>
            <th>更新</th>
            <th class="text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in visible" :key="s.name" class="clickable" @click="openSecret(s)">
            <td data-label="名称"><span class="task-name">{{ s.name }}</span></td>
            <td data-label="分组"><span class="category-badge">{{ s.category || "default" }}</span></td>
            <td data-label="更新"><span class="muted text-sm">{{ formatRelative(s.updated_at) }}</span></td>
            <td class="text-right" data-label="操作" @click.stop>
              <router-link class="btn btn-sm" :to="{ name: 'secret-view', params: { name: s.name } }">查看</router-link>
              <router-link class="btn btn-sm" :to="{ name: 'secret-edit', params: { name: s.name } }">编辑</router-link>
              <button class="btn btn-sm btn-danger" type="button" @click="remove(s)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
td.text-right .btn { margin-left: 6px; }
</style>
