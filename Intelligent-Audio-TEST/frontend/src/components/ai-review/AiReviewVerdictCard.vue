<template>
  <div class="ai-review-verdict-card">
    <div class="verdict-card-header">
      <i class="fas fa-sparkles verdict-card-icon"></i>
      <span class="verdict-card-title">{{ AI_REVIEW_VERDICT_COPY.title }}</span>
      <span class="verdict-card-chip">
        <i class="fas fa-clock verdict-card-chip-icon"></i> 对话结论·待保存
      </span>
    </div>

    <div class="verdict-card-compare" v-if="originalEvaluationStatus">
      <span class="compare-label">{{ AI_REVIEW_VERDICT_COPY.compareTitle }}</span>
      <span class="compare-row">
        <span class="compare-item">AI：{{ AI_REVIEW_VERDICT_COPY.title }}</span>
        <span class="compare-arrow">→</span>
        <span class="compare-item">原评估：{{ evalLabel(originalEvaluationStatus) }}</span>
      </span>
    </div>

    <div class="verdict-card-body">
      <span v-if="!content" class="verdict-card-empty">{{ AI_REVIEW_VERDICT_COPY.verdictNotReady }}</span>
      <p v-else class="verdict-card-content">{{ content }}</p>
    </div>

    <p class="verdict-card-note">
      <i class="fas fa-circle-info verdict-card-note-icon"></i>
      {{ AI_REVIEW_VERDICT_COPY.sourceNote }}
    </p>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/log.css'

import { AI_REVIEW_VERDICT_COPY } from '@/domain/constants/aiReviewSession'

defineProps<{
  /** Agent 对话给出的结论说明（自由文本；正式结论以后端 AI 复检记录为准，§5.5 方案A） */
  content: string
  originalEvaluationStatus?: string | null
}>()

function evalLabel(status?: string | null): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'failed': return '评估失败'
    default: return status || '—'
  }
}
</script>

<style scoped>
.ai-review-verdict-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--card);
  padding: 12px 14px;
  margin: 8px 0 10px;
  box-shadow: var(--shadow-sm);
}

.verdict-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.verdict-card-icon {
  color: var(--primary);
  font-size: 13px;
}

.verdict-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground);
}

.verdict-card-chip {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--warning) 15%, transparent);
  color: var(--warning-dark, var(--foreground));
  font-size: 11px;
}

.verdict-card-chip-icon {
  font-size: 10px;
}

.verdict-card-compare {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  background: var(--muted);
  border-radius: var(--radius-control);
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--muted-foreground);
}

.compare-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.compare-arrow {
  color: var(--destructive);
}

.verdict-card-body {
  font-size: 13px;
  color: var(--foreground);
}

.verdict-card-empty {
  color: var(--muted-foreground);
  font-size: 12px;
}

.verdict-card-content {
  margin: 0;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.verdict-card-note {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--muted-foreground);
}

.verdict-card-note-icon {
  margin-top: 2px;
}
</style>
