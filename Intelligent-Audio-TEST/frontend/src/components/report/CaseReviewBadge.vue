<template>
  <span class="case-review-badge" title="该用例存在人工复核结果，点击查看复核历史" @click.stop="emit('open')">
    <i class="fas fa-clipboard-check"></i>
    <span>{{ props.count !== undefined && props.count > 0 ? `已复核 ${props.count}` : '含复核' }}</span>
  </span>
</template>

<script setup lang="ts">
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/layouts/main.css'

/**
 * 用例卡片「人工复核」Badge（19 规范 §4.1 卡片标记）。
 * 点击打开报告侧复核历史抽屉（人工/AI 两 Tab，ReportReviewHistoryDrawer），
 * 由父组件（SpecificCaseComparisonComponent）控制抽屉状态（§4.3 与 React 对齐）。
 *
 * 数据：来源任务复核历史按 test_case_id 聚合（reviewApi.getReviewHistory，真实）。
 */
const props = defineProps<{
  caseName: string
  /** 已复核结果数（报告快照复核明细 §8-3 未落地前不传，仅显「含复核」无计数，对齐 React §4.1） */
  count?: number
}>()

const emit = defineEmits<{
  (e: 'open'): void
}>()
</script>

<style scoped>
.case-review-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-md);
  font-size: 12px;
  font-weight: 500;
  color: var(--primary);
  background: var(--accent);
  border: 1px solid color-mix(in srgb, var(--primary) 25%, transparent);
  cursor: pointer;
  transition: background 0.2s ease;
}
.case-review-badge:hover {
  background: color-mix(in srgb, var(--primary) 18%, transparent);
}
</style>
