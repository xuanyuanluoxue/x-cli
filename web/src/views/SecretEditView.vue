<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/api/client.js";
import { confirmDialog, toast } from "@/utils/ui.js";
import AppLoader from "@/components/AppLoader.vue";
import SecretFieldsEditor from "@/components/SecretFieldsEditor.vue";

const route = useRoute();
const router = useRouter();

const isNew = computed(() => route.name === "secret-new");
const secretName = computed(() => (isNew.value ? null : String(route.params.name)));

const loading = ref(!isNew.value);
const loadError = ref("");
const notFound = ref(false);
const original = ref(null);
const editor = ref(null);

const name = ref("");
const category = ref("default");
const note = ref("");
const fields = ref([
  { label: "密钥", kind: "secret", value: "", primary: true },
]);

const nameError = ref("");
const fieldsError = ref("");
const saving = ref(false);

function normalizedFields() {
  return fields.value.map((field) => ({
    label: field.label.trim(),
    kind: field.kind,
    value: field.value,
    primary: Boolean(field.primary),
  }));
}

async function confirmAndLoad() {
  const confirmed = await confirmDialog({
    title: "编辑将读取全部字段值",
    body:
      "为了编辑多个参数，页面需要从本地密钥库读取普通文本和密钥明文。\n\n" +
      "这些内容只保留在当前页面内存中，不会写入浏览器存储。请确认当前环境安全。",
    confirmText: "我已了解，继续编辑",
    cancelText: "取消",
  });
  if (!confirmed) {
    router.replace({ name: "secrets" });
    return;
  }
  await loadSecret();
}

async function loadSecret() {
  loading.value = true;
  try {
    const secret = await api.getSecret(secretName.value);
    original.value = secret;
    name.value = secret.name || "";
    category.value = secret.category || "default";
    note.value = secret.note || "";
    fields.value = Array.isArray(secret.fields) && secret.fields.length
      ? secret.fields.map((field) => ({ ...field }))
      : [{ label: "密钥", kind: "secret", value: secret.value || "", primary: true }];
  } catch (error) {
    if (error.code === "unauthorized") return;
    if (error.code === "not_found") notFound.value = true;
    else loadError.value = error.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function submit() {
  nameError.value = "";
  fieldsError.value = "";

  const cleanName = name.value.trim();
  if (!cleanName) {
    nameError.value = "名称不能为空";
    return;
  }
  const issue = editor.value?.validate?.() || "";
  if (issue) {
    fieldsError.value = issue;
    return;
  }

  saving.value = true;
  const payload = {
    category: category.value.trim() || "default",
    note: note.value.trim(),
    fields: normalizedFields(),
  };
  try {
    if (isNew.value) {
      await api.createSecret({ name: cleanName, ...payload });
      toast("密钥记录已创建", "success");
      router.replace({ name: "secret-view", params: { name: cleanName } });
    } else {
      await api.updateSecret(original.value.name, payload);
      toast("全部字段已保存", "success");
      router.push({ name: "secret-view", params: { name: original.value.name } });
    }
  } catch (error) {
    if (error.code === "duplicate") nameError.value = "同名密钥已存在";
    else {
      fieldsError.value = error.code === "validation_error" ? error.message : "";
      toast((isNew.value ? "创建失败：" : "保存失败：") + error.message, "error");
    }
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  if (!isNew.value) confirmAndLoad();
});
</script>

<template>
  <div class="view-root">
    <div class="page-header">
      <div>
        <h1>{{ isNew ? "新建密钥" : "编辑密钥" }}</h1>
        <div class="subtitle">
          {{ isNew ? "把地址、账号和密钥收进同一条记录" : "调整字段、显示类型与主密钥" }}
        </div>
      </div>
    </div>

    <AppLoader v-if="loading" label="读取密钥字段" />

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
      <div class="identity-grid">
        <div class="field">
          <label for="f-name">名称 <span class="required-mark">*</span></label>
          <input
            id="f-name"
            v-model="name"
            type="text"
            required
            maxlength="100"
            :readonly="!isNew"
            placeholder="如 123pan.webdav"
          >
          <div class="help">{{ isNew ? "用于列表检索，创建后不可修改" : "名称创建后不可修改" }}</div>
          <div class="error" role="alert">{{ nameError }}</div>
        </div>

        <div class="field">
          <label for="f-category">分组</label>
          <input id="f-category" v-model="category" type="text" placeholder="default">
          <div class="help">例如 123pan、API、SSH</div>
        </div>
      </div>

      <SecretFieldsEditor ref="editor" v-model="fields" />
      <div class="fields-error" role="alert">{{ fieldsError }}</div>

      <div class="field note-field">
        <label for="f-note">备注</label>
        <textarea id="f-note" v-model="note" rows="3" placeholder="来源、用途、轮转时间等补充说明"></textarea>
      </div>

      <div class="form-actions">
        <div class="save-hint">保存后立即写入本地密钥库</div>
        <div class="right">
          <router-link class="btn btn-ghost" :to="{ name: 'secrets' }">取消</router-link>
          <button type="submit" class="btn btn-primary" :disabled="saving">
            {{ saving ? (isNew ? "创建中…" : "保存中…") : (isNew ? "创建记录" : "保存全部字段") }}
          </button>
        </div>
      </div>
    </form>
  </div>
</template>

<style scoped>
.form-card { max-width: 880px; padding: var(--s6); }
.identity-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(180px, .6fr); gap: var(--s4); }
.note-field { margin-top: var(--s6); }
.fields-error {
  min-height: 0;
  margin-top: calc(-1 * var(--s1));
  color: var(--danger);
  font-size: var(--text-sm);
}
.fields-error:empty { display: none; }
.save-hint { color: var(--ink-3); font-size: var(--text-xs); }

@media (max-width: 640px) {
  .form-card { padding: var(--s4); }
  .identity-grid { grid-template-columns: 1fr; gap: 0; }
  .form-actions { align-items: flex-end; gap: var(--s3); }
  .save-hint { max-width: 120px; }
}
</style>
