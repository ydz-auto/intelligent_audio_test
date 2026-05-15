<template>
  <div class="batch-spl-modal">
    <div class="modal-header">
      <h3>{{ title }}</h3>
      <p class="case-count">将为 {{ caseCount }} 个用例设置声压级</p>
    </div>
    
    <div class="modal-body">
      <div class="form-group">
        <label>声压级 (dB) <span class="required">*</span></label>
        <input 
          type="number" 
          v-model.number="splValue" 
          class="form-input" 
          min="0" 
          max="140" 
          step="1"
          placeholder="请输入声压级，例如：65"
        />
        <p class="form-hint">建议值：65 dB</p>
      </div>
    </div>
    
    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
      <button type="button" class="btn btn-primary" @click="handleConfirm" :disabled="!isValid">
        确定
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Props {
  modalId: string
  title?: string
  caseCount?: number
  initialValue?: number
}

interface Emits {
  (e: 'close'): void
  (e: 'confirm', data: { value: number }): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: '批量设置声压级',
  caseCount: 0,
  initialValue: 94
})

const emit = defineEmits<Emits>()

const splValue = ref(props.initialValue)

const isValid = computed(() => {
  return splValue.value >= 0 && splValue.value <= 140
})

function handleConfirm() {
  if (!isValid.value) {
    return
  }
  emit('confirm', {
    value: splValue.value
  })
}

function handleCancel() {
  emit('cancel')
}
</script>

<style scoped>
.batch-spl-modal {
  padding: 20px;
}

.modal-header {
  margin-bottom: 20px;
}

.modal-header h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: #333;
}

.case-count {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.modal-body {
  padding: 10px 0;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #333;
}

.required {
  color: #dc3545;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.form-input:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.form-hint {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: #999;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.btn {
  padding: 8px 20px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
}

.btn-secondary {
  background: #f5f5f5;
  color: #333;
}

.btn-secondary:hover {
  background: #e8e8e8;
}

.btn-primary {
  background: #1677ff;
  color: #fff;
}

.btn-primary:hover {
  background: #4096ff;
}

.btn-primary:disabled {
  background: #ccc;
  cursor: not-allowed;
}
</style>
