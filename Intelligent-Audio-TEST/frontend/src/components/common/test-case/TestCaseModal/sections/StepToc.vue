<template>
  <div class="rce-step-toc">
    <div
      v-for="step in steps"
      :key="step.id"
      class="rce-toc-item"
      :class="{ active: activeStep === step.id }"
      @click="$emit('select', step.id)"
    >
      <span class="rce-toc-num">{{ step.num }}</span>
      <i :class="step.icon" class="rce-toc-icon"></i>
      <span class="rce-toc-label">{{ step.label }}</span>
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
  display: flex;
  align-items: stretch;
  gap: 0;
  padding: 0 16px;
  background: var(--background-primary, #fff);
  border-bottom: 1px solid var(--border-color, #e8e8e8);
  flex-shrink: 0;
}

.rce-toc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 18px;
  font-size: 14px;
  color: var(--text-secondary, #999);
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  position: relative;
}
.rce-toc-item::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 0;
  height: 2px;
  background: var(--primary-color, #ff6a00);
  border-radius: 1px;
  transform: translateX(-50%);
  transition: width 0.2s ease;
}
.rce-toc-item:hover {
  color: var(--text-primary, #333);
}
.rce-toc-item.active {
  color: var(--primary-color, #ff6a00);
  font-weight: 600;
}
.rce-toc-item.active::after {
  width: 60%;
}

.rce-toc-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #f0f0f0;
  color: var(--text-secondary, #999);
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s ease;
}
.rce-toc-item:hover .rce-toc-num {
  background: #e8e8e8;
}
.rce-toc-item.active .rce-toc-num {
  background: var(--primary-color, #ff6a00);
  color: #fff;
}

.rce-toc-icon {
  font-size: 14px;
  opacity: 0.6;
}
.rce-toc-item.active .rce-toc-icon {
  opacity: 1;
}

.rce-toc-label {
  font-size: 14px;
}
</style>
