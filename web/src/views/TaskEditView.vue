<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "@/api/client.js";
import { formatDate, ARCHIVE_REASONS } from "@/utils/format.js";
import { toast, confirmDialog } from "@/utils/ui.js";
import AppLoader from "@/components/AppLoader.vue";

const route = useRoute();
const router = useRouter();

const isNew = computed(() => route.name === "task-new");
const taskId = computed(() => (isNew.value ? null : String(route.params.id)));

const loading = ref(!isNew.value);
const loadError = ref("");
const notFound = ref(false);
const task = ref(null);

// 表单字段
const name = ref("");
const status = ref("pending");
const priority = ref("medium");
const deadline = ref("");
const tagsStr = ref("");
const nameError = ref("");
const saving = ref(false);

const STATUS_OPTIONS = [
  { value: "pending", label: "待办" },
  { value: "in_progress", label: "进行中" },
  { value: "blocked", label: "阻塞" },
  { value: "waiting", label: "等待" },
  { value: "archived", label: "已归档" },
];
const PRIORITY_OPTIONS = [
  { value: "low", label: "低" },
  { value: "medium", label: "中" },
  { value: "high", label: "高" },
];

const isArchived = computed(() =>
  task.value && (task.value.archived || task.value.status === "archived"),
);

function parseTags() {
  const s = tagsStr.value.trim();
  return s ? s.split(",").map((x) => x.trim()).filter(Boolean) : [];
}

async function loadTask() {
  loading.value = true;
  try {
    const t = await api.getTask(taskId.value);
    task.value = t;
    name.value = t.name || "";
    status.value = t.status || "pending";
    priority.value = t.priority || "medium";
    deadline.value = formatDate(t.deadline) || "";
    tagsStr.value = Array.isArray(t.tags) ? t.tags.join(", ") : "";
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
  saving.value = true;
  try {
    if (isNew.value) {
      const n = name.value.trim();
      if (!n) {
        nameError.value = "任务名不能为空";
        saving.value = false;
        return;
      }
      const created = await api.createTask({
        name: n,
        priority: priority.value,
        deadline: deadline.value || null,
        tags: parseTags(),
      });
      toast(`已创建：${created.name}`, "success");
      router.replace({ name: "task-edit", params: { id: created.id } });
    } else {
      await api.updateTask(task.value.id, {
        status: status.value,
        priority: priority.value,
        deadline: deadline.value || null,
        tags: parseTags(),
      });
      toast("已保存", "success");
      router.push({ name: "tasks" });
    }
  } catch (err) {
    if (err.code === "duplicate") nameError.value = "同名任务已存在，请换个名字";
    else if (err.code === "validation_error") nameError.value = err.message;
    else toast((isNew.value ? "创建失败：" : "保存失败：") + err.message, "error");
  } finally {
    saving.value = false;
  }
}

async function archive() {
  const ok = await confirmDialog({
    title: "归档任务",
    body: `确认归档「${task.value.name}」？归档后任务从列表隐藏，需先 restore 才能再次编辑。`,
    confirmText: "确认归档",
    danger: true,
  });
  if (!ok) return;
  try {
    await api.archiveTask(task.value.id, "done");
    toast(`已归档：${task.value.name}`, "success");
    router.push({ name: "tasks" });
  } catch (err) {
    if (err.code === "duplicate") toast("任务已归档", "warning");
    else toast("归档失败：" + err.message, "error");
  }
}

onMounted(() => {
  if (!isNew.value) loadTask();
});
</script>

<template>
  <div class="view-root">
    <div class="page-header">
      <div>
        <h1>{{ isNew ? "新建任务" : "编辑任务" }}</h1>
        <div class="subtitle">{{ isNew ? "定义一个清晰、可跟踪的工作项" : "更新执行状态、优先级与时间边界" }}</div>
      </div>
    </div>

    <AppLoader v-if="loading" label="读取任务数据" />

    <div v-else-if="notFound" class="error-page">
      <h2>任务不存在</h2>
      <p>id = <code>{{ taskId }}</code> 在任务库里找不到。</p>
      <router-link class="btn" :to="{ name: 'tasks' }">返回列表</router-link>
    </div>

    <div v-else-if="loadError" class="error-page">
      <h2>加载失败</h2>
      <p>{{ loadError }}</p>
      <router-link class="btn" :to="{ name: 'tasks' }">返回列表</router-link>
    </div>

    <form v-else class="card form-card" autocomplete="off" @submit.prevent="submit">
      <!-- 新建：可填名；编辑：只读 -->
      <div v-if="isNew" class="field">
        <label for="f-name">任务名 <span class="required-mark">*</span></label>
        <input id="f-name" v-model="name" type="text" required maxlength="200" placeholder="例：科目一模拟考">
        <div class="help">支持中英文，1-200 字符</div>
        <div class="error" role="alert">{{ nameError }}</div>
      </div>
      <div v-else class="field">
        <label>任务名</label>
        <div class="readonly-name">
          <span>{{ task.name }}</span>
          <span class="task-id">{{ task.id }}</span>
        </div>
        <div class="help">name 创建后不可修改（如需改名请归档后新建）</div>
      </div>

      <div v-if="!isNew" class="field">
        <label for="f-status">状态</label>
        <select id="f-status" v-model="status" :disabled="isArchived">
          <option v-for="o in STATUS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <div v-if="isArchived" class="help">已归档任务不可改状态（先 restore）</div>
      </div>

      <div class="field">
        <label for="f-priority">优先级</label>
        <select id="f-priority" v-model="priority" :disabled="isArchived">
          <option v-for="o in PRIORITY_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>

      <div class="field">
        <label for="f-deadline">截止日期</label>
        <input id="f-deadline" v-model="deadline" type="date" :disabled="isArchived">
        <div class="help">{{ isNew ? "可选；YYYY-MM-DD" : "留空 = 清除" }}</div>
      </div>

      <div class="field">
        <label for="f-tags">标签</label>
        <input id="f-tags" v-model="tagsStr" type="text" placeholder="标签1, 标签2" :disabled="isArchived">
        <div class="help">{{ isNew ? "用英文逗号分隔，可选" : "英文逗号分隔；完全替换" }}</div>
      </div>

      <div class="form-actions">
        <div>
          <button
            v-if="!isNew && !isArchived"
            type="button"
            class="btn btn-danger"
            @click="archive"
          >归档</button>
          <span v-else-if="!isNew && isArchived" class="muted text-sm">已归档（{{ ARCHIVE_REASONS[task.reason] || task.reason || "done" }}）</span>
        </div>
        <div class="right">
          <router-link class="btn btn-ghost" :to="{ name: 'tasks' }">取消</router-link>
          <button type="submit" class="btn btn-primary" :disabled="saving || isArchived">
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
