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
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 13000;
  overflow: hidden;
  opacity: 1;
  visibility: visible;
}

.modal {
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
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
  border-bottom: 1px solid #e9ecef;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
}

.modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #343a40;
}

.modal-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #6c757d;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close:hover {
  color: #343a40;
  background-color: #e9ecef;
}

.modal-scroll-container {
  max-height: calc(90vh - 120px);
  overflow-y: auto;
  flex: 1;
}

.modal-body {
  padding: 20px 24px;
  background-color: #fff;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  border-top: 1px solid #e9ecef;
  background-color: #f8f9fa;
}

.btn {
  padding: 8px 18px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-primary {
  background-color: #ff6a00;
  color: #fff;
}

.btn-primary:hover {
  background-color: #ff8c40;
}

.btn-primary:disabled {
  background-color: #d9d9d9;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: #f0f0f0;
  color: #333;
}

.btn-secondary:hover {
  background-color: #e0e0e0;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
}

.required {
  color: #e53e3e;
}

.form-select,
.form-input,
.form-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  background: #fff;
  color: #1f2937;
  box-sizing: border-box;
}

.form-select:focus,
.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #ff6a00;
  box-shadow: 0 0 0 2px rgba(255, 106, 0, 0.15);
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #9ca3af;
}
</style>
