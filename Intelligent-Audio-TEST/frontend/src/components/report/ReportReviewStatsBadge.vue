<template>
  <span
    v-if="reviewCount > 0"
    class="report-review-stats"
    :class="{ clickable }"
    :title="'该报告已复核 ' + reviewCount + ' 条结果'"
    @click="handleClick"
  >
    <i class="fas fa-clipboard-check"></i>
    已复核 {{ reviewCount }} 条
  </span>
</template>

<script setup lang="ts">
/**
 * 报告头/总览复核统计徽章（§4.1 统计入口）。
 *
 * review_count > 0 时显示「已复核 {n} 条」；点击锚点到具体用例分区
 * 或筛选复核用例（由父组件 handleClick 决定，默认锚点 #section-case）。
 */
const props = defineProps<{
  reviewCount: number
  clickable?: boolean
}>()

const emit = defineEmits<{
  (e: 'click'): void
}>()

function handleClick() {
  if (!props.clickable) return
  emit('click')
}
</script>

<style scoped>
.report-review-stats {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--primary);
  background: var(--accent);
  border: 1px solid color-mix(in srgb, var(--primary) 30%, transparent);
}
.report-review-stats.clickable {
  cursor: pointer;
}
.report-review-stats.clickable:hover {
  background: color-mix(in srgb, var(--primary) 16%, transparent);
}
</style>
