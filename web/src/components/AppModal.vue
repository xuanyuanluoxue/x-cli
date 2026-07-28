<script setup>
import { watch, onBeforeUnmount } from "vue";
import { modalState, resolveModal } from "@/utils/ui.js";

function onBackdrop(e) {
  if (e.target === e.currentTarget) resolveModal(false);
}
function onKey(e) {
  if (e.key === "Escape" && modalState.current) resolveModal(false);
}

watch(
  () => !!modalState.current,
  (open) => {
    if (open) document.addEventListener("keydown", onKey);
    else document.removeEventListener("keydown", onKey);
  },
);
onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
</script>

<template>
  <Teleport to="body">
    <div v-if="modalState.current" class="modal-backdrop" @click="onBackdrop">
      <div class="modal" role="alertdialog" aria-modal="true" :aria-label="modalState.current.title">
        <h3>{{ modalState.current.title }}</h3>
        <div class="modal-body">{{ modalState.current.body }}</div>
        <label v-if="modalState.current.checkboxLabel" class="modal-option">
          <input v-model="modalState.current.checked" type="checkbox">
          <span>{{ modalState.current.checkboxLabel }}</span>
        </label>
        <div class="modal-actions">
          <button class="btn" @click="resolveModal(false)">{{ modalState.current.cancelText }}</button>
          <button
            class="btn"
            :class="modalState.current.danger ? 'btn-danger-solid' : 'btn-primary'"
            @click="resolveModal(true)"
          >{{ modalState.current.confirmText }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
