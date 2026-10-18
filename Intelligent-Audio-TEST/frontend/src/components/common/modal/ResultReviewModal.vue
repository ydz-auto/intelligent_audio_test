<template>
  <div class="result-review-modal">
    <div class="modal-body">
      <p class="review-tip">
        对 {{ results.length }} 条结果进行人工复核（逐条留痕，历史不覆盖）。
      </p>

      <!-- 执行状态改判 -->
      <div class="field-group">
        <label class="field-label">执行状态改判（可选）</label>
        <select v-model="executionStatus" class="form-select">
          <option value="">— 不改判 —</option>
          <option value="completed">已完成 (completed)</option>
          <option value="failed">失败 (failed)</option>
          <option value="stopped">已停止 (stopped)</option>
          <option value="skipped">已跳过 (skipped)</option>
        </select>
      </div>

      <!-- 评估状态改判 -->
      <div class="field-group">
        <label class="field-label">评估状态改判（可选）</label>
        <select v-model="evaluationStatus" class="form-select">
          <option value="">— 不改判 —</option>
          <option value="completed">已完成 (completed)</option>
          <option value="failed">失败 (failed)</option>
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
          placeholder="填写复核意见（必填）"
        ></textarea>
      </div>

      <p v-if="errorText" class="form-error">{{ errorText }}</p>

      <!-- 复核历史（单条复核时展示历史不覆盖） -->
      <div v-if="reviewHistory.length" class="history-block">
        <p class="history-title">复核历史（多次复核追加，不覆盖）</p>
        <div v-for="(item, idx) in reviewHistory" :key="idx" class="history-item">
          <span class="history-field">{{ fieldLabel(item.fieldName) }}</span>
          <span class="history-values">
            {{ item.oldValue ?? '—' }} → {{ item.newValue }}
          </span>
          <span class="history-comment">{{ item.comment }}</span>
        </div>
      </div>
    </div>

    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="emit('cancel')">取消</button>
      <button
        type="button"
        class="btn btn-primary"
        :disabled="confirmDisabled"
        @click="handleConfirm"
      >
        提交复核
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * INT-340：测试结果人工复核模态（RESULT_REVIEW）。
 *
 * 终态任务单条/批量改判执行状态（completed/failed/stopped/skipped）与
 * 评估状态（completed/failed），复核备注必填；确认载荷
 * { executionStatus?, evaluationStatus?, comment }。
 *
 * 批量复核：多选结果统一改判 + 逐条留痕（后端按 result_ids 循环留痕）。
 */
import { computed, ref } from 'vue'

export interface ReviewResultMeta {
  resultId: number
  executionStatus?: string
  evaluationStatus?: string
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
  results: ReviewResultMeta[]
  reviewHistory?: ReviewHistoryItem[]
}

interface Emits {
  (e: 'confirm', data: { executionStatus?: string; evaluationStatus?: string; comment: string }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '人工复核',
  reviewHistory: () => [],
})

const emit = defineEmits<Emits>()

const executionStatus = ref('')
const evaluationStatus = ref('')
const comment = ref('')
const errorText = ref('')

const confirmDisabled = computed(() => !comment.value.trim())

const fieldLabel = (field: string) => (field === 'execution_status' ? '执行状态' : '评估状态')

function handleConfirm() {
  if (!comment.value.trim()) {
    errorText.value = '复核备注必填'
    return
  }
  if (!executionStatus.value && !evaluationStatus.value) {
    errorText.value = '执行状态/评估状态至少设置一项'
    return
  }
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
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--color-gray-400);
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
.form-error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--destructive);
}
.history-block {
  margin-top: 10px;
  padding: 10px 12px;
  background: color-mix(in srgb, var(--muted) 30%, transparent);
  border-radius: var(--radius-tag);
}
.history-title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-gray-400);
}
.history-item {
  font-size: 12px;
  color: var(--color-gray-400);
  margin-bottom: 4px;
}
.history-field {
  font-weight: 500;
}
.history-values {
  margin: 0 6px;
}
.history-comment {
  color: var(--color-gray-400);
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
  background: var(--secondary);
  color: var(--background);
}
.btn:disabled {
  background: var(--color-gray-300);
  cursor: not-allowed;
}
</style>
