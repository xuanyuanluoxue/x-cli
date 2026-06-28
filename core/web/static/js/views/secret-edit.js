// views/secret-edit.js — 新建 / 编辑密钥
//
// 参数：
//   "new"   → 新建模式
//   <name>  → 编辑模式（GET /api/secrets/:name 拉详情）
//
// 字段：
//   name      — 新建可填，编辑只读
//   value     — 必填，password + 眼睛 toggle
//   category  — 可选（默认 "default"）
//   note      — 可选

import { api } from "../api.js";
import { escapeHtml, toast, navigate } from "../utils.js";

export function render(nameOrNew) {
  const isNew = !nameOrNew || nameOrNew === "new";
  const root = document.createElement("div");

  if (isNew) {
    root.innerHTML = renderForm({ isNew: true });
  } else {
    // 编辑模式：先显示 loading，加载完再换 form
    root.innerHTML = `
      <div class="page-header">
        <div>
          <h1>✏️ 编辑密钥</h1>
          <div class="subtitle">修改 value / category / note（name 不可改）</div>
        </div>
      </div>
      <div class="secret-edit-card card">
        <div class="empty"><div class="empty-icon">⏳</div><div class="empty-title">加载中…</div></div>
      </div>
    `;
    api.getSecret(nameOrNew)
      .then((secret) => {
        const main = document.querySelector(".secret-edit-card");
        if (!main) return;
        main.outerHTML = renderForm({ isNew: false, secret });
        queueMicrotask(() => bindEditForm(secret));
      })
      .catch((e) => {
        const main = document.querySelector(".secret-edit-card");
        if (!main) return;
        if (e.code === "not_found") {
          main.outerHTML = `
            <div class="error-page">
              <div class="error-icon">🔍</div>
              <h2>密钥不存在</h2>
              <p>name = <code>${escapeHtml(nameOrNew)}</code></p>
              <a class="btn" href="#secrets">返回列表</a>
            </div>
          `;
        } else if (e.code !== "unauthorized") {
          main.outerHTML = `
            <div class="error-page">
              <div class="error-icon">💥</div>
              <h2>加载失败</h2>
              <p>${escapeHtml(e.message)}</p>
              <a class="btn" href="#secrets">返回列表</a>
            </div>
          `;
        }
      });
  }

  if (isNew) {
    queueMicrotask(() => bindNewForm());
  }
  return Promise.resolve(root);
}

function renderForm({ isNew, secret = null }) {
  const s = secret || { name: "", value: "", category: "default", note: "" };
  return `
    <div class="page-header">
      <div>
        <h1>${isNew ? "➕ 新建密钥" : "✏️ 编辑密钥"}</h1>
        <div class="subtitle">${isNew ? "创建第一个密钥" : "修改 value / category / note（name 不可改）"}</div>
      </div>
    </div>
    <form class="secret-edit-card card" id="secret-form" autocomplete="off">
      <div class="field">
        <label for="f-name">名称 <span style="color:var(--danger)">*</span></label>
        <input id="f-name" type="text" required maxlength="100" value="${escapeHtml(s.name)}" ${isNew ? "" : "readonly"}>
        <div class="help">${isNew ? "建议用英文 / kebab-case（如 minimax / github-token）" : "name 创建后不可修改"}</div>
        <div class="error" id="err-name"></div>
      </div>
      <div class="field">
        <label for="f-value">Value <span style="color:var(--danger)">*</span></label>
        <div style="display:flex; gap:6px; align-items:stretch;">
          <input id="f-value" type="password" required value="${escapeHtml(s.value)}" autocomplete="off">
          <button type="button" class="btn" id="toggle-value" style="padding:0 12px;" title="显示 / 隐藏">👁️</button>
        </div>
        <div class="help">${isNew ? "明文存储在本地 JSON（见 docs/architecture.md）" : "留空 = 不修改；填了 = 覆盖"}</div>
        <div class="error" id="err-value"></div>
      </div>
      <div class="field">
        <label for="f-category">分组</label>
        <input id="f-category" type="text" value="${escapeHtml(s.category || "default")}" placeholder="default">
        <div class="help">可选；用于分类（如 "API"、"DB"、"SSH"）</div>
      </div>
      <div class="field">
        <label for="f-note">备注</label>
        <textarea id="f-note" rows="3" placeholder="来源、用途、轮转时间…">${escapeHtml(s.note || "")}</textarea>
      </div>
      <div class="form-actions">
        <a class="btn" href="#secrets">取消</a>
        <button type="submit" class="btn btn-primary" id="save-btn">${isNew ? "创建" : "保存"}</button>
      </div>
    </form>
  `;
}

function bindNewForm() {
  const form = document.getElementById("secret-form");
  if (!form) return;
  bindToggle();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("f-name").value.trim();
    const value = document.getElementById("f-value").value;
    const category = document.getElementById("f-category").value.trim() || "default";
    const note = document.getElementById("f-note").value.trim();

    document.getElementById("err-name").textContent = "";
    document.getElementById("err-value").textContent = "";
    if (!name) { document.getElementById("err-name").textContent = "名称不能为空"; return; }
    if (!value) { document.getElementById("err-value").textContent = "value 不能为空"; return; }

    const btn = document.getElementById("save-btn");
    btn.disabled = true;
    btn.textContent = "创建中…";

    try {
      await api.createSecret({ name, value, category, note });
      toast("✅ 已创建", "success");
      navigate("#secrets/" + encodeURIComponent(name));
    } catch (err) {
      if (err.code === "duplicate") {
        document.getElementById("err-name").textContent = "同名密钥已存在";
      } else {
        toast("❌ 创建失败：" + err.message, "error");
      }
    } finally {
      btn.disabled = false;
      btn.textContent = "创建";
    }
  });
}

function bindEditForm(secret) {
  const form = document.getElementById("secret-form");
  if (!form) return;
  bindToggle();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const valueEl = document.getElementById("f-value");
    const value = valueEl.value;
    const category = document.getElementById("f-category").value.trim() || "default";
    const note = document.getElementById("f-note").value.trim();

    // 编辑模式 value 留空 = 不修改
    const body = {};
    if (value !== "") body.value = value;
    body.category = category;
    if (note !== secret.note) body.note = note;

    const btn = document.getElementById("save-btn");
    btn.disabled = true;
    btn.textContent = "保存中…";

    try {
      await api.updateSecret(secret.name, body);
      toast("✅ 已保存", "success");
      navigate("#secrets/" + encodeURIComponent(secret.name));
    } catch (err) {
      toast("❌ 保存失败：" + err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "保存";
    }
  });
}

function bindToggle() {
  const btn = document.getElementById("toggle-value");
  if (!btn) return;
  const input = document.getElementById("f-value");
  let visible = false;
  btn.addEventListener("click", () => {
    visible = !visible;
    input.type = visible ? "text" : "password";
    btn.textContent = visible ? "🙈" : "👁️";
  });
}
