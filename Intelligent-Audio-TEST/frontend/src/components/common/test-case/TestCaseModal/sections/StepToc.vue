<template>
  <div class="rce-step-toc">
    <div class="rce-toc-title">本轮步骤</div>
    <div
      v-for="step in steps"
      :key="step.id"
      class="rce-toc-item"
      :class="{ active: activeStep === step.id }"
      @click="$emit('select', step.id)"
    >
      <span class="rce-toc-num">{{ step.num }}</span>
      <i :class="step.icon" class="rce-toc-icon"></i>
      <span>{{ step.label }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  steps: Array<{ id: string; num: number; label: string; icon: string }>
  activeStep: string
}>()

defineEmits<{
  'select': [stepId: string]
}>()
</script>

<style scoped>
.rce-step-toc {
  width: 130px;
  min-width: 130px;
  background: var(--background-primary, #fff);
  border-right: 1px solid var(--border-color, #e0e0e0);
  padding: 12px 8px;
}

.rce-toc-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary, #333);
  margin-bottom: 10px;
  padding: 0 4px;
}

.rce-toc-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--text-secondary, #666);
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: 2px;
}
.rce-toc-item:hover {
  background: rgba(0, 0, 0, 0.03);
  color: var(--primary-color, #ff6a00);
}
.rce-toc-item.active {
  background: var(--primary-light, #fff3e8);
  color: var(--primary-color, #ff6a00);
  font-weight: 500;
}

.rce-toc-num {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--border-color, #e0e0e0);
  color: var(--text-secondary, #666);
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.rce-toc-item.active .rce-toc-num {
  background: var(--primary-color, #ff6a00);
  color: #fff;
}

.rce-toc-icon {
  font-size: 11px;
}
</style>
