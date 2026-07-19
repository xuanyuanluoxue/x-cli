<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/api/client.js";
import {
  formatDate, statusMeta, priorityMeta, deadlineState,
} from "@/utils/format.js";
import { debounce } from "@/utils/dom.js";
import { toast, confirmDialog } from "@/utils/ui.js";
import AppLoader from "@/components/AppLoader.vue";

const route = useRoute();
const router = useRouter();

const STATUS_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "pending", label: "待办" },
  { value: "in_progress", label: "进行中" },
  { value: "blocked", label: "阻塞" },
  { value: "waiting", label: "等待" },
];
const PRIORITY_OPTIONS = [
  { value: "", label: "全部优先级" },
  { value: "high", label: "高" },
  { value: "medium", label: "中" },
  { value: "low", label: "低" },
];

const tasks = ref([]);
const loading = ref(true);
const loadError = ref("");

const q = ref(String(route.query.q || ""));
const status = ref(String(route.query.status || ""));
const priority = ref(String(route.query.priority || ""));
const showArchived = ref(route.query.archived === "1");

// 过滤条件 → hash query（replace，不堆积历史）
watch([q, status, priority, showArchived], () => {
  const query = {};
  if (q.value) query.q = q.value;
  if (status.value) query.status = status.value;
  if (priority.value) query.priority = priority.value;
  if (showArchived.value) query.archived = "1";
  router.replace({ name: "tasks", query });
});

const reloadDebounced = debounce(load, 150);
watch(q, () => reloadDebounced());
watch([status, priority, showArchived], () => load());

const visible = computed(() => {
  if (!q.value) return tasks.value;
  const needle = q.value.toLowerCase();
  return tasks.value.filter((t) =>
    (t.name || "").toLowerCase().includes(needle) ||
    (t.id || "").toLowerCase().includes(needle) ||
    (Array.isArray(t.tags) && t.tags.some((tag) => (tag || "").toLowerCase().includes(needle))),
  );
});

const summary = computed(() => {
  if (loading.value) return "加载中…";
  const total = tasks.value.length;
  const shown = visible.value.length;
  return shown === total
    ? `共 ${total} 个任务${showArchived.value ? "（含已归档）" : ""}`
    : `显示 ${shown} / ${total} 个任务`;
});

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    const params = {};
    if (status.value) params.status = status.value;
    if (priority.value) params.priority = priority.value;
    if (showArchived.value) params.include_archived = "true";
    const { tasks: list } = await api.listTasks(params);
    tasks.value = list || [];
  } catch (e) {
    if (e.code === "unauthorized") return;
    loadError.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

function resetFilters() {
  q.value = "";
  status.value = "";
  priority.value = "";
  showArchived.value = false;
}

function openTask(t) {
  router.push({ name: "task-edit", params: { id: t.id } });
}

async function archive(t) {
  const ok = await confirmDialog({
    title: "归档任务",
    body: `确认归档任务「${t.name}」？归档后可在「显示已归档」开关下查看。`,
    confirmText: "确认归档",
    danger: true,
  });
  if (!ok) return;
  try {
    await api.archiveTask(t.id, "done");
    toast("已归档", "success");
    await load();
  } catch (err) {
    if (err.code === "duplicate") toast("任务已归档", "warning");
    else toast("归档失败：" + err.message, "error");
  }
}

function isArchived(t) {
  return t.archived || t.status === "archived";
}
function deadlineCls(t) {
  const ds = deadlineState(t.deadline);
  return ds === "overdue" ? "overdue" : ds === "soon" ? "soon" : "";
}

// 标签展示：默认最多 3 个，窗口变窄时只保留 1 个，超出的折叠为 +N
const TAG_LIMIT_WIDE = 3;
const TAG_LIMIT_NARROW = 1;
const narrow = ref(window.innerWidth < 900);
const tagLimit = computed(() => (narrow.value ? TAG_LIMIT_NARROW : TAG_LIMIT_WIDE));

function updateNarrow() {
  narrow.value = window.innerWidth < 900;
}

function visibleTags(t) {
  return Array.isArray(t.tags) ? t.tags.slice(0, tagLimit.value) : [];
}
function hiddenTagCount(t) {
  const n = Array.isArray(t.tags) ? t.tags.length : 0;
  return Math.max(0, n - tagLimit.value);
}
function tagsTitle(t) {
  return Array.isArray(t.tags) && t.tags.length ? `标签：${t.tags.join("、")}` : "";
}

onMounted(() => {
  window.addEventListener("resize", updateNarrow);
  load();
});
onUnmounted(() => window.removeEventListener("resize", updateNarrow));
</script>

<template>
  <div class="view-root">
    <div class="page-header">
      <div>
        <h1>任务</h1>
        <div class="subtitle">{{ summary }}</div>
      </div>
      <div class="actions">
        <router-link class="btn btn-primary" :to="{ name: 'task-new' }">新建任务</router-link>
      </div>
    </div>

    <div class="toolbar">
      <div class="toolbar-group search-field">
        <input v-model="q" type="text" placeholder="搜索任务名 / 标签…" autocomplete="off" aria-label="搜索任务">
      </div>
      <div class="toolbar-group">
        <select v-model="status" aria-label="按状态过滤">
          <option v-for="o in STATUS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <select v-model="priority" aria-label="按优先级过滤">
          <option v-for="o in PRIORITY_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <label class="switch">
          <input v-model="showArchived" type="checkbox">
          <span>显示已归档</span>
        </label>
      </div>
      <div class="toolbar-spacer"></div>
      <div class="toolbar-group">
        <button class="btn btn-ghost btn-sm" type="button" title="清空所有过滤条件" @click="resetFilters">重置</button>
      </div>
    </div>

    <AppLoader v-if="loading" label="读取任务库" />

    <div v-else-if="loadError" class="error-page">
      <h2>加载失败</h2>
      <p>{{ loadError }}</p>
      <button class="btn" type="button" @click="load">重试</button>
    </div>

    <div v-else-if="visible.length === 0" class="card">
      <div class="empty">
        <div class="empty-title">{{ tasks.length === 0 ? "没有任务" : "没有匹配项" }}</div>
        <div class="empty-hint">{{ tasks.length === 0 ? "建立第一个任务，开始编排你的工作流。" : "试试调整过滤条件。" }}</div>
      </div>
    </div>

    <div v-else class="table-wrap">
      <table class="data">
        <thead>
          <tr>
            <th>任务</th>
            <th>状态</th>
            <th>优先级</th>
            <th>截止</th>
            <th>标签</th>
            <th class="text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="t in visible"
            :key="t.id"
            class="clickable"
            :class="{ archived: isArchived(t) }"
            @click="openTask(t)"
          >
            <td data-label="任务">
              <span class="task-name-wrap">
                <span class="task-name">{{ t.name }}</span>
                <span class="task-id">{{ t.id }}</span>
              </span>
            </td>
            <td data-label="状态">
              <span class="badge" :class="`status-${t.status || 'pending'}`">
                <span class="dot"></span>{{ statusMeta(t.status).label }}
              </span>
            </td>
            <td data-label="优先级">
              <span class="badge" :class="`priority-${t.priority || 'low'}`">
                {{ priorityMeta(t.priority).icon }} {{ priorityMeta(t.priority).label }}
              </span>
            </td>
            <td data-label="截止">
              <span class="deadline" :class="deadlineCls(t)">{{ t.deadline ? formatDate(t.deadline) || "—" : "—" }}</span>
            </td>
            <td data-label="标签" :title="tagsTitle(t)">
              <template v-if="Array.isArray(t.tags) && t.tags.length">
                <span v-for="tag in visibleTags(t)" :key="tag" class="tag">{{ tag }}</span>
                <span v-if="hiddenTagCount(t)" class="tag tag-more">+{{ hiddenTagCount(t) }}</span>
              </template>
              <span v-else class="muted text-sm">—</span>
            </td>
            <td class="text-right" data-label="操作" @click.stop>
              <router-link class="btn btn-sm" :to="{ name: 'task-edit', params: { id: t.id } }">编辑</router-link>
              <button v-if="!isArchived(t)" class="btn btn-sm btn-danger" type="button" @click="archive(t)">归档</button>
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
