<template>
  <div class="reevaluate-select">
    <p class="reevaluate-title">{{ content }}</p>
    <div class="reevaluate-options">
      <div 
        class="reevaluate-option" 
        :class="{ active: selectedType === 'all' }"
        @click="selectedType = 'all'"
      >
        <div class="option-radio">
          <div class="radio-circle"></div>
        </div>
        <div class="option-content">
          <span class="option-title">重新评估全部用例</span>
          <span class="option-desc">对该任务下所有执行成功的用例进行重新评估</span>
        </div>
      </div>
      <div 
        class="reevaluate-option" 
        :class="{ active: selectedType === 'failed' }"
        @click="selectedType = 'failed'"
      >
        <div class="option-radio">
          <div class="radio-circle"></div>
        </div>
        <div class="option-content">
          <span class="option-title">仅重新评估失败用例</span>
          <span class="option-desc">仅对评估结果为失败的用例进行重新评估</span>
        </div>
      </div>
    </div>
    <div class="reevaluate-checkbox">
      <label class="checkbox-label">
        <input 
          type="checkbox" 
          v-model="reextractDeviceOutput" 
          class="checkbox-input"
        />
        <span class="option-title">重新提取设备输出（从存档日志）</span>
      </label>
      <span class="checkbox-desc">从文件资源管理器中的存档日志重新提取设备输出数据</span>
    </div>
    <div class="reevaluate-actions">
      <button class="btn btn-secondary" @click="handleCancel">
        取消
      </button>
      <button 
        class="btn btn-primary" 
        :disabled="!selectedType" 
        @click="handleConfirm"
      >
        确认
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  modalId: { type: String, required: true },
  content: { type: String, default: '请选择重新评估类型' }
})

const emit = defineEmits(['close', 'confirm'])

const selectedType = ref(null)
const reextractDeviceOutput = ref(false)

const handleConfirm = () => {
  if (selectedType.value) {
    emit('confirm', { 
      reevaluateType: selectedType.value,
      reextractDeviceOutput: reextractDeviceOutput.value
    })
  }
}

const handleCancel = () => {
  emit('close')
}
</script>

<style scoped>
.reevaluate-select {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.reevaluate-title {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
  color: #333;
  text-align: center;
}

.reevaluate-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.reevaluate-option {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px;
  border: 2px solid #e5e7eb;
  border-radius: 10px;
  background-color: #fff;
  cursor: pointer;
  transition: all 0.2s ease;
}

.reevaluate-option:hover {
  border-color: #1677ff;
  background-color: #f8fbff;
}

.reevaluate-option.active {
  border-color: #1677ff;
  background-color: #e6f0ff;
}

.option-radio {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  margin-top: 2px;
}

.radio-circle {
  width: 20px;
  height: 20px;
  border: 2px solid #d1d5db;
  border-radius: 50%;
  transition: all 0.2s ease;
}

.reevaluate-option:hover .radio-circle {
  border-color: #1677ff;
}

.reevaluate-option.active .radio-circle {
  border-color: #1677ff;
  background-color: #1677ff;
  box-shadow: inset 0 0 0 3px #fff;
}

.option-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.option-title {
  font-size: 15px;
  font-weight: 500;
  color: #374151;
}

.reevaluate-option.active .option-title {
  color: #1677ff;
}

.option-desc {
  font-size: 13px;
  color: #9ca3af;
}

.reevaluate-option:hover .option-desc {
  color: #6b7280;
}

.reevaluate-option.active .option-desc {
  color: #6b7280;
}

.reevaluate-checkbox {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background-color: #f9fafb;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.checkbox-input {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: #1677ff;
}

.checkbox-text {
  font-size: 14px;
  font-weight: 500;
  color: #374151;
}

.checkbox-desc {
  font-size: 12px;
  color: #9ca3af;
  margin-left: 28px;
}

.reevaluate-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}
</style>
