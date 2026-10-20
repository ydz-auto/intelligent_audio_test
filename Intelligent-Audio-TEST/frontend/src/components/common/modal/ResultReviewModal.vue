<template>
  <div class="result-review-modal">
    <div class="modal-body">
      <p class="review-tip">
        对 {{ results.length }} 条结果进行人工复核（逐条留痕，历史不覆盖）。
      </p>

      <!-- 结果摘要（单条=1 → 单条复核；多条 → 批量复核） -->
      <div class="review-summary" :class="{ 'review-summary--batch': results.length > 1 }">
        <div v-if="results.length === 1 && results[0]" class="review-summary-row">
          <span class="rs-name" :title="caseName || '用例'">{{ caseName || '用例' }}</span>
          <span class="rs-badge rs-exec" :class="results[0].executionStatus">{{ execLabel(results[0].executionStatus) }}</span>
          <span class="rs-badge rs-eval" :class="summaryEvaluation">{{ evalLabel(summaryEvaluation) }}</span>
          <span class="rs-dim">{{ results[0].deviceName || results[0].apiName || '—' }}</span>
          <span v-if="results[0].reviewed" class="reviewed-badge" title="该结果已存在人工复核结果，详见「复核历史」">
            <i class="fas fa-clipboard-check"></i> 已复核
          </span>
        </div>
        <div v-else class="review-summary-list">
          <div v-for="(r, idx) in results" :key="r.resultId" class="review-summary-row">
            <span class="rs-index">{{ idx + 1 }}</span>
            <span class="rs-name" :title="caseNameByResultId?.[r.resultId] ?? caseName ?? '用例'">
              {{ caseNameByResultId?.[r.resultId] ?? caseName ?? '用例' }}
            </span>
            <span class="rs-badge rs-exec" :class="r.executionStatus">{{ execLabel(r.executionStatus) }}</span>
            <span class="rs-dim">{{ r.deviceName || r.apiName || '—' }}</span>
            <span v-if="r.reviewed" class="reviewed-badge"><i class="fas fa-clipboard-check"></i> 已复核</span>
          </div>
        </div>
      </div>

      <!-- 执行状态改判 -->
      <div class="field-group">
        <label class="field-label">用例执行状态</label>
        <select v-model="executionStatus" class="form-select">
          <option value="">— 不改判 —</option>
          <option value="completed">已完成</option>
          <option value="failed">执行失败</option>
          <option value="stopped">已停止</option>
          <option value="skipped">已跳过</option>
        </select>
      </div>

      <!-- 评估状态改判 -->
      <div class="field-group">
        <label class="field-label">用例评估状态</label>
        <select v-model="evaluationStatus" class="form-select">
          <option value="">— 不改判 —</option>
          <option value="completed">已完成</option>
          <option value="failed">评估失败</option>
        </select>
      </div>

      <!-- 复核备注（必填） -->
      <div class="field-group">
        <label class="field-label">
          复核备注 <span class="required">*</span>
        </label>
        <textarea
          v-model="comment"
          class="form-textarea"
          rows="3"
          placeholder="填写改判依据或复核意见"
        ></textarea>
        <p class="field-hint">状态可人工设置、评估分数默认不改；至少设置一项执行/评估状态</p>
      </div>

      <p v-if="errorText" class="form-error">{{ errorText }}</p>

      <!-- 查看复核历史（单条/批量已有复核时显） -->
      <button
        v-if="hasAnyHistory"
        type="button"
        class="history-link"
        @click="historyOpen = true"
      >
        <i class="fas fa-clock-rotate-left"></i> 查看复核历史{{ singleResult ? `（${singleResult.reviewHistory?.length ?? 0}）` : '' }}
      </button>
    </div>

    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="emit('cancel')">取消</button>
      <button
        type="button"
        class="btn btn-primary"
        :disabled="confirmDisabled || submitting"
        @click="handleConfirm"
      >
        {{ submitting ? '提交中…' : '提交复核' }}
      </button>
    </div>

    <!-- 复核历史抽屉（§3.4；单条弹窗「查看复核历史」link 复用） -->
    <ReviewHistoryDrawer
      v-if="historyOpen"
      :task-id="taskId"
      :task-name="taskName"
      :result-id="singleResult?.resultId"
      :case-name-map="historyCaseNameMap"
      @close="historyOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/tag.css'
import '../../../assets/styles/components/log.css'

/**
 * 人工复核弹窗（19 规范 §3.2/§3.3；单条=results 长度 1 → 单条复核，多条 → 批量复核，共用组件）。
 * 结果摘要 + 改判 UI（执行/评估 Select + 备注必填）+ 说明行 + 已有复核时「查看复核历史」link（开 §3.4 抽屉）。
 * 提交 POST /tasks/results/review（逐条留痕）；成功 toast 后任务详情/统计按复核后判定刷新。
 * AI 采纳入口：preset 预填 AI 判定的评估状态 + 备注（AI 理由），人工确认后提交。
 */
import { computed, ref } from 'vue'
import ReviewHistoryDrawer from './ReviewHistoryDrawer.vue'

export interface ReviewResultMeta {
  resultId: number
  executionStatus?: string
  evaluationStatus?: string
  deviceName?: string | null
  apiName?: string | null
  reviewed?: boolean
  reviewHistory?: Array<Record<string, any>>
}

export interface ReviewHistoryItem {
  id: number
  resultId: number
  fieldName: 'execution_status' | 'evaluation_status'
  oldValue?: string | null
  newValue: string
  comment: string
  createdAt?: string | null
}

interface Props {
  modalId: string
  title?: string
  taskId: string | number
  /** 结果摘要（单条=1 → 单条复核；多条 → 批量复核） */
  results: ReviewResultMeta[]
  /** 单条复核标题用（批量标题按「已选 {n} 条结果」） */
  caseName?: string
  /** 批量模式下每条结果所属用例名（resultId → 用例名；缺省用 caseName） */
  caseNameByResultId?: Record<number, string>
  /** 任务名（历史抽屉标题） */
  taskName?: string
  /** 用例评估状态（结果行评估徽章展示） */
  evaluationStatus?: string | null
  reviewHistory?: ReviewHistoryItem[]
  /** AI 采纳预填（AI 判定的评估状态 + 备注=AI 理由） */
  preset?: { evaluationStatus?: string; comment?: string } | null
}

interface Emits {
  (e: 'confirm', data: { executionStatus?: string; evaluationStatus?: string; comment: string }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '人工复核',
  caseName: '',
  caseNameByResultId: () => ({}),
  taskName: '',
  evaluationStatus: null,
  reviewHistory: () => [],
  preset: null,
})

const emit = defineEmits<Emits>()

const isBatch = computed(() => props.results.length > 1)
const singleResult = computed(() => (isBatch.value ? null : props.results[0] ?? null))

const executionStatus = ref('')
const evaluationStatus = ref('')
const comment = ref('')
const errorText = ref('')
const submitting = ref(false)
const historyOpen = ref(false)

// AI 采纳预填：preset 变化时填充评估状态 + 备注（弹窗每次打开以最新 preset 为准）
const appliedPreset = ref<{ evaluationStatus?: string; comment?: string } | null>(null)
if (props.preset && props.preset !== appliedPreset.value) {
  appliedPreset.value = props.preset
  evaluationStatus.value = props.preset.evaluationStatus ?? ''
  comment.value = props.preset.comment ?? ''
}

const summaryEvaluation = computed(() => props.evaluationStatus || singleResult.value?.executionStatus || null)
const hasAnyHistory = computed(() => {
  if (props.results.some((r) => r.reviewed || (r.reviewHistory?.length ?? 0) > 0)) return true
  return props.reviewHistory.length > 0
})

/** 单条已有复核时「查看复核历史」抽屉的用例名映射（历史行 testCaseId → 当前用例名） */
const historyCaseNameMap = computed(() => {
  if (!props.caseName) return undefined
  const map: Record<string, string> = {}
  for (const r of props.results) {
    for (const h of r.reviewHistory ?? []) {
      if (h.testCaseId) map[String(h.testCaseId)] = props.caseName
    }
  }
  return Object.keys(map).length > 0 ? map : undefined
})

const confirmDisabled = computed(() => !comment.value.trim() || submitting.value)

function execLabel(status?: string | null): string {
  switch (status) {
    case 'completed': return '执行完成'
    case 'failed': return '执行失败'
    case 'stopped': return '已停止'
    case 'skipped': return '已跳过'
    case 'running': return '执行中'
    case 'pending': return '待执行'
    default: return status || '—'
  }
}

function evalLabel(status?: string | null): string {
  switch (status) {
    case 'completed': return '评估完成'
    case 'failed': return '评估失败'
    case 'pending': return '待评估'
    case 'evaluating': return '评估中'
    default: return status || '—'
  }
}

function handleConfirm() {
  if (!comment.value.trim()) {
    errorText.value = '复核备注必填'
    return
  }
  if (!executionStatus.value && !evaluationStatus.value) {
    errorText.value = '执行状态/评估状态至少设置一项'
    return
  }
  submitting.value = true
  emit('confirm', {
    executionStatus: executionStatus.value || undefined,
    evaluationStatus: evaluationStatus.value || undefined,
    comment: comment.value.trim(),
  })
}
</script>

<style scoped>
.modal-body {
  padding: 20px 24px 4px;
}
.review-tip {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-secondary, var(--color-slate-400));
}
.review-summary {
  margin-bottom: 14px;
}
.review-summary-list {
  max-height: 176px;
  overflow-y: auto;
  border: 1px solid var(--border-color, var(--color-slate-200));
  border-radius: var(--radius-control);
  padding: 8px 10px;
}
.review-summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  padding: 2px 0;
}
.review-summary-row + .review-summary-row {
  margin-top: 2px;
}
.rs-index {
  font-family: var(--font-mono, monospace);
  color: var(--text-secondary, var(--color-slate-400));
}
.rs-name {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  color: var(--foreground, var(--color-slate-800));
}
.rs-dim {
  color: var(--text-secondary, var(--color-slate-500));
}
.rs-badge {
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  font-size: 11px;
}
.rs-exec.completed { background: var(--color-emerald-100); color: var(--color-emerald-600); }
.rs-exec.failed { background: var(--color-red-100); color: var(--color-red-600); }
.rs-exec.stopped { background: var(--color-gray-100); color: var(--color-gray-500); }
.rs-exec.skipped { background: var(--color-gray-100); color: var(--color-gray-500); }
.rs-eval.completed { background: var(--color-blue-100); color: var(--color-blue-600); }
.rs-eval.failed { background: var(--color-red-100); color: var(--color-red-600); }
.reviewed-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  background: var(--color-slate-100);
  color: var(--color-slate-600);
  font-size: 11px;
}
.field-group {
  margin-bottom: 14px;
}
.field-label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 500;
  color: var(--foreground);
}
.required {
  color: var(--destructive);
}
.form-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--color-gray-300);
  border-radius: var(--radius-control);
  font-size: 14px;
  background: var(--background);
  color: var(--foreground);
}
.form-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--color-gray-300);
  border-radius: var(--radius-tag);
  font-size: 14px;
  box-sizing: border-box;
  resize: vertical;
  background: var(--background);
  color: var(--foreground);
}
.field-hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary, var(--color-slate-500));
}
.form-error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--destructive);
}
.history-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: none;
  background: none;
  font-size: 12px;
  color: var(--text-secondary, var(--color-slate-500));
  text-decoration: underline;
  cursor: pointer;
  margin-top: 4px;
}
.history-link:hover {
  color: var(--primary, var(--primary-color));
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
  padding: 16px 24px;
}
.btn {
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-control);
  font-size: 14px;
  cursor: pointer;
}
.btn-secondary {
  background: var(--muted);
  color: var(--foreground);
}
.btn-primary {
  background: var(--primary, var(--primary-color));
  color: var(--background);
}
.btn:disabled {
  background: var(--color-gray-300);
  cursor: not-allowed;
}
</style>
