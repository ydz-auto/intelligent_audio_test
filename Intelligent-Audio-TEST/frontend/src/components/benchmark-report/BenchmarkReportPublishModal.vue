<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal benchmark-report-modal">
        <div class="modal-header">
          <h3 class="modal-title">发布 Benchmark 报告</h3>
          <button class="modal-close" @click="handleClose"><i class="fas fa-times"></i></button>
        </div>
        <div class="modal-scroll-container">
          <div class="modal-body">
            <div class="form-group">
              <label class="form-label">报告名称 <span class="required">*</span></label>
              <input v-model="form.name" class="form-input" placeholder="例如：LibriSpeech 语音识别基准报告" maxlength="255" :disabled="submitting" />
            </div>

            <div class="form-group">
              <label class="form-label">说明</label>
              <textarea v-model="form.description" class="form-textarea" rows="2" placeholder="报告说明（可选，随快照冻结）" :disabled="submitting"></textarea>
            </div>

            <div class="form-group">
              <label class="form-label">Benchmark 测试集标识</label>
              <input
                v-model="form.suite"
                class="form-input"
                placeholder="例如：librispeech-test-clean（可选，随快照冻结）"
                maxlength="128"
                :disabled="submitting"
              />
            </div>

            <div class="form-group">
              <label class="form-label">Benchmark 被测类别</label>
              <select v-model="form.category" class="form-select" :disabled="submitting">
                <option value="">不指定（全量）</option>
                <option v-for="(label, value) in BenchmarkCategoryLabels" :key="value" :value="value">
                  {{ label }}
                </option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label">数据来源</label>
              <select v-model="form.source" class="form-select" :disabled="submitting">
                <option value="">不指定（双轨全量）</option>
                <option :value="BenchmarkReportSource.PLATFORM_TEST">{{ BenchmarkReportSourceLabels[BenchmarkReportSource.PLATFORM_TEST] }}</option>
                <option :value="BenchmarkReportSource.EXTERNAL_IMPORT">{{ BenchmarkReportSourceLabels[BenchmarkReportSource.EXTERNAL_IMPORT] }}</option>
              </select>
              <div class="form-hint">发布时聚合当前排行快照定格，不随后续重算漂移</div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="handleClose" :disabled="submitting">取消</button>
          <button class="btn btn-primary" :disabled="!canSubmit || submitting" @click="handleConfirm">
            <i class="fas fa-paper-plane"></i> {{ submitting ? '发布中...' : '发布' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { BenchmarkCategoryLabels } from '../../domain/enums'
import {
  BenchmarkReportSource,
  BenchmarkReportSourceLabels,
} from '../../domain/model/benchmarkReport'

const props = defineProps<{
  submitting?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'confirm', payload: {
    name: string
    description?: string
    suite?: string
    category?: string
    source?: string
  }): void
}>()

const form = ref<{
  name: string
  description: string
  suite: string
  category: string
  source: string
}>({
  name: '',
  description: '',
  suite: '',
  category: '',
  source: '',
})

const canSubmit = computed(
  () => form.value.name.trim().length > 0 && !props.submitting
)

function handleClose() {
  emit('close')
}

function handleConfirm() {
  if (!canSubmit.value) return
  emit('confirm', {
    name: form.value.name.trim(),
    description: form.value.description.trim() || undefined,
    suite: form.value.suite.trim() || undefined,
    category: form.value.category || undefined,
    source: form.value.source || undefined,
  })
}
</script>

<style scoped>
/* 自包含弹窗样式：不能依赖其他组件的 scoped 样式；opacity/visibility 显式声明，
   规避全局 .modal-overlay{visibility:hidden;opacity:0}（test-case-manager.css，仅 .active 才可见）串扰 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background-color: color-mix(in srgb, var(--color-black) 50%, transparent);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: var(--z-index-modal-top);
  overflow: hidden;
  opacity: 1;
  visibility: visible;
}

.modal {
  background-color: var(--background);
  border-radius: var(--radius-control);
  box-shadow: 0 4px 20px color-mix(in srgb, var(--color-black) 15%, transparent);
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transform: none;
}

.benchmark-report-modal {
  width: 520px;
  max-width: 92vw;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--modal-border-color);
  background: linear-gradient(135deg, var(--modal-surface-top) 0%, var(--modal-border-color) 100%);
}

.modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: var(--font-weight-semibold);
  color: var(--modal-title-color);
}

.modal-close {
  background: none;
  border: none;
  font-size: var(--font-size-lg);
  cursor: pointer;
  color: var(--modal-muted);
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  transition: all var(--transition-fast);
}

.modal-close:hover {
  color: var(--modal-title-color);
  background-color: var(--modal-border-color);
}

.modal-scroll-container {
  max-height: calc(90vh - 120px);
  overflow-y: auto;
  flex: 1;
}

.modal-body {
  padding: 20px 24px;
  background-color: var(--background);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  border-top: 1px solid var(--modal-border-color);
  background-color: var(--modal-surface-top);
}

.btn {
  padding: 8px 18px;
  border: none;
  border-radius: var(--radius-tag);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  transition: all var(--transition-fast);
}

.btn-primary {
  background-color: var(--primary);
  color: var(--color-white);
}

.btn-primary:hover {
  background-color: var(--btn-primary-hover-color);
}

.btn-primary:disabled {
  background-color: var(--btn-primary-disabled-bg);
  cursor: not-allowed;
}

.btn-secondary {
  background-color: var(--gray-light);
  color: var(--foreground);
}

.btn-secondary:hover {
  background-color: var(--btn-secondary-hover-bg);
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: var(--font-weight-semibold);
  color: var(--modal-text);
}

.required {
  color: var(--danger-required);
}

.form-select,
.form-input,
.form-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-gray-300);
  border-radius: var(--radius-6);
  font-size: 13px;
  background: var(--background);
  color: var(--modal-text);
  box-sizing: border-box;
}

.form-select:focus,
.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 15%, transparent);
}

.form-hint {
  margin-top: 6px;
  font-size: var(--font-size-xs);
  color: var(--color-gray-400);
}
</style>
