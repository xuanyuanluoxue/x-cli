<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  modelValue: {
    type: Array,
    required: true,
  },
});

const emit = defineEmits(["update:modelValue"]);
const revealed = ref({});

const primaryCount = computed(() => props.modelValue.filter((field) => field.primary).length);

function replaceFields(next) {
  emit("update:modelValue", next.map((field) => ({ ...field })));
}

function patchField(index, patch) {
  replaceFields(props.modelValue.map((field, i) => (
    i === index ? { ...field, ...patch } : field
  )));
}

function addField() {
  replaceFields([
    ...props.modelValue,
    { label: "", kind: "text", value: "", primary: false },
  ]);
}

function removeField(index) {
  if (props.modelValue[index]?.primary) return;
  replaceFields(props.modelValue.filter((_field, i) => i !== index));
}

function moveField(index, direction) {
  const target = index + direction;
  if (target < 0 || target >= props.modelValue.length) return;
  const next = props.modelValue.map((field) => ({ ...field }));
  [next[index], next[target]] = [next[target], next[index]];
  replaceFields(next);
}

function makePrimary(index) {
  if (props.modelValue[index]?.kind !== "secret") return;
  replaceFields(props.modelValue.map((field, i) => ({
    ...field,
    primary: i === index,
  })));
}

function toggleReveal(index) {
  revealed.value = { ...revealed.value, [index]: !revealed.value[index] };
}

function fieldIssue(index) {
  const field = props.modelValue[index];
  if (!field.label?.trim()) return "请填写字段名称";
  if (field.label.trim().length > 64) return "字段名称不能超过 64 个字符";
  const duplicate = props.modelValue.some((candidate, i) => (
    i !== index
    && candidate.label?.trim().toLocaleLowerCase() === field.label.trim().toLocaleLowerCase()
  ));
  if (duplicate) return "字段名称不能重复";
  if (!field.value) return "请填写字段值";
  if (field.primary && field.kind !== "secret") return "主密钥必须是密钥信息";
  return "";
}

function validate() {
  if (!props.modelValue.length) return "至少添加一个字段";
  if (props.modelValue.length > 50) return "一条记录最多 50 个字段";
  for (let i = 0; i < props.modelValue.length; i += 1) {
    const issue = fieldIssue(i);
    if (issue) return `字段 ${i + 1}：${issue}`;
  }
  if (primaryCount.value !== 1) return "必须设置且只能设置一个主密钥";
  return "";
}

defineExpose({ validate });
</script>

<template>
  <section class="fields-editor" aria-labelledby="secret-fields-title">
    <div class="fields-heading">
      <div>
        <div class="eyebrow">CREDENTIAL FIELDS</div>
        <h2 id="secret-fields-title">密钥库参数</h2>
        <p>普通文本直接显示；密钥信息默认隐藏。带钥匙标记的字段是 CLI 默认取值。</p>
      </div>
      <span class="field-count">{{ modelValue.length }} / 50</span>
    </div>

    <div class="fields-list">
      <article
        v-for="(field, index) in modelValue"
        :key="index"
        class="field-card"
        :class="{ 'is-primary': field.primary }"
      >
        <div class="field-card-head">
          <div class="field-number">{{ String(index + 1).padStart(2, "0") }}</div>
          <div class="field-badges">
            <span class="type-badge" :class="`is-${field.kind}`">
              {{ field.kind === "secret" ? "密钥信息" : "普通文本" }}
            </span>
            <span v-if="field.primary" class="primary-badge">◆ 主密钥</span>
          </div>
          <div class="field-card-actions" aria-label="字段排序与删除">
            <button
              type="button"
              class="icon-btn"
              :disabled="index === 0"
              :aria-label="`上移字段 ${index + 1}`"
              @click="moveField(index, -1)"
            >↑</button>
            <button
              type="button"
              class="icon-btn"
              :disabled="index === modelValue.length - 1"
              :aria-label="`下移字段 ${index + 1}`"
              @click="moveField(index, 1)"
            >↓</button>
            <button
              type="button"
              class="icon-btn remove-btn"
              :disabled="field.primary"
              :title="field.primary ? '请先设置另一个主密钥' : '删除字段'"
              :aria-label="`删除字段 ${index + 1}`"
              @click="removeField(index)"
            >×</button>
          </div>
        </div>

        <div class="field-grid">
          <div class="mini-field label-field">
            <label :for="`secret-field-label-${index}`">字段名称</label>
            <input
              :id="`secret-field-label-${index}`"
              :value="field.label"
              type="text"
              maxlength="64"
              placeholder="如 URL / 账号 / 密码"
              @input="patchField(index, { label: $event.target.value })"
            >
          </div>

          <div class="mini-field type-field">
            <label :for="`secret-field-kind-${index}`">显示类型</label>
            <select
              :id="`secret-field-kind-${index}`"
              :value="field.kind"
              :disabled="field.primary"
              @change="patchField(index, { kind: $event.target.value })"
            >
              <option value="text">普通文本</option>
              <option value="secret">密钥信息</option>
            </select>
          </div>

          <div class="mini-field value-field">
            <label :for="`secret-field-value-${index}`">字段值</label>
            <div class="value-editor">
              <textarea
                :id="`secret-field-value-${index}`"
                :value="field.value"
                rows="2"
                spellcheck="false"
                :class="{
                  mono: field.kind === 'secret',
                  masked: field.kind === 'secret' && !revealed[index],
                }"
                :aria-label="`${field.label || `字段 ${index + 1}`}的值`"
                placeholder="输入字段内容"
                @input="patchField(index, { value: $event.target.value })"
              ></textarea>
              <button
                v-if="field.kind === 'secret'"
                type="button"
                class="btn btn-sm reveal-btn"
                :aria-pressed="Boolean(revealed[index])"
                @click="toggleReveal(index)"
              >{{ revealed[index] ? "HIDE" : "SHOW" }}</button>
            </div>
          </div>
        </div>

        <div class="field-card-foot">
          <div class="inline-error" role="alert">{{ fieldIssue(index) }}</div>
          <button
            v-if="field.kind === 'secret' && !field.primary"
            type="button"
            class="primary-action"
            @click="makePrimary(index)"
          >设为主密钥</button>
          <span v-else-if="field.primary" class="primary-help">CLI 默认复制此字段</span>
        </div>
      </article>
    </div>

    <button
      type="button"
      class="add-field-btn"
      :disabled="modelValue.length >= 50"
      @click="addField"
    >
      <span aria-hidden="true">＋</span>
      添加字段
    </button>

    <div class="plaintext-note">
      <span aria-hidden="true">!</span>
      “密钥信息”仅控制页面是否掩码；所有内容仍以明文保存在本地 JSON。
    </div>
  </section>
</template>

<style scoped>
.fields-editor {
  margin: var(--s6) 0;
  padding-top: var(--s5);
  border-top: 1px solid var(--line);
}

.fields-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s4);
  margin-bottom: var(--s4);
}
.fields-heading h2 { margin: 2px 0 var(--s1); font-size: var(--text-lg); }
.fields-heading p { margin: 0; color: var(--ink-3); font-size: var(--text-sm); }
.eyebrow {
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
}
.field-count {
  flex: none;
  padding: 4px 8px;
  color: var(--ink-3);
  background: var(--bg-subtle);
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.fields-list { display: grid; gap: var(--s3); }
.field-card {
  position: relative;
  padding: var(--s4);
  overflow: hidden;
  background: var(--bg-subtle);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  transition: border-color var(--t-fast), background var(--t-fast);
}
.field-card::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  content: "";
  background: transparent;
}
.field-card.is-primary { background: var(--accent-soft); border-color: #ccd9ce; }
.field-card.is-primary::before { background: var(--accent); }
.field-card-head { display: flex; align-items: center; gap: var(--s3); margin-bottom: var(--s3); }
.field-number {
  color: var(--ink-4);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 700;
}
.field-badges { display: flex; align-items: center; gap: var(--s2); }
.type-badge,
.primary-badge {
  padding: 2px 7px;
  border-radius: var(--r-pill);
  font-size: 10.5px;
  font-weight: 600;
}
.type-badge.is-text { color: var(--info); background: var(--info-soft); }
.type-badge.is-secret { color: var(--warning); background: var(--warning-soft); }
.primary-badge { color: var(--accent); background: var(--surface); border: 1px solid #ccd9ce; }
.field-card-actions { display: flex; gap: 3px; margin-left: auto; }
.icon-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--ink-2);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  cursor: pointer;
}
.icon-btn:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.icon-btn:disabled { color: var(--ink-4); cursor: not-allowed; opacity: .55; }
.remove-btn:hover:not(:disabled) { color: var(--danger); border-color: var(--danger); }

.field-grid { display: grid; grid-template-columns: minmax(150px, .8fr) 130px minmax(240px, 1.6fr); gap: var(--s3); }
.mini-field label {
  display: block;
  margin-bottom: 5px;
  color: var(--ink-3);
  font-size: var(--text-xs);
  font-weight: 600;
}
.mini-field input,
.mini-field select,
.mini-field textarea {
  width: 100%;
  color: var(--ink);
  background: var(--surface);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-md);
}
.mini-field input,
.mini-field select { height: 36px; padding: 0 var(--s3); }
.mini-field textarea { min-height: 62px; padding: var(--s2) 72px var(--s2) var(--s3); resize: vertical; line-height: 1.45; }
.mini-field input:focus,
.mini-field select:focus,
.mini-field textarea:focus { outline: none; border-color: var(--accent); }
.mini-field select:disabled { color: var(--ink-3); background: #efefec; }
.value-editor { position: relative; }
.masked { -webkit-text-security: disc; }
.reveal-btn { position: absolute; top: 7px; right: 7px; background: var(--surface); }

.field-card-foot { display: flex; align-items: center; gap: var(--s3); min-height: 24px; margin-top: var(--s2); }
.inline-error { color: var(--danger); font-size: var(--text-xs); }
.primary-action {
  margin-left: auto;
  padding: 0;
  color: var(--accent);
  background: transparent;
  border: 0;
  font-size: var(--text-xs);
  font-weight: 650;
  cursor: pointer;
}
.primary-action:hover { text-decoration: underline; }
.primary-help { margin-left: auto; color: var(--accent); font-size: var(--text-xs); }

.add-field-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s2);
  width: 100%;
  min-height: 42px;
  margin-top: var(--s3);
  color: var(--accent);
  background: transparent;
  border: 1px dashed #afc3b2;
  border-radius: var(--r-md);
  font-weight: 650;
  cursor: pointer;
  transition: background var(--t-fast), border-color var(--t-fast);
}
.add-field-btn:hover { background: var(--accent-soft); border-color: var(--accent); }
.add-field-btn:disabled { color: var(--ink-4); border-color: var(--line); cursor: not-allowed; }
.add-field-btn span { font-size: 18px; line-height: 1; }
.plaintext-note {
  display: flex;
  gap: var(--s2);
  margin-top: var(--s3);
  color: var(--ink-3);
  font-size: var(--text-xs);
}
.plaintext-note span {
  display: inline-grid;
  flex: none;
  place-items: center;
  width: 16px;
  height: 16px;
  color: var(--warning);
  border: 1px solid #d6c49d;
  border-radius: 50%;
  font-family: var(--font-mono);
  font-weight: 700;
}

@media (max-width: 760px) {
  .field-grid { grid-template-columns: 1fr 120px; }
  .value-field { grid-column: 1 / -1; }
}

@media (max-width: 520px) {
  .fields-heading { align-items: center; }
  .fields-heading p { display: none; }
  .field-card { padding: var(--s3); }
  .field-card-head { flex-wrap: wrap; }
  .field-card-actions { width: 100%; margin-left: 0; }
  .field-grid { grid-template-columns: 1fr; }
  .value-field { grid-column: auto; }
}
</style>
