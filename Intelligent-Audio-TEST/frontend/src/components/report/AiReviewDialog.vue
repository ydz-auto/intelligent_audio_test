<template>
  <teleport to="body">
    <div class="ai-review-overlay" v-if="visible">
      <div class="ai-review-dialog" @click.stop>
        <div class="ai-review-header">
          <h3 class="ai-review-title">
            <i class="fas fa-sparkles"></i> AI 复核
          </h3>
          <button class="ai-review-close" @click="handleClose" title="关闭">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="ai-review-body">
          <!-- 复核对象摘要 -->
          <div class="ai-review-summary">
            <div class="summary-row">
              <span class="summary-label">用例</span>
              <span class="summary-value">{{ caseName }}</span>
            </div>
            <div class="summary-row" v-if="dimensionName">
              <span class="summary-label">复核维度</span>
              <span class="summary-value">{{ dimensionName }}</span>
            </div>
            <div class="summary-row" v-if="originalEvaluationStatus">
              <span class="summary-label">当前评估状态</span>
              <span class="summary-value">{{ evalStatusLabel(originalEvaluationStatus) }}</span>
            </div>
          </div>

          <p class="ai-review-note">
            由大模型对当前评估结果进行复检，产出复核结论供人工确认；不直接修改统计。
          </p>

          <!-- 待发起：发起按钮 -->
          <div class="ai-review-actions" v-if="phase === 'idle'">
            <button class="btn-primary ai-review-primary" @click="handleInitiate" :disabled="initiating">
              <i class="fas fa-sparkles"></i>
              {{ initiating ? 'AI 复核中…' : '发起 AI 复核' }}
            </button>
          </div>

          <!-- 执行中：进度 -->
          <div class="ai-review-running" v-else-if="phase === 'running'">
            <div class="ai-review-spinner"></div>
            <span class="ai-review-running-text">AI 复核中…</span>
          </div>

          <!-- 已完成：AI 结论卡 + 人工处置 -->
          <div v-else-if="phase === 'completed'" class="ai-review-result">
            <div v-if="errorText" class="ai-review-error">
              <i class="fas fa-exclamation-circle"></i>
              {{ errorText }}
            </div>

            <template v-if="record">
              <div class="ai-review-verdict" :class="verdictClass">
                <span class="verdict-icon">
                  <i :class="verdictIcon"></i>
                </span>
                <span class="verdict-label">{{ verdictLabel }}</span>
                <span class="verdict-confidence">{{ confidenceLabel }}</span>
              </div>

              <div class="ai-review-compare" v-if="record.originalEvaluationStatus">
                <div class="compare-item">
                  <span class="compare-label">AI 判定</span>
                  <span class="compare-value">{{ verdictLabel }}</span>
                </div>
                <div class="compare-arrow"><i class="fas fa-arrow-right"></i></div>
                <div class="compare-item">
                  <span class="compare-label">原评估判定</span>
                  <span class="compare-value">{{ evalStatusLabel(record.originalEvaluationStatus) }}</span>
                </div>
              </div>

              <div class="ai-review-reasoning">
                <span class="reasoning-label">理由</span>
                <p class="reasoning-text">{{ record.reasoning }}</p>
              </div>

              <div class="ai-review-dispose">
                <button class="btn-primary ai-review-adopt" @click="handleAdopt">
                  <i class="fas fa-check-circle"></i> 采纳为复核结果
                </button>
                <button class="btn-secondary ai-review-reject" @click="handleReject">
                  <i class="fas fa-times-circle"></i> 驳回
                </button>
                <button class="btn-ghost ai-review-ignore" @click="handleIgnore">
                  忽略
                </button>
              </div>
            </template>
          </div>

          <!-- 已处置状态 -->
          <div v-else class="ai-review-disposed">
            <i class="fas" :class="disposedIcon"></i>
            <span class="disposed-text">{{ disposedText }}</span>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import '../../assets/styles/test-common.css'
import '../../assets/styles/components/common.css'
import '../../assets/styles/components/button.css'
import '../../assets/styles/components/form.css'
import '../../assets/styles/components/modal.css'
import '../../assets/styles/components/table.css'
import '../../assets/styles/components/navigation.css'
import '../../assets/styles/components/tag.css'
import '../../assets/styles/components/log.css'
import '../../assets/styles/layouts/main.css'

/**
 * AI 复核发起弹窗 + 结论卡 + 人工处置（§4.3）。
 *
 * 状态机（§2.1）：待发起(idle) → 执行中(running) → 已完成(completed)
 * → 已采纳(adopted) / 已驳回(rejected) / 待查(ignored)。
 *
 * 后端 AI 复核端点待后端立项（§8-2）：reviewApi.submitAiReview 等为 `// 待接线`
 * 桩（返回符合 §5.3 schema 的示例结论），FEAT 落地后由接线卡替换为真实请求。
 */
import { computed, ref } from 'vue'
import { AI_REVIEW_VERDICT_LABELS, EVALUATION_STATUS_LABELS } from '@/domain/model/review'

const props = defineProps<{
  visible: boolean
  caseName: string
  dimensionName?: string
  originalEvaluationStatus?: string
  phase: string
  record: any
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
  return AI_REVIEW_VERDICT_LABELS[v as keyof typeof AI_REVIEW_VERDICT_LABELS] ?? '复核通过'
})
const verdictClass = computed(() => {
  if (!props.record?.verdict) return ''
  if (props.record.verdict === 'passed') return 'verdict-passed'
  if (props.record.verdict === 'failed') return 'verdict-failed'
  return 'verdict-uncertain'
})
const verdictIcon = computed(() => {
  if (props.record?.verdict === 'passed') return 'fa-check-circle'
  if (props.record.verdict === 'failed') return 'fa-times-circle'
  return 'fa-question-circle'
})
const confidenceLabel = computed(() => {
  const conf = props.record?.confidence
  if (!conf) return ''
  return `置信度 ${Math.round(conf.value * 100)}%（${conf.label}）`
})

const errorText = computed(() => props.error || '')

const disposedIcon = computed(() => {
  if (props.phase === 'adopted') return 'fa-check-circle'
  if (props.phase === 'rejected') return 'fa-times-circle'
  return 'fa-clock'
})
const disposedText = computed(() => {
  if (props.phase === 'adopted') return '已采纳 AI 复核结论，复核已提交'
  if (props.phase === 'rejected') return '已驳回 AI 复核结论，保留原判定'
  return '已忽略，AI 结论保留待查'
})

const evalStatusLabel = (status?: string) => EVALUATION_STATUS_LABELS[status ?? ''] ?? status ?? '—'

function handleClose() {
  emit('close')
}
function handleInitiate() {
  emit('initiate')
}
function handleAdopt() {
  emit('adopt')
}
function handleReject() {
  emit('reject')
}
function handleIgnore() {
  emit('ignore')
}
</script>

<style scoped>
.ai-review-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--foreground) 40%, transparent);
}
.ai-review-dialog {
  width: 480px;
  max-width: calc(100vw - 32px);
  background: var(--background);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-md);
  display: flex;
  flex-direction: column;
  max-height: 80vh;
}
.ai-review-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.ai-review-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.ai-review-title i {
  color: var(--primary);
}
.ai-review-close {
  background: transparent;
  border: none;
  color: var(--muted-foreground);
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
}
.ai-review-close:hover {
  color: var(--foreground);
}
.ai-review-body {
  padding: 16px 20px;
  overflow-y: auto;
}
.ai-review-summary {
  background: var(--muted);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}
.summary-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
}
.summary-label {
  color: var(--muted-foreground);
  flex-shrink: 0;
}
.summary-value {
  color: var(--foreground);
  word-break: break-all;
}
.ai-review-note {
  margin: 0 0 14px;
  font-size: 13px;
  color: var(--muted-foreground);
  line-height: 1.5;
}
.ai-review-actions {
  display: flex;
  justify-content: flex-end;
}
.ai-review-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--primary);
  color: var(--primary-foreground);
  font-size: 14px;
  cursor: pointer;
}
.ai-review-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.ai-review-running {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
}
.ai-review-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: var(--radius-full);
  animation: aiReviewSpin 0.8s linear infinite;
}
@keyframes aiReviewSpin {
  to { transform: rotate(360deg); }
}
.ai-review-running-text {
  font-size: 14px;
  color: var(--muted-foreground);
}
.ai-review-error {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--destructive);
  margin-bottom: 12px;
}
.ai-review-verdict {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}
.verdict-passed {
  color: var(--success);
  background: var(--success-light);
}
.verdict-failed {
  color: var(--destructive);
  background: var(--destructive-light);
}
.verdict-uncertain {
  color: var(--warning);
  background: var(--warning-light);
}
.verdict-confidence {
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-foreground);
}
.ai-review-compare {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--muted);
  border-radius: var(--radius-md);
  margin-bottom: 12px;
}
.compare-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.compare-label {
  font-size: 12px;
  color: var(--muted-foreground);
}
.compare-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}
.compare-arrow {
  color: var(--muted-foreground);
}
.ai-review-reasoning {
  margin-bottom: 16px;
}
.reasoning-label {
  font-size: 12px;
  color: var(--muted-foreground);
  display: block;
  margin-bottom: 4px;
}
.reasoning-text {
  margin: 0;
  font-size: 13px;
  color: var(--foreground);
  line-height: 1.5;
  word-break: break-word;
}
.ai-review-dispose {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
.ai-review-adopt {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--primary);
  color: var(--primary-foreground);
  font-size: 13px;
  cursor: pointer;
}
.ai-review-reject {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--muted);
  color: var(--foreground);
  font-size: 13px;
  cursor: pointer;
}
.ai-review-ignore {
  padding: 8px 12px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--muted-foreground);
  font-size: 13px;
  cursor: pointer;
}
.ai-review-ignore:hover {
  color: var(--foreground);
}
.ai-review-disposed {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--foreground);
  padding: 8px 0;
}
.ai-review-disposed i {
  color: var(--success);
}
</style>
