<template>
  <Teleport to="body">
    <div class="ai-review-overlay" @click.self="emit('close')">
      <div class="ai-review-dialog">
        <!-- 头部 -->
        <div class="ai-header">
          <h3><i class="fas fa-sparkles"></i> AI 复核 — {{ caseName || '用例' }}</h3>
          <button class="ai-close" @click="emit('close')"><i class="fas fa-times"></i></button>
        </div>

        <div class="ai-body">
          <p class="ai-tip">
            由大模型对当前评估结果进行复检，产出复核结论供人工确认；<b>不直接修改统计</b>。
          </p>

          <!-- 复核对象摘要 -->
          <div class="ai-target">
            <span class="ai-target-case" :title="caseName">{{ caseName || '用例' }}</span>
            <span class="ai-target-rt" :title="`当前评估状态：${evalLabel(evaluationStatus)}`">
              评估：{{ evalLabel(evaluationStatus) }}
            </span>
            <span class="ai-target-results">{{ results.length }} 条结果</span>
          </div>

          <!-- 待发起 -->
          <div v-if="phase === 'idle'" class="ai-idle">
            <button class="ai-btn ai-btn-primary" @click="launch">
              <i class="fas fa-wand-magic-sparkles"></i> 发起 AI 复核
            </button>
          </div>

          <!-- 执行中 -->
          <div v-else-if="phase === 'running'" class="ai-running">
            <i class="fas fa-spinner fa-spin"></i> AI 复核中，请稍候…
          </div>

        <!-- 已完成 -->
          <div v-else-if="phase === 'completed' && record" class="ai-record">
            <div class="ai-verdict">
              <span class="ai-verdict-badge" :class="verdictClass">
                <i :class="verdictIcon"></i> {{ verdictText }}
              </span>
              <span class="ai-confidence">置信度 {{ aiConfidenceLabel(record.confidence?.value ?? 0) }}（{{ Math.round((record.confidence?.value ?? 0) * 100) }}%）</span>
            </div>
            <p class="ai-reasoning">{{ record.reasoning }}</p>
            <div class="ai-compare">
              <span>AI 判定 vs 原评估判定</span>
              <span class="ai-compare-row">
                <span class="ai-compare-item"><b>AI：</b>{{ verdictText }}</span>
                <span class="ai-compare-arrow">→</span>
                <span class="ai-compare-item"><b>原评估：</b>{{ evalLabel(evaluationStatus) }}</span>
              </span>
            </div>
            <p class="ai-adopt-hint">人工采纳后落入人工复核语义（改判评估状态 + 留痕 + 统计重算）</p>
            <div class="ai-actions">
              <button class="ai-btn ai-btn-primary" @click="adopt">
                <i class="fas fa-clipboard-check"></i> 采纳为复核结果
              </button>
              <button class="ai-btn" @click="reject">
                <i class="fas fa-xmark"></i> 驳回
              </button>
              <button class="ai-btn" @click="emit('close')">
                <i class="fas fa-eye-slash"></i> 忽略（保留待查）
              </button>
            </div>
          </div>

          <!-- 已采纳 / 已驳回 -->
          <div v-else-if="phase === 'adopted'" class="ai-done ai-done--adopted">
            <i class="fas fa-circle-check"></i> 已采纳 AI 复核结论，请在复核弹窗中确认提交
          </div>
          <div v-else-if="phase === 'rejected'" class="ai-done ai-done--rejected">
            <i class="fas fa-circle-xmark"></i> 已驳回 AI 复核结论，原判定保持不变（记录标记已驳回备查）
          </div>

          <p v-if="errorText" class="ai-error">{{ errorText }}</p>
        </div>

        <div class="ai-footer">
          <button class="ai-btn" @click="emit('close')">关闭</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/navigation.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'
import '../../../assets/styles/layouts/main.css'

/**
 * AI 复核弹窗（19 规范 §5.2 + §2.1 AI 复核状态机：待发起→执行中→已完成→已采纳/已驳回/待查）。
 * 定位：建议层，不直接改统计；只有人工「采纳」才落入人工复核语义（开 §3.2 复核弹窗预填
 * AI 判定的评估状态 + 备注=AI 理由 → 人工确认提交 → POST /tasks/results/ai-review/{id}/adopt
 * 由后端落 test_result_reviews 留痕 + 统计重算 + 标记采纳）。
 * 消费 reviewAiApi（requestAiReview / rejectAiReview）真实端点；采纳由父级打开复核弹窗
 * 确认后带改判载荷调用 adoptAiReview，本组件不直接落采纳端点。
 */
import { ref, computed } from 'vue'
import {
  AI_VERDICT_LABELS, aiConfidenceLabel, requestAiReview, rejectAiReview,
  type AiReviewRecord, type AiReviewPhase,
} from '../../../infrastructure/api/reviewAiApi'

const props = defineProps<{
  taskId: number
  caseId: string
  caseName?: string
  /** 发起对象（用例执行结果行；§5.2 可发起对象 = 评估已完成/评估失败） */
  results: Array<{ id: string | number }>
  /** 用例当前评估状态（AI 判定 vs 原评估判定对比行） */
  evaluationStatus?: string | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  /** 人工采纳 → 父级打开 §3.2 复核弹窗预填（评估状态 + 备注=AI 理由 + 记录 id） */
  (e: 'adopt', preset: { recordId: number; evaluationStatus?: string; comment: string }): void
}>()

const phase = ref<AiReviewPhase>('idle')
const record = ref<AiReviewRecord | null>(null)
const errorText = ref('')

const verdictClass = computed(() => ({
  'ai-verdict-badge--passed': record.value?.verdict === 'passed',
  'ai-verdict-badge--failed': record.value?.verdict === 'failed',
  'ai-verdict-badge--uncertain': record.value?.verdict === 'uncertain',
}))
const verdictIcon = computed(() => {
  switch (record.value?.verdict) {
    case 'passed': return 'fas fa-circle-check'
    case 'failed': return 'fas fa-circle-xmark'
    default: return 'fas fa-circle-question'
  }
})
const verdictText = computed(() => {
  const v = record.value?.verdict
  return v ? AI_VERDICT_LABELS[v] : ''
})

function evalLabel(status?: string | null): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'failed': return '评估失败'
    case 'pending': return '待评估'
    case 'evaluating': return '评估中'
    default: return status || '—'
  }
}

async function launch() {
  if (!props.results.length) return
  phase.value = 'running'
  errorText.value = ''
  try {
    record.value = await requestAiReview(props.taskId, props.caseId, {
      resultIds: props.results.map((r) => Number(r.id)),
    })
    phase.value = 'completed'
  } catch (err: any) {
    errorText.value = err?.message || 'AI 复核发起失败，请稍后重试'
    phase.value = 'idle'
  }
}

/** 采纳：仅向父级派发预填载荷（AI 判定评估状态 + 理由）；父级开 §3.2 复核弹窗确认后调 adopt 端点 */
function adopt() {
  if (!record.value) return
  const verdict = record.value.verdict
  // §2.1：通过→已完成，不通过→评估失败，存疑→留给人工
  const presetEvaluation = verdict === 'passed' ? 'completed' : verdict === 'failed' ? 'failed' : undefined
  emit('adopt', {
    recordId: record.value.id,
    evaluationStatus: presetEvaluation,
    comment: record.value.reasoning,
  })
}

async function reject() {
  if (!record.value) return
  try {
    await rejectAiReview(record.value.id)
    phase.value = 'rejected'
  } catch (err: any) {
    errorText.value = err?.message || 'AI 复核驳回失败，请稍后重试'
  }
}
</script>

<style scoped>
.ai-review-overlay {
  position: fixed;
  inset: 0;
  z-index: 1060;
  background: color-mix(in srgb, var(--color-black) 40%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
}
.ai-review-dialog {
  width: min(520px, 92vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--background, #fff);
  border-radius: var(--radius-card, var(--radius-xl));
  box-shadow: var(--shadow-lg, 0 8px 24px rgb(0 0 0 / 0.12));
}
.ai-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color, var(--color-slate-200));
}
.ai-header h3 {
  margin: 0;
  flex: 1;
  font-size: 16px;
  font-weight: var(--font-weight-semibold, 600);
  color: var(--text-primary, var(--foreground));
  display: flex;
  align-items: center;
  gap: 8px;
}
.ai-header h3 i {
  color: var(--primary-color, var(--primary));
}
.ai-close {
  border: none;
  background: none;
  color: var(--text-secondary, var(--color-slate-500));
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
}
.ai-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}
.ai-tip {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-secondary, var(--color-slate-500));
}
.ai-target {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 12px;
  border: 1px solid var(--border-color, var(--color-slate-200));
  border-radius: var(--radius-control);
  margin-bottom: 14px;
  font-size: 12px;
}
.ai-target-case {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  color: var(--text-primary, var(--foreground));
}
.ai-target-rt {
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  background: var(--color-slate-100);
  color: var(--color-slate-600);
}
.ai-target-results {
  color: var(--text-secondary, var(--color-slate-500));
}
.ai-idle {
  text-align: center;
  padding: 16px 0;
}
.ai-running {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px 0;
  color: var(--text-secondary, var(--color-slate-500));
  font-size: 13px;
}
.ai-record {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ai-verdict {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ai-verdict-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 12px;
  border-radius: var(--radius-pill);
  font-size: 13px;
  font-weight: 500;
}
.ai-verdict-badge--passed { background: var(--color-emerald-100); color: var(--color-emerald-600); }
.ai-verdict-badge--failed { background: var(--color-red-100); color: var(--color-red-600); }
.ai-verdict-badge--uncertain { background: var(--color-amber-100); color: var(--color-amber-700); }
.ai-confidence {
  font-size: 12px;
  color: var(--text-secondary, var(--color-slate-500));
}
.ai-reasoning {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--border-color, var(--color-slate-200));
  border-radius: var(--radius-control);
  background: color-mix(in srgb, var(--muted) 20%, transparent);
  font-size: 13px;
  color: var(--text-primary, var(--foreground));
}
.ai-compare {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary, var(--color-slate-500));
}
.ai-compare-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ai-compare-arrow {
  color: var(--danger-color, #dc2626);
}
.ai-adopt-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary, var(--color-slate-500));
}
.ai-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.ai-done {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  font-size: 13px;
}
.ai-done--adopted { color: var(--color-emerald-600); }
.ai-done--rejected { color: var(--danger-color, #dc2626); }
.ai-error {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--danger-color, #dc2626);
}
.ai-footer {
  display: flex;
  justify-content: flex-end;
  padding: 12px 20px;
  border-top: 1px solid var(--border-color, var(--color-slate-200));
}
.ai-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--color-slate-300, #cbd5e1);
  border-radius: var(--radius-control);
  background: var(--background, #fff);
  color: var(--foreground, #1e293b);
  font-size: 13px;
  cursor: pointer;
}
.ai-btn:hover {
  border-color: var(--primary, #ff6a00);
  color: var(--primary, #ff6a00);
}
.ai-btn-primary {
  background: var(--primary, #ff6a00);
  border-color: var(--primary, #ff6a00);
  color: #fff;
}
.ai-btn-primary:hover {
  background: var(--primary-dark, #e55d00);
  color: #fff;
}
</style>
