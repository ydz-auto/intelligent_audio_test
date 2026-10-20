<template>
  <Teleport to="body">
    <div v-if="visible" class="qreview-overlay" @click.self="emit('close')">
      <div class="qreview-dialog" @click.stop>
        <div class="qreview-header">
          <h3 class="qreview-title">
            <i class="fas fa-bolt"></i> 快速复核 — {{ caseName || '用例' }}
          </h3>
          <button class="qreview-close" @click="emit('close')" title="关闭">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="qreview-body">
          <p class="qreview-note">
            快速复核为一次性状态机（发起 → 结论），适合批量/低分初筛，不可追问；深度追问请用「AI 复核」会话。
            结论不直接修改统计，采纳后才落人工复核语义。
          </p>

          <!-- 待发起：发起按钮 -->
          <div v-if="phase === 'idle'" class="qreview-idle">
            <button class="qreview-btn qreview-btn-primary" @click="emit('initiate')" :disabled="initiating">
              <i class="fas fa-sparkles"></i>
              {{ initiating ? 'AI 复核中…' : '发起 AI 复核' }}
            </button>
          </div>

          <!-- 执行中：进度 -->
          <div v-else-if="phase === 'running'" class="qreview-running">
            <i class="fas fa-spinner fa-spin"></i>
            <span>AI 复核中，请稍候…</span>
          </div>

          <!-- 已完成：AI 结论卡 + 人工处置 -->
          <div v-else-if="phase === 'completed'" class="qreview-result">
            <div v-if="errorText" class="qreview-error">
              <i class="fas fa-circle-exclamation"></i>
              {{ errorText }}
            </div>

            <template v-if="record">
              <!-- 后端复检未出结论（running/pending/failed）：显状态，不显结论行（§5.5 方案A，对齐记录卡口径） -->
              <div v-if="record.status && record.status !== 'completed'" class="qreview-status" :class="`qreview-status--${String(record.status)}`">
                <i class="fas fa-robot"></i>
                <span>后端 AI 复检：{{ aiReviewStatusLabel(record.status) }}</span>
              </div>

              <template v-else>
                <div class="qreview-verdict" :class="verdictClass">
                  <i :class="verdictIcon"></i>
                  <span class="qreview-verdict-label">{{ verdictLabel }}</span>
                  <span class="qreview-confidence">
                    置信度 {{ Math.round((record.confidence?.value ?? 0) * 100) }}%（{{ record.confidence?.label ?? '—' }}）
                  </span>
                </div>

                <div class="qreview-compare" v-if="record.originalEvaluationStatus">
                  <span class="qreview-compare-label">AI 判定 vs 原评估判定</span>
                  <span class="qreview-compare-row">
                    <span class="qreview-compare-item">AI：{{ verdictLabel }}</span>
                    <span class="qreview-compare-arrow">→</span>
                    <span class="qreview-compare-item">原评估：{{ evalStatusLabel(record.originalEvaluationStatus) }}</span>
                  </span>
                </div>

                <div class="qreview-reasoning" v-if="record.reasoning">
                  <span class="qreview-reasoning-label">理由</span>
                  <p class="qreview-reasoning-text">{{ record.reasoning }}</p>
                </div>

                <!-- 采纳/驳回仅在后端复检 completed（结论落位）后开放（§5.5 契约） -->
                <div class="qreview-dispose">
                  <button class="qreview-btn qreview-btn-primary" @click="emit('adopt')">
                    <i class="fas fa-clipboard-check"></i> 采纳为复核结果
                  </button>
                  <button class="qreview-btn" @click="emit('reject')">
                    <i class="fas fa-xmark"></i> 驳回
                  </button>
                  <button class="qreview-btn qreview-btn-ghost" @click="emit('ignore')">
                    <i class="fas fa-eye-slash"></i> 忽略（保留待查）
                  </button>
                </div>
              </template>
            </template>
          </div>

          <!-- 已处置状态 -->
          <div v-else class="qreview-disposed">
            <i class="fas" :class="disposedIcon"></i>
            <span class="qreview-disposed-text">{{ disposedText }}</span>
          </div>
        </div>

        <div class="qreview-footer">
          <button class="qreview-btn" @click="emit('close')">关闭</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/log.css'

import { computed } from 'vue'
import { AI_REVIEW_VERDICT_LABELS, aiReviewStatusLabel } from '@/domain/model/review'
import type { AiReviewRecord } from '@/domain/model/review'

/**
 * 报告侧「快速复核」弹窗（19 规范 §5.1 次要入口：一次性状态机，批量/低分初筛，不可追问）。
 *
 * 定位：建议层，不直接改统计；只有人工「采纳」才落入人工复核语义（开 §3.2 复核弹窗预填
 * AI 判定的评估状态 + 备注=AI 理由 → 人工确认提交 → 单次 adopt（POST /ai-review/{id}/adopt，
 * 防双写留痕））。状态由父级经 useReportReviews 一次性状态机（aiReviewMap）驱动。
 */
const props = defineProps<{
  visible: boolean
  caseName: string
  phase: string
  record: AiReviewRecord | null
  error: string
  initiating: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'initiate'): void
  (e: 'adopt'): void
  (e: 'reject'): void
  (e: 'ignore'): void
}>()

const verdictLabel = computed(() => {
  const v = props.record?.verdict as string | undefined
  if (!v) return ''
  return AI_REVIEW_VERDICT_LABELS[v as keyof typeof AI_REVIEW_VERDICT_LABELS] ?? v
})
const verdictClass = computed(() => {
  const v = props.record?.verdict
  if (v === 'passed') return 'qreview-verdict--passed'
  if (v === 'failed') return 'qreview-verdict--failed'
  return 'qreview-verdict--uncertain'
})
const verdictIcon = computed(() => {
  switch (props.record?.verdict) {
    case 'passed': return 'fas fa-circle-check'
    case 'failed': return 'fas fa-circle-xmark'
    default: return 'fas fa-circle-question'
  }
})
const errorText = computed(() => props.error || '')

const disposedIcon = computed(() => {
  if (props.phase === 'adopted') return 'fas fa-circle-check'
  if (props.phase === 'rejected') return 'fas fa-circle-xmark'
  return 'fas fa-clock'
})
const disposedText = computed(() => {
  if (props.phase === 'adopted') return '已采纳 AI 复核结论，复核已提交'
  if (props.phase === 'rejected') return '已驳回 AI 复核结论，原判定保持不变（记录标记已驳回备查）'
  return '已忽略，AI 结论保留待查'
})

function evalStatusLabel(status?: string | null): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'failed': return '评估失败'
    case 'pending': return '待评估'
    case 'running': return '评估中'
    default: return status || '—'
  }
}
</script>

<style scoped>
.qreview-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--foreground) 40%, transparent);
}
.qreview-dialog {
  width: min(480px, 92vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-md);
}
.qreview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.qreview-title {
  margin: 0;
  flex: 1;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.qreview-title i {
  color: var(--primary);
}
.qreview-close {
  background: transparent;
  border: none;
  color: var(--muted-foreground);
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
}
.qreview-close:hover {
  color: var(--foreground);
}
.qreview-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}
.qreview-note {
  margin: 0 0 14px;
  font-size: 13px;
  color: var(--muted-foreground);
  line-height: 1.5;
}
.qreview-idle {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}
.qreview-running {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px 0;
  color: var(--muted-foreground);
  font-size: 13px;
}
.qreview-result {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.qreview-error {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid color-mix(in srgb, var(--destructive) 30%, transparent);
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--destructive) 8%, transparent);
  color: var(--destructive);
  font-size: 12px;
}
.qreview-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--muted) 20%, transparent);
  font-size: 13px;
  color: var(--foreground);
}
.qreview-status--failed {
  color: var(--destructive);
  border-color: color-mix(in srgb, var(--destructive) 30%, transparent);
  background: color-mix(in srgb, var(--destructive) 8%, transparent);
}
.qreview-status--running,
.qreview-status--pending {
  color: var(--warning-dark, var(--warning));
  border-color: color-mix(in srgb, var(--warning) 30%, transparent);
}
.qreview-verdict {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.qreview-verdict i {
  font-size: 14px;
}
.qreview-verdict--passed {
  color: var(--success-dark, var(--success));
}
.qreview-verdict--failed {
  color: var(--destructive);
}
.qreview-verdict--uncertain {
  color: var(--warning-dark, var(--warning));
}
.qreview-verdict-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}
.qreview-confidence {
  font-size: 12px;
  color: var(--muted-foreground);
}
.qreview-compare {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--muted-foreground);
}
.qreview-compare-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.qreview-compare-arrow {
  color: var(--destructive);
}
.qreview-reasoning {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--muted) 20%, transparent);
}
.qreview-reasoning-label {
  font-size: 12px;
  color: var(--muted-foreground);
}
.qreview-reasoning-text {
  margin: 0;
  font-size: 13px;
  color: var(--foreground);
  line-height: 1.5;
  word-break: break-word;
}
.qreview-dispose {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.qreview-disposed {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  font-size: 13px;
  color: var(--muted-foreground);
}
.qreview-disposed i {
  color: var(--success-dark, var(--success));
}
.qreview-footer {
  display: flex;
  justify-content: flex-end;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}
.qreview-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--background);
  color: var(--foreground);
  font-size: 13px;
  cursor: pointer;
}
.qreview-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}
.qreview-btn-primary {
  background: var(--primary);
  border-color: var(--primary);
  color: var(--primary-foreground);
}
.qreview-btn-primary:hover {
  background: var(--primary-hover);
  border-color: var(--primary-hover);
  color: var(--primary-foreground);
}
.qreview-btn-ghost {
  border-color: transparent;
  background: transparent;
}
</style>
