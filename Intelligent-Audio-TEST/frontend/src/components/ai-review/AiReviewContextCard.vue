<template>
  <div class="ai-review-context-card">
    <div class="context-card-header">
      <i class="fas fa-clipboard-list context-card-icon"></i>
      <span class="context-card-title">{{ AI_REVIEW_CONTEXT_COPY.title }}</span>
    </div>

    <div v-if="!context" class="context-card-loading">
      <span class="loading-spinner-small"></span>
      <span>{{ AI_REVIEW_CONTEXT_COPY.loading }}</span>
    </div>

    <template v-else>
      <div class="context-row">
        <span class="context-label">{{ AI_REVIEW_CONTEXT_COPY.object }}</span>
        <span class="context-value">{{ context.caseName }}<CaseIdBadge v-if="context.caseId" :case-id="context.caseId" /></span>
      </div>

      <div class="context-row">
        <span class="context-label">{{ AI_REVIEW_CONTEXT_COPY.resultsCount }}</span>
        <span class="context-badges">
          <span
            v-for="r in context.results"
            :key="String(r.id)"
            class="result-badge"
            :title="`执行：${execLabel(r.executionStatus)}｜评估：${evalLabel(r.evaluationStatus)}`"
          >
            <i class="fas fa-microchip result-badge-icon"></i>
            {{ r.deviceName || r.apiName || `结果 #${r.id}` }}
          </span>
        </span>
      </div>

      <div v-if="context.lowDimensionText" class="context-row">
        <span class="context-label">{{ AI_REVIEW_CONTEXT_COPY.lowDimension }}</span>
        <span class="context-value context-value--warning">{{ context.lowDimensionText }}</span>
      </div>

      <div v-if="context.llmCommentText" class="context-row">
        <span class="context-label">{{ AI_REVIEW_CONTEXT_COPY.llmComment }}</span>
        <span class="context-value">{{ context.llmCommentText }}</span>
      </div>

      <div class="context-row">
        <span class="context-label">{{ AI_REVIEW_CONTEXT_COPY.existingConclusion }}</span>
        <span v-if="context.existingRecord" class="context-badge context-badge--existing">
          <i class="fas fa-circle-check"></i>
          {{ aiReviewStatusLabel(context.existingRecord.status) }}·{{ context.existingRecord.verdict }}（{{ formatTime(context.existingRecord.createdAt) }}）
        </span>
        <span v-else class="context-value context-value--muted">{{ AI_REVIEW_CONTEXT_COPY.noExisting }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'

import { AI_REVIEW_CONTEXT_COPY } from '@/domain/constants/aiReviewSession'
import { aiReviewStatusLabel } from '@/domain/model/review'
import CaseIdBadge from '@/components/common/CaseIdBadge.vue'
import type { AiReviewContext } from '@/composables/aiReviewSession'

defineProps<{
  context: AiReviewContext | null
}>()

function execLabel(status?: string | null): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'failed': return '执行失败'
    case 'stopped': return '已停止'
    case 'skipped': return '已跳过'
    default: return status || '—'
  }
}

function evalLabel(status?: string | null): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'failed': return '评估失败'
    default: return status || '—'
  }
}

function formatTime(ts?: string | null): string {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  return d.toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.ai-review-context-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--card);
  padding: 12px 14px;
  margin-bottom: 10px;
  box-shadow: var(--shadow-sm);
}

.context-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.context-card-icon {
  color: var(--primary);
  font-size: 13px;
}

.context-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground);
}

.context-card-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  color: var(--muted-foreground);
}

.loading-spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: var(--radius-full);
  animation: ai-review-spin 0.8s linear infinite;
}

@keyframes ai-review-spin {
  to { transform: rotate(360deg); }
}

.context-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 3px 0;
  font-size: 12px;
}

.context-label {
  flex-shrink: 0;
  width: 84px;
  color: var(--muted-foreground);
}

.context-value {
  color: var(--foreground);
  word-break: break-all;
}

.context-value--muted {
  color: var(--muted-foreground);
}

.context-value--warning {
  color: var(--warning-dark, var(--foreground));
}

.context-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.result-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--muted);
  color: var(--foreground);
  font-size: 11px;
}

.result-badge-icon {
  color: var(--muted-foreground);
  font-size: 10px;
}

.context-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
}

.context-badge--existing {
  background: color-mix(in srgb, var(--success) 12%, transparent);
  color: var(--success-dark, var(--foreground));
}
</style>
