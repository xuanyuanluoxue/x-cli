<script setup>
// SecretEditView — 新建 / 编辑密钥
// 新建：name 可填，value 必填；编辑：name 只读，value 留空 = 不修改。
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/api/client.js";
import { toast } from "@/utils/ui.js";
import AppLoader from "@/components/AppLoader.vue";

const route = useRoute();
const router = useRouter();

const isNew = computed(() => route.name === "secret-new");
const secretName = computed(() => (isNew.value ? null : String(route.params.name)));

const loading = ref(!isNew.value);
const loadError = ref("");
const notFound = ref(false);
const original = ref(null);

const name = ref("");
const value = ref("");
const category = ref("default");
const note = ref("");
const valueVisible = ref(false);
const nameError = ref("");
const valueError = ref("");
const saving = ref(false);

async function loadSecret() {
  loading.value = true;
  try {
    const s = await api.getSecret(secretName.value);
    original.value = s;
    name.value = s.name || "";
    category.value = s.category || "default";
    note.value = s.note || "";
    value.value = ""; // 编辑模式不回填明文
  } catch (e) {
    if (e.code === "unauthorized") return;
    if (e.code === "not_found") notFound.value = true;
    else loadError.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function submit() {
  nameError.value = "";
  valueError.value = "";
  saving.value = true;
  try {
    if (isNew.value) {
      const n = name.value.trim();
      if (!n) { nameError.value = "名称不能为空"; saving.value = false; return; }
      if (!value.value) { valueError.value = "value 不能为空"; saving.value = false; return; }
      await api.createSecret({
        name: n,
        value: value.value,
        category: category.value.trim() || "default",
        note: note.value.trim(),
      });
      toast("已创建", "success");
      router.replace({ name: "secret-view", params: { name: n } });
    } else {
      const body = {
        category: category.value.trim() || "default",
      };
      if (value.value !== "") body.value = value.value;
      if (note.value.trim() !== (original.value.note || "")) body.note = note.value.trim();
      await api.updateSecret(original.value.name, body);
      toast("已保存", "success");
      router.push({ name: "secret-view", params: { name: original.value.name } });
    }
  } catch (err) {
    if (err.code === "duplicate") nameError.value = "同名密钥已存在";
    else toast((isNew.value ? "创建失败：" : "保存失败：") + err.message, "error");
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  if (!isNew.value) loadSecret();
});
</script>

<template>
  <div class="view-root">
    <div class="page-header">
      <div>
        <h1>{{ isNew ? "新建密钥" : "编辑密钥" }}</h1>
        <div class="subtitle">{{ isNew ? "建立一条仅存储在本地的密钥记录" : "更新密钥内容、分组与用途备注" }}</div>
      </div>
    </div>

    <AppLoader v-if="loading" label="读取密钥记录" />

    <div v-else-if="notFound" class="error-page">
      <h2>密钥不存在</h2>
      <p>name = <code>{{ secretName }}</code></p>
      <router-link class="btn" :to="{ name: 'secrets' }">返回列表</router-link>
    </div>

    <div v-else-if="loadError" class="error-page">
      <h2>加载失败</h2>
      <p>{{ loadError }}</p>
      <router-link class="btn" :to="{ name: 'secrets' }">返回列表</router-link>
    </div>

    <form v-else class="card form-card" autocomplete="off" @submit.prevent="submit">
      <div class="field">
        <label for="f-name">名称 <span class="required-mark">*</span></label>
        <input
          id="f-name"
          v-model="name"
          type="text"
          required
          maxlength="100"
          :readonly="!isNew"
          placeholder="如 minimax / github-token"
        >
        <div class="help">{{ isNew ? "建议用英文 / kebab-case" : "name 创建后不可修改" }}</div>
        <div class="error" role="alert">{{ nameError }}</div>
      </div>

      <div class="field">
        <label for="f-value">Value <span v-if="isNew" class="required-mark">*</span></label>
        <div class="input-with-action">
          <input
            id="f-value"
            v-model="value"
            :type="valueVisible ? 'text' : 'password'"
            :required="isNew"
            autocomplete="new-password"
            :placeholder="isNew ? '输入密钥明文' : '留空则保持原 value'"
          >
          <button
            type="button"
            class="btn"
            :aria-pressed="valueVisible"
            :aria-label="valueVisible ? '隐藏明文' : '显示明文'"
            @click="valueVisible = !valueVisible"
          >{{ valueVisible ? "HIDE" : "SHOW" }}</button>
        </div>
        <div class="help">{{ isNew ? "明文存储在本地 JSON，不经过第三方" : "留空 = 不修改；填了 = 覆盖" }}</div>
        <div class="error" role="alert">{{ valueError }}</div>
      </div>

      <div class="field">
        <label for="f-category">分组</label>
        <input id="f-category" v-model="category" type="text" placeholder="default">
        <div class="help">可选；用于分类（如 "API"、"DB"、"SSH"）</div>
      </div>

      <div class="field">
        <label for="f-note">备注</label>
        <textarea id="f-note" v-model="note" rows="3" placeholder="来源、用途、轮转时间…"></textarea>
      </div>

      <div class="form-actions">
        <div></div>
        <div class="right">
          <router-link class="btn btn-ghost" :to="{ name: 'secrets' }">取消</router-link>
          <button type="submit" class="btn btn-primary" :disabled="saving">
            {{ saving ? (isNew ? "创建中…" : "保存中…") : (isNew ? "创建" : "保存") }}
          </button>
        </div>
      </div>
    </form>
  </div>
</template>

<style scoped>
.form-card { max-width: 560px; }
</style>
