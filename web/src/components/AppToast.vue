<script setup>
import { toastState } from "@/utils/ui.js";
</script>

<template>
  <div id="toast-root" aria-live="polite" aria-atomic="false">
    <div
      v-for="t in toastState.items"
      :key="t.id"
      class="toast"
      :class="[`toast-${t.type}`, { leaving: t.leaving }]"
      role="status"
    >{{ t.message }}</div>
  </div>
</template>
