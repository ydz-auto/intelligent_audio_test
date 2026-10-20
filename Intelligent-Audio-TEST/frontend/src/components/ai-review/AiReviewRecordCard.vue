<template>
  <div class="ai-review-record-card">
    <div class="record-card-header">
      <i class="fas fa-robot record-card-icon"></i>
      <span class="record-card-title">{{ AI_REVIEW_RECORD_COPY.recordTitle }}</span>
      <span class="record-card-status" :class="`record-status--${record.status ?? 'unknown'}`">
        {{ aiReviewStatusLabel(record.status) }}
      </span>
      <span v-if="record.adopted" class="record-card-adopted"><i class="fas fa-check-circle"></i> {{ AI_REVIEW_RECORD_COPY.adoptedAt }}</span>
      <span v-else-if="record.rejected" class="record-card-rejected"><i class="fas fa-times-circle"></i> {{ AI_REVIEW_RECORD_COPY.rejectedAt }}</span>
    </div>

    <div class="record-card-verdict" :class="`record-verdict--${record.verdict ?? 'unknown'}`" v-if="showVerdict">
      <i :class="verdictIcon"></i>
      <span class="record-verdict-label">{{ aiReviewVerdictLabel(record.verdict) }}</span>
      <span class="record-verdict-confidence">
        {{ AI_REVIEW_RECORD_COPY.confidence }} {{ Math.round((record.confidence?.value ?? 0) * 100) }}%（{{ record.confidence?.label ?? '—' }}）
      </span>
    </div>

    <div class="record-card-compare" v-if="showVerdict && originalEvaluationStatus">
      <span class="compare-label">{{ AI_REVIEW_VERDICT_COPY.compareTitle }}</span>
      <span class="compare-row">
        <span class="compare-item">AI：{{ aiReviewVerdictLabel(record.verdict) }}</span>
        <span class="compare-arrow">→</span>
        <span class="compare-item">原评估：{{ evalLabel(originalEvaluationStatus) }}</span>
      </span>
    </div>

    <div class="record-card-reasoning" v-if="record.reasoning">
      <span class="reasoning-label">{{ AI_REVIEW_RECORD_COPY.reasoning }}</span>
      <p class="reasoning-text">{{ record.reasoning }}</p>
    </div>

    <p class="record-card-meta" v-if="record.createdAt">
      {{ formatTime(record.createdAt) }}
    </p>
  </div>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/log.css'

import { computed } from 'vue'
import { AI_REVIEW_RECORD_COPY, AI_REVIEW_VERDICT_COPY } from '@/domain/constants/aiReviewSession'
import { aiReviewStatusLabel, aiReviewVerdictLabel } from '@/domain/model/review'
import type { AiReviewRecord } from '@/domain/model/review'

const props = defineProps<{
  /** 后端 AI 复检落位记录（§5.5 方案A：正式结论以 ai_reviews 记录为准） */
  record: AiReviewRecord
  originalEvaluationStatus?: string | null
}>()

const verdictIcon = computed(() => {
  switch (props.record.verdict) {
    case 'passed': return 'fas fa-circle-check'
    case 'failed': return 'fas fa-circle-xmark'
    default: return 'fas fa-circle-question'
  }
})

/**
 * 结论行只在后端落位成功（status=completed 且有 verdict）时展示；
 * running/failed 时后端无 verdict/confidence，避免「复核失败 + 复核通过」矛盾呈现。
 */
const showVerdict = computed(() => props.record.status === 'completed' && !!props.record.verdict)

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
.ai-review-record-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--card);
  padding: 12px 14px;
  margin: 8px 0 10px;
  box-shadow: var(--shadow-sm);
}

.record-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.record-card-icon {
  color: var(--primary);
  font-size: 13px;
}

.record-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--foreground);
}

.record-card-status {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
}

.record-status--running,
.record-status--pending {
  background: color-mix(in srgb, var(--warning) 15%, transparent);
  color: var(--warning-dark, var(--foreground));
}

.record-status--completed {
  background: color-mix(in srgb, var(--success) 15%, transparent);
  color: var(--success-dark, var(--foreground));
}

.record-status--failed {
  background: color-mix(in srgb, var(--destructive) 12%, transparent);
  color: var(--destructive);
}

.record-card-adopted {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--success-dark, var(--foreground));
}

.record-card-rejected {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--destructive);
}

.record-card-verdict {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 12px;
  border-radius: var(--radius-pill);
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 8px;
}

.record-verdict--passed { background: color-mix(in srgb, var(--success) 15%, transparent); color: var(--success-dark, var(--foreground)); }
.record-verdict--failed { background: color-mix(in srgb, var(--destructive) 12%, transparent); color: var(--destructive); }
.record-verdict--uncertain { background: color-mix(in srgb, var(--warning) 15%, transparent); color: var(--warning-dark, var(--foreground)); }

.record-verdict-confidence {
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-foreground);
}

.record-card-compare {
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

.record-card-reasoning {
  margin-bottom: 4px;
}

.reasoning-label {
  display: block;
  font-size: 12px;
  color: var(--muted-foreground);
  margin-bottom: 4px;
}

.reasoning-text {
  margin: 0;
  font-size: 13px;
  color: var(--foreground);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.record-card-meta {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--muted-foreground);
}
</style>
