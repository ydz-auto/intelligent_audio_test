<template>
  <div class="placeholder-page">
    <div class="placeholder-card">
      <i class="fas fa-hard-hat placeholder-icon"></i>
      <h2>{{ title }}</h2>
      <p>{{ description }}</p>
      <p class="placeholder-path">当前路径：{{ route.path }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'

defineProps<{
  title: string
  description?: string
}>()

const route = useRoute()
</script>

<style scoped>
.placeholder-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: var(--page-margin);
}
.placeholder-card {
  text-align: center;
  background: var(--card);
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  padding: 48px 40px;
  max-width: 520px;
  width: 100%;
}
.placeholder-icon {
  font-size: 40px;
  color: var(--warning);
  margin-bottom: 12px;
}
.placeholder-card h2 {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: var(--foreground);
}
.placeholder-card p {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.placeholder-path {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: var(--font-mono, monospace);
}
</style>
