<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client.js";
import { formatDate, statusMeta, deadlineState } from "@/utils/format.js";
import AppLoader from "@/components/AppLoader.vue";

const router = useRouter();

const loading = ref(true);
const loadError = ref("");
const stats = ref(null);
const highPriority = ref([]);
const upcoming = ref([]);
const overdue = ref([]);

const STATUS_ORDER = { in_progress: 0, blocked: 1, waiting: 2, pending: 3 };

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    const [s, allRes] = await Promise.all([
      api.stats(),
      api.listTasks({ include_archived: "true" }),
    ]);
    stats.value = s;
    const tasks = allRes.tasks || [];

    const now = Date.now();
    const in7 = new Date();
    in7.setHours(0, 0, 0, 0);
    in7.setDate(in7.getDate() + 7);

    const up = [];
    const od = [];
    for (const t of tasks) {
      if (t.archived || t.status === "archived" || !t.deadline) continue;
      const d = new Date(t.deadline);
      if (isNaN(d.getTime())) continue;
      if (d.getTime() < now) od.push(t);
      else if (d.getTime() <= in7.getTime()) up.push(t);
    }
    up.sort((a, b) => new Date(a.deadline) - new Date(b.deadline));
    od.sort((a, b) => new Date(a.deadline) - new Date(b.deadline));
    upcoming.value = up;
    overdue.value = od;

    highPriority.value = tasks
      .filter((t) => t.priority === "high" && !t.archived && t.status !== "archived")
      .sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9));
  } catch (e) {
    if (e.code === "unauthorized") return;
    loadError.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

function openTask(t) {
  router.push({ name: "task-edit", params: { id: t.id } });
}

function deadlineCls(t) {
  const ds = deadlineState(t.deadline);
  return ds === "overdue" ? "overdue" : ds === "soon" ? "soon" : "";
}

onMounted(load);
</script>

<template>
  <div class="view-root">
    <div class="page-header">
      <div>
        <h1>统计</h1>
        <div class="subtitle">聚合任务状态、高优先级与时间风险</div>
      </div>
    </div>

    <AppLoader v-if="loading" label="计算运行数据" />

    <div v-else-if="loadError" class="error-page">
      <h2>加载失败</h2>
      <p>{{ loadError }}</p>
      <button class="btn" type="button" @click="load">重试</button>
    </div>

    <template v-else-if="stats">
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">总任务</div>
        </div>
        <div class="stat-card">
          <div class="stat-value accent-blue">{{ stats.by_status?.in_progress || 0 }}</div>
          <div class="stat-label">进行中</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.by_status?.pending || 0 }}</div>
          <div class="stat-label">待办</div>
        </div>
        <div class="stat-card">
          <div class="stat-value accent-danger">{{ stats.by_status?.blocked || 0 }}</div>
          <div class="stat-label">阻塞</div>
        </div>
        <div class="stat-card">
          <div class="stat-value accent-warning">{{ stats.by_status?.waiting || 0 }}</div>
          <div class="stat-label">等待</div>
        </div>
        <div class="stat-card">
          <div class="stat-value muted-val">{{ stats.by_status?.archived || 0 }}</div>
          <div class="stat-label">已归档</div>
        </div>
      </div>

      <div class="stats-sections">
        <section class="card section-card">
          <div class="section-head">
            <h3>高优先级</h3>
            <span class="muted text-sm">{{ highPriority.length }} 个</span>
          </div>
          <div v-if="highPriority.length" class="task-list">
            <button
              v-for="t in highPriority"
              :key="t.id"
              type="button"
              class="task-row"
              @click="openTask(t)"
            >
              <span class="tr-name">
                <span class="tr-title">{{ t.name }}</span>
                <span class="task-id">{{ t.id }}</span>
              </span>
              <span class="tr-meta">
                <span class="badge" :class="`status-${t.status}`"><span class="dot"></span>{{ statusMeta(t.status).label }}</span>
                <span class="deadline" :class="deadlineCls(t)">{{ t.deadline ? formatDate(t.deadline) : "—" }}</span>
              </span>
            </button>
          </div>
          <div v-else class="section-empty">没有高优先级任务</div>
        </section>

        <section class="card section-card">
          <div class="section-head">
            <h3>即将到期 · ≤7 天</h3>
            <span class="muted text-sm">{{ upcoming.length }} 个</span>
          </div>
          <div v-if="upcoming.length" class="task-list">
            <button
              v-for="t in upcoming"
              :key="t.id"
              type="button"
              class="task-row"
              @click="openTask(t)"
            >
              <span class="tr-name">
                <span class="tr-title">{{ t.name }}</span>
                <span class="task-id">{{ t.id }}</span>
              </span>
              <span class="tr-meta">
                <span class="deadline soon">{{ formatDate(t.deadline) }}</span>
              </span>
            </button>
          </div>
          <div v-else class="section-empty">未来 7 天无任务到期</div>
        </section>

        <section class="card section-card">
          <div class="section-head">
            <h3>已过期</h3>
            <span class="muted text-sm">{{ overdue.length }} 个</span>
          </div>
          <div v-if="overdue.length" class="task-list">
            <button
              v-for="t in overdue"
              :key="t.id"
              type="button"
              class="task-row"
              @click="openTask(t)"
            >
              <span class="tr-name">
                <span class="tr-title">{{ t.name }}</span>
                <span class="task-id">{{ t.id }}</span>
              </span>
              <span class="tr-meta">
                <span class="deadline overdue">{{ formatDate(t.deadline) }}</span>
              </span>
            </button>
          </div>
          <div v-else class="section-empty">无过期任务 🎉</div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: var(--s3);
  margin-bottom: var(--s6);
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  padding: var(--s4);
}
.stat-value {
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--ink);
  line-height: 1.1;
}
.stat-value.accent-blue { color: var(--info); }
.stat-value.accent-danger { color: var(--danger); }
.stat-value.accent-warning { color: var(--warning); }
.stat-value.muted-val { color: var(--ink-4); }
.stat-label {
  margin-top: 2px;
  font-size: var(--text-xs);
  color: var(--ink-3);
}

.stats-sections {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--s4);
  align-items: start;
}
.section-card { padding: var(--s4); }
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: var(--s3);
}
.section-head h3 { font-size: var(--text-md); }

.task-list {
  display: flex;
  flex-direction: column;
}
.task-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s3);
  padding: var(--s2) var(--s2);
  text-align: left;
  border-radius: var(--r-md);
  transition: background var(--t-fast);
  width: 100%;
}
.task-row:hover { background: var(--bg-subtle); }
.tr-name {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.tr-title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tr-meta {
  display: flex;
  align-items: center;
  gap: var(--s2);
  flex: none;
}

.section-empty {
  padding: var(--s6) var(--s2);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--ink-4);
}

@media (max-width: 1080px) {
  .stats-grid { grid-template-columns: repeat(3, 1fr); }
  .stats-sections { grid-template-columns: 1fr; }
}
@media (max-width: 560px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
