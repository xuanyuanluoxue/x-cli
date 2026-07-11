// views/task-edit.js — 单个任务编辑 / 新建
//
// 参数：
//   "new"   → 新建模式
//   <id>    → 编辑模式（GET /api/tasks/:id）
//
// 操作：
//   保存 (PATCH /api/tasks/:id 或 POST /api/tasks)
//   归档 (POST /api/tasks/:id/archive, with confirm)
//   取消 (返回列表)

import { api, ApiError } from "../api.js";
import {
  escapeHtml, formatDate, toast, confirmModal, openModal,
  ARCHIVE_REASONS, navigate,
} from "../utils.js";

const STATUS_OPTIONS = ["pending", "in_progress", "blocked", "waiting", "archived"];
const PRIORITY_OPTIONS = ["low", "medium", "high"];

export function render(idOrNew) {
  const isNew = !idOrNew || idOrNew === "new";
  const root = document.createElement("div");

  if (isNew) {
    root.innerHTML = renderNewForm();
  } else {
    root.innerHTML = renderLoading();
  }

  // 异步：编辑模式加载任务
  if (!isNew) {
    api.getTask(idOrNew)
      .then((task) => {
        const main = document.querySelector(".task-edit-card");
        if (!main) return;
        main.outerHTML = renderEditForm(task);
        bindEditForm(task);
      })
      .catch((e) => {
        const main = document.querySelector("#main");
        if (e.code === "not_found") {
          main.innerHTML = `
            <div class="error-page">
              <div class="error-icon">🔍</div>
              <h2>任务不存在</h2>
              <p>id = <code>${escapeHtml(idOrNew)}</code> 在任务库里找不到。</p>
              <a class="btn" href="#tasks">返回列表</a>
            </div>
          `;
        } else {
          main.innerHTML = `
            <div class="error-page">
              <div class="error-icon">💥</div>
              <h2>加载失败</h2>
              <p>${escapeHtml(e.message)}</p>
              <a class="btn" href="#tasks">返回列表</a>
            </div>
          `;
        }
      });
  } else {
    // 新建模式：DOMContentLoaded 后绑定
    queueMicrotask(() => bindNewForm());
  }

  return Promise.resolve(root);
}

// ---- 模板 ----

function renderLoading() {
  return `
    <div class="task-edit-card card">
      <div class="empty"><div class="empty-icon">⏳</div><div class="empty-title">加载任务中…</div></div>
    </div>
  `;
}

function renderNewForm() {
  return `
    <div class="page-header">
      <div>
        <h1>➕ 新建任务</h1>
        <div class="subtitle">创建一个新任务</div>
      </div>
    </div>
    <form class="task-edit-card card" id="new-task-form" autocomplete="off">
      <div class="field">
        <label for="f-name">任务名 <span style="color:var(--danger)">*</span></label>
        <input id="f-name" type="text" required maxlength="200" placeholder="例：科目一模拟考">
        <div class="help">支持中英文，1-200 字符</div>
        <div class="error" id="err-name"></div>
      </div>
      <div class="field">
        <label for="f-priority">优先级</label>
        <select id="f-priority">
          <option value="low">🐢 低</option>
          <option value="medium" selected>⚡ 中</option>
          <option value="high">🔥 高</option>
        </select>
      </div>
      <div class="field">
        <label for="f-deadline">截止日期</label>
        <input id="f-deadline" type="date">
        <div class="help">可选；YYYY-MM-DD</div>
      </div>
      <div class="field">
        <label for="f-tags">标签</label>
        <input id="f-tags" type="text" placeholder="标签1, 标签2, 标签3">
        <div class="help">用英文逗号分隔，可选</div>
      </div>
      <div class="form-actions">
        <a class="btn" href="#tasks">取消</a>
        <div class="right">
          <button type="submit" class="btn btn-primary" id="create-btn">创建</button>
        </div>
      </div>
    </form>
  `;
}

function renderEditForm(task) {
  const tagsStr = Array.isArray(task.tags) ? task.tags.join(", ") : "";
  const isArchived = task.archived || task.status === "archived";

  return `
    <div class="page-header">
      <div>
        <h1>✏️ 编辑任务</h1>
        <div class="subtitle">修改后点保存；归档是单向操作</div>
      </div>
    </div>
    <form class="task-edit-card card" id="edit-task-form" autocomplete="off">
      <div class="field">
        <label>任务名</label>
        <div class="readonly-name">
          <span>${escapeHtml(task.name)}</span>
          <span class="task-id">${escapeHtml(task.id)}</span>
        </div>
        <div class="help">name 创建后不可修改（如需改名请归档后新建）</div>
      </div>
      <div class="field">
        <label for="f-status">状态</label>
        <select id="f-status" ${isArchived ? "disabled" : ""}>
          ${STATUS_OPTIONS.map(s => `<option value="${s}" ${s === task.status ? "selected" : ""}>${escapeHtml(statusLabel(s))}</option>`).join("")}
        </select>
        ${isArchived ? `<div class="help">已归档任务不可改状态（先 restore）</div>` : ""}
      </div>
      <div class="field">
        <label for="f-priority">优先级</label>
        <select id="f-priority" ${isArchived ? "disabled" : ""}>
          ${PRIORITY_OPTIONS.map(p => `<option value="${p}" ${p === task.priority ? "selected" : ""}>${escapeHtml(priorityLabel(p))}</option>`).join("")}
        </select>
      </div>
      <div class="field">
        <label for="f-deadline">截止日期</label>
        <input id="f-deadline" type="date" value="${escapeHtml(formatDate(task.deadline) || "")}" ${isArchived ? "disabled" : ""}>
        <div class="help">留空 = 清除</div>
      </div>
      <div class="field">
        <label for="f-tags">标签</label>
        <input id="f-tags" type="text" value="${escapeHtml(tagsStr)}" placeholder="标签1, 标签2" ${isArchived ? "disabled" : ""}>
        <div class="help">英文逗号分隔；完全替换</div>
      </div>
      <div class="form-actions">
        <div>
          ${!isArchived ? `<button type="button" class="btn btn-danger" id="archive-btn">归档</button>` : `<span class="muted text-sm">已归档（${escapeHtml(task.reason || "done")}）</span>`}
        </div>
        <div class="right">
          <a class="btn" href="#tasks">取消</a>
          <button type="submit" class="btn btn-primary" id="save-btn" ${isArchived ? "disabled" : ""}>保存</button>
        </div>
      </div>
    </form>
  `;
}

function statusLabel(s) {
  return ({ pending: "⏳ 待办", in_progress: "▶ 进行中", blocked: "⛔ 阻塞", waiting: "⌛ 等待", archived: "✅ 已归档" })[s] || s;
}
function priorityLabel(p) {
  return ({ low: "🐢 低", medium: "⚡ 中", high: "🔥 高" })[p] || p;
}

// ---- 行为 ----

function bindNewForm() {
  const form = document.getElementById("new-task-form");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("err-name");
    errEl.textContent = "";

    const name = document.getElementById("f-name").value.trim();
    if (!name) {
      errEl.textContent = "任务名不能为空";
      return;
    }
    const priority = document.getElementById("f-priority").value;
    const deadline = document.getElementById("f-deadline").value || null;
    const tagsStr = document.getElementById("f-tags").value.trim();
    const tags = tagsStr ? tagsStr.split(",").map(s => s.trim()).filter(Boolean) : [];

    const btn = document.getElementById("create-btn");
    btn.disabled = true;
    btn.textContent = "创建中…";

    try {
      const task = await api.createTask({ name, priority, deadline, tags });
      toast(`✅ 已创建：${task.name}`, "success");
      navigate("#tasks/" + encodeURIComponent(task.id));
    } catch (err) {
      if (err.code === "duplicate") {
        errEl.textContent = "同名任务已存在，请换个名字";
      } else if (err.code === "validation_error") {
        errEl.textContent = err.message;
      } else {
        toast("❌ 创建失败：" + err.message, "error");
      }
    } finally {
      btn.disabled = false;
      btn.textContent = "创建";
    }
  });
}

function bindEditForm(task) {
  const form = document.getElementById("edit-task-form");
  if (!form) return;
  const isArchived = task.archived || task.status === "archived";

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = document.getElementById("f-status").value;
    const priority = document.getElementById("f-priority").value;
    const deadlineVal = document.getElementById("f-deadline").value;
    const tagsStr = document.getElementById("f-tags").value.trim();
    const tags = tagsStr ? tagsStr.split(",").map(s => s.trim()).filter(Boolean) : [];

    // deadline 留空 = null（清除）
    const deadline = deadlineVal || null;

    const btn = document.getElementById("save-btn");
    btn.disabled = true;
    btn.textContent = "保存中…";

    try {
      await api.updateTask(task.id, { status, priority, deadline, tags });
      toast("✅ 已保存", "success");
      navigate("#tasks");
    } catch (err) {
      toast("❌ 保存失败：" + err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "保存";
    }
  });

  // 归档按钮
  if (!isArchived) {
    const archiveBtn = document.getElementById("archive-btn");
    archiveBtn.addEventListener("click", async () => {
      const reason = await pickArchiveReason();
      if (!reason) return;
      try {
        await api.archiveTask(task.id, reason);
        toast(`✅ 已归档：${task.name}`, "success");
        navigate("#tasks");
      } catch (err) {
        if (err.code === "duplicate") {
          toast("⚠️ 任务已归档", "warning");
        } else {
          toast("❌ 归档失败：" + err.message, "error");
        }
      }
    });
  }
}

function pickArchiveReason() {
  return new Promise((resolve) => {
    const wrap = document.createElement("div");
    wrap.innerHTML = `
      <div class="archive-confirm">
        <h3>📦 归档任务</h3>
        <div class="modal-body">
          归档后任务会从列表隐藏，可在已归档开关下查看。归档不可逆（需要先 restore 才能再次编辑）。
        </div>
        <div class="reason-options">
          ${Object.entries(ARCHIVE_REASONS).map(([k, v]) => `
            <button type="button" class="reason-option" data-reason="${k}">${escapeHtml(v)}</button>
          `).join("")}
        </div>
        <div class="modal-actions">
          <button class="btn cancel-btn">取消</button>
          <button class="btn btn-danger-solid confirm-btn" disabled>确认归档</button>
        </div>
      </div>
    `;
    const close = openModal(wrap);
    let pickedReason = null;
    wrap.querySelectorAll(".reason-option").forEach((btn) => {
      btn.addEventListener("click", () => {
        wrap.querySelectorAll(".reason-option").forEach(b => b.classList.remove("selected"));
        btn.classList.add("selected");
        pickedReason = btn.getAttribute("data-reason");
        wrap.querySelector(".confirm-btn").disabled = false;
      });
    });
    wrap.querySelector(".cancel-btn").onclick = () => { close(); resolve(null); };
    wrap.querySelector(".confirm-btn").onclick = () => {
      close();
      resolve(pickedReason);
    };
  });
}
