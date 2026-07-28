<script setup>
import { useRoute } from "vue-router";
const route = useRoute();
</script>

<template>
  <div class="error-page">
    <h2>页面不存在</h2>
    <p>找不到路径 <code>{{ route.path }}</code>，试试侧栏导航？</p>
    <router-link class="btn btn-primary" :to="{ name: 'tasks' }">返回任务列表</router-link>
  </div>
</template>
