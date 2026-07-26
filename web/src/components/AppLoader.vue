<script setup>
defineProps({
  label: { type: String, default: "加载中" },
});
</script>

<template>
  <div class="empty" role="status">
    <span class="loader" aria-hidden="true"></span>
    <div class="empty-title">{{ label }}</div>
  </div>
</template>
