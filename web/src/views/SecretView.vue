<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/api/client.js";
import { formatTimestamp } from "@/utils/format.js";
import { copyToClipboard } from "@/utils/dom.js";
import { confirmDialog, toast } from "@/utils/ui.js";
import { confirmSecretAccess } from "@/utils/secret-confirmation.js";
import AppLoader from "@/components/AppLoader.vue";

const route = useRoute();
const router = useRouter();
const name = String(route.params.name);

const stage = ref("confirm");
const loadError = ref("");
const secret = ref(null);
const revealed = ref({});

const fields = computed(() => {
  if (Array.isArray(secret.value?.fields) && secret.value.fields.length) {
    return secret.value.fields;
  }
  return secret.value
    ? [{ label: "密钥", kind: "secret", value: secret.value.value || "", primary: true }]
    : [];
});

onMounted(async () => {
  const confirmed = await confirmSecretAccess({
    title: "你正在查看密钥库参数",
    body:
      "页面将读取这条记录的全部字段，包括密钥明文。内容可能被屏幕录制或浏览器调试工具捕获。\n\n" +
      "请确认你处于安全环境，离开后关闭页面。",
    confirmText: "我已了解，继续查看",
    cancelText: "取消",
  });
  if (!confirmed) {
    router.replace({ name: "secrets" });
    return;
  }

  stage.value = "loading";
  try {
    secret.value = await api.getSecret(name);
    stage.value = "ready";
  } catch (error) {
    if (error.code === "unauthorized") return;
    if (error.code === "not_found") stage.value = "not_found";
    else {
      loadError.value = error.message || "加载失败";
      stage.value = "error";
    }
  }
});

function toggleField(index) {
  revealed.value = { ...revealed.value, [index]: !revealed.value[index] };
}

async function copyField(field) {
  const copied = await copyToClipboard(field.value || "");
  toast(
    copied ? `已复制字段「${field.label}」` : "复制失败，请手动复制",
    copied ? "success" : "error",
  );
}

function safeUrl(value) {
  const candidate = String(value || "").trim();
  if (!/^https?:\/\/[^\s]+$/i.test(candidate)) return "";
  try {
    const parsed = new URL(candidate);
    return ["http:", "https:"].includes(parsed.protocol) ? candidate : "";
  } catch {
    return "";
  }
}

async function remove() {
  const confirmed = await confirmDialog({
    title: "删除密钥",
    body: `确定要删除「${secret.value.name}」吗？此操作不可撤销。`,
    confirmText: "确认删除",
    danger: true,
  });
  if (!confirmed) return;
  try {
    await api.deleteSecret(secret.value.name);
    toast("已删除", "success");
    router.push({ name: "secrets" });
  } catch (error) {
    toast("删除失败：" + error.message, "error");
  }
}
</script>

<template>
  <div class="view-root">
    <div class="page-header">
      <div>
        <h1>查看密钥</h1>
        <div class="subtitle">每个参数独立显示与复制，明文只在当前页面短暂存在</div>
      </div>
    </div>

    <div v-if="stage === 'confirm'" class="card">
      <div class="empty">
        <div class="empty-title">等待安全确认</div>
        <div class="empty-hint">确认后才向本地 API 请求全部字段值</div>
      </div>
    </div>

    <AppLoader v-else-if="stage === 'loading'" label="读取密钥字段" />

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
        <div>
          <div class="eyebrow">CREDENTIAL RECORD</div>
          <h2>{{ secret.name }}</h2>
        </div>
        <span class="category-badge">{{ secret.category || "default" }}</span>
      </div>

      <div v-if="secret.note" class="note-block">{{ secret.note }}</div>

      <section class="parameter-section" aria-labelledby="parameter-title">
        <div class="parameter-heading">
          <div>
            <h3 id="parameter-title">密钥库参数</h3>
            <p>{{ fields.length }} 个字段 · 密钥信息默认隐藏</p>
          </div>
        </div>

        <div class="parameter-list">
          <article
            v-for="(field, index) in fields"
            :key="`${field.label}-${index}`"
            class="parameter-row"
            :class="{ 'is-primary': field.primary }"
          >
            <div class="parameter-meta">
              <div class="parameter-label">{{ field.label }}</div>
              <div class="parameter-badges">
                <span class="kind-badge" :class="`is-${field.kind}`">
                  {{ field.kind === "secret" ? "密钥信息" : "普通文本" }}
                </span>
                <span v-if="field.primary" class="primary-badge">◆ 主密钥</span>
              </div>
            </div>

            <div class="parameter-value">
              <a
                v-if="field.kind === 'text' && safeUrl(field.value)"
                class="url-value mono"
                :href="safeUrl(field.value)"
                target="_blank"
                rel="noopener noreferrer"
              >{{ field.value }}</a>
              <pre
                v-else
                class="value-surface"
                :class="{ mono: field.kind === 'secret' }"
              >{{ field.kind === "secret" && !revealed[index] ? "••••••••••••" : field.value }}</pre>

              <div class="parameter-actions">
                <button
                  v-if="field.kind === 'secret'"
                  type="button"
                  class="btn btn-sm"
                  :aria-pressed="Boolean(revealed[index])"
                  :aria-label="revealed[index] ? `隐藏字段 ${field.label}` : `显示字段 ${field.label}`"
                  @click="toggleField(index)"
                >{{ revealed[index] ? "HIDE" : "SHOW" }}</button>
                <button
                  type="button"
                  class="btn btn-sm"
                  :aria-label="`复制字段 ${field.label}`"
                  @click="copyField(field)"
                >COPY</button>
              </div>
            </div>
          </article>
        </div>
      </section>

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
          <router-link
            class="btn btn-primary"
            :to="{ name: 'secret-edit', params: { name: secret.name } }"
          >编辑字段</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-card { max-width: 800px; padding: var(--s6); }
.secret-head { display: flex; align-items: flex-end; gap: var(--s3); margin-bottom: var(--s4); }
.secret-head h2 { margin: 2px 0 0; font-size: var(--text-xl); letter-spacing: -.01em; }
.eyebrow {
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
}
.category-badge { margin-bottom: 2px; }
.note-block {
  padding: var(--s3) var(--s4);
  margin-bottom: var(--s5);
  color: var(--ink-2);
  background: var(--bg-subtle);
  border-radius: var(--r-md);
  font-size: var(--text-sm);
  white-space: pre-line;
}

.parameter-section { margin: var(--s5) 0 var(--s6); }
.parameter-heading { display: flex; justify-content: space-between; margin-bottom: var(--s3); }
.parameter-heading h3 { margin: 0; font-size: var(--text-lg); }
.parameter-heading p { margin: 3px 0 0; color: var(--ink-3); font-size: var(--text-xs); }
.parameter-list { overflow: hidden; border: 1px solid var(--line); border-radius: var(--r-lg); }
.parameter-row {
  position: relative;
  display: grid;
  grid-template-columns: minmax(130px, .45fr) minmax(260px, 1.55fr);
  gap: var(--s4);
  padding: var(--s4);
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}
.parameter-row:last-child { border-bottom: 0; }
.parameter-row.is-primary { background: var(--accent-soft); }
.parameter-row.is-primary::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  content: "";
  background: var(--accent);
}
.parameter-meta { min-width: 0; }
.parameter-label { margin-bottom: var(--s2); overflow-wrap: anywhere; font-weight: 700; }
.parameter-badges { display: flex; flex-wrap: wrap; gap: var(--s1); }
.kind-badge,
.primary-badge {
  padding: 2px 7px;
  border-radius: var(--r-pill);
  font-size: 10.5px;
  font-weight: 600;
}
.kind-badge.is-text { color: var(--info); background: var(--info-soft); }
.kind-badge.is-secret { color: var(--warning); background: var(--warning-soft); }
.primary-badge { color: var(--accent); background: var(--accent-soft); border: 1px solid #ccd9ce; }

.parameter-value { min-width: 0; }
.value-surface,
.url-value {
  display: block;
  min-height: 38px;
  margin: 0;
  padding: 9px 86px 9px var(--s3);
  overflow: auto;
  color: var(--ink);
  background: var(--bg-subtle);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-md);
  font-size: var(--text-base);
  line-height: 1.45;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.url-value { color: var(--info); text-decoration: underline; text-underline-offset: 2px; }
.parameter-value { position: relative; }
.parameter-actions {
  position: absolute;
  top: 5px;
  right: 5px;
  display: flex;
  gap: 4px;
}
.parameter-actions .btn { background: var(--surface); }

.meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--s2) var(--s5);
  margin: 0 0 var(--s2);
  padding: var(--s4) 0;
  border-top: 1px solid var(--line);
}
.meta-row { display: grid; grid-template-columns: 58px 1fr; gap: var(--s2); font-size: var(--text-sm); }
.meta dt { color: var(--ink-3); }
.meta dd { margin: 0; color: var(--ink-2); }

@media (max-width: 640px) {
  .detail-card { padding: var(--s4); }
  .parameter-row { grid-template-columns: 1fr; gap: var(--s3); }
  .parameter-label { margin-bottom: var(--s1); }
  .meta { grid-template-columns: 1fr; }
}
</style>
