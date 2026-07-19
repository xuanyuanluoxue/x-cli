// utils/ui.js — toast + confirm modal 的轻量响应式服务
//
// 用法：
//   import { toast, confirmDialog } from "@/utils/ui.js";
//   toast("已保存", "success");
//   const ok = await confirmDialog({ title, body, danger: true });
//
// App.vue 挂载 <AppToast/> 与 <AppModal/> 消费这里的响应式状态。
import { reactive } from "vue";

// ---- toast ----
let toastSeq = 0;
export const toastState = reactive({ items: [] });

export function toast(message, type = "info", duration = 2400) {
  const id = ++toastSeq;
  toastState.items.push({ id, message, type, leaving: false });
  setTimeout(() => {
    const item = toastState.items.find((t) => t.id === id);
    if (item) item.leaving = true;
    setTimeout(() => {
      const i = toastState.items.findIndex((t) => t.id === id);
      if (i >= 0) toastState.items.splice(i, 1);
    }, 200);
  }, duration);
}

// ---- confirm modal ----
// modalState.current = { title, body, confirmText, cancelText, danger, resolve }
export const modalState = reactive({ current: null });

export function confirmDialog({
  title,
  body,
  confirmText = "确认",
  cancelText = "取消",
  danger = false,
}) {
  return new Promise((resolve) => {
    modalState.current = { title, body, confirmText, cancelText, danger, resolve };
  });
}

export function resolveModal(result) {
  const cur = modalState.current;
  modalState.current = null;
  if (cur) cur.resolve(result);
}
