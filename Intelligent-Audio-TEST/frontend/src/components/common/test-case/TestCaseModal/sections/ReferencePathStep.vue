<template>
  <div class="rce-step" id="step-ref">
    <div class="rce-step-header">
      <i class="fas fa-file-alt rce-step-icon"></i>
      <span class="rce-step-title">参考参数</span>
      <span class="rce-tag rce-tag-gray">referenceParamsPath · 自动生成 · 只读</span>
    </div>
    <div v-if="round.referenceParamsPath" class="rce-ref-info">
      <i class="fas fa-folder-open"></i>
      <span>{{ round.referenceParamsPath }}</span>
    </div>
    <div v-else class="rce-ref-empty">
      <i class="fas fa-info-circle"></i>
      参考参数将在音频关联后自动生成
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RoundConfigItem } from '@/domain'

defineProps<{
  round: RoundConfigItem
}>()
</script>

<style scoped>
.rce-step {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--gray-light);
}
.rce-step:last-child { border-bottom: none; }

.rce-step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.rce-step-icon { font-size: 14px; color: var(--primary-color, var(--primary)); }
.rce-step-title { font-size: 14px; font-weight: 600; color: var(--text-primary, var(--foreground)); }

.rce-tag {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
}
.rce-tag-gray { background: var(--muted); color: var(--color-gray-400); }

.rce-ref-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--background-secondary, var(--muted));
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary, var(--color-gray-500));
}
.rce-ref-info i { color: var(--text-light, var(--color-gray-400)); }

.rce-ref-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-light, var(--color-gray-400));
  font-size: 13px;
}
.rce-ref-empty i { margin-right: 4px; }
</style>
