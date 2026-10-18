<template>
  <button class="agent-button" title="灵犀Agent" @click="goAiChat">
    <i class="fas fa-robot"></i>
    <span class="agent-button__label">灵犀Agent</span>
  </button>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goAiChat() {
  router.push('/ai-chat')
}
</script>

<style scoped>
.agent-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border: 1px solid var(--ring);
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: var(--primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}
.agent-button:hover {
  background: var(--primary);
  color: var(--primary-foreground);
}
.agent-button__label {
  display: none;
}
@media (min-width: 1280px) {
  .agent-button__label {
    display: inline;
  }
}
</style>
