<template>
  <div class="reevaluate-select">
    <p class="reevaluate-title">{{ content }}</p>
    <div class="reevaluate-options">

      <div
        class="reevaluate-option"
        :class="{ active: selectedType === TaskStatus.FAILED }"
        @click="selectedType = TaskStatus.FAILED"
      >
        <div class="option-radio">
          <div class="radio-circle"></div>
        </div>
        <div class="option-content">
          <span class="option-title">仅重新评估失败用例</span>
          <span class="option-desc">仅对评估结果为失败的用例进行重新评估</span>
        </div>
      </div>
      <div
        class="reevaluate-option"
        :class="{ active: selectedType === ViewMode.ALL }"
        @click="selectedType = ViewMode.ALL"
      >
        <div class="option-radio">
          <div class="radio-circle"></div>
        </div>
        <div class="option-content">
          <span class="option-title">重新评估全部用例</span>
          <span class="option-desc">对该任务下所有执行成功的用例进行重新评估</span>
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
import { TaskStatus, ViewMode } from '@/domain/enums'

const props = defineProps({
  modalId: { type: String, required: true },
  content: { type: String, default: '请选择重新评估类型' }
})

const emit = defineEmits(['close', 'confirm'])

const selectedType = ref(TaskStatus.FAILED)
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
  color: var(--foreground);
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
  border: 2px solid var(--border);
  border-radius: 10px;
  background-color: var(--background);
  cursor: pointer;
  transition: all 0.2s ease;
}

.reevaluate-option:hover {
  border-color: var(--secondary);
  background-color: var(--color-slate-50);
}

.reevaluate-option.active {
  border-color: var(--secondary);
  background-color: var(--color-blue-50);
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
  border: 2px solid var(--color-gray-300);
  border-radius: 50%;
  transition: all 0.2s ease;
}

.reevaluate-option:hover .radio-circle {
  border-color: var(--secondary);
}

.reevaluate-option.active .radio-circle {
  border-color: var(--secondary);
  background-color: var(--secondary);
  box-shadow: inset 0 0 0 3px var(--background);
}

.option-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.option-title {
  font-size: 15px;
  font-weight: 500;
  color: var(--color-gray-700);
}

.reevaluate-option.active .option-title {
  color: var(--secondary);
}

.option-desc {
  font-size: 13px;
  color: var(--color-gray-400);
}

.reevaluate-option:hover .option-desc {
  color: var(--color-gray-500);
}

.reevaluate-option.active .option-desc {
  color: var(--color-gray-500);
}

.reevaluate-checkbox {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background-color: var(--color-gray-50);
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
  accent-color: var(--secondary);
}

.checkbox-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-gray-700);
}

.checkbox-desc {
  font-size: 12px;
  color: var(--color-gray-400);
  margin-left: 28px;
}

.reevaluate-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
</style>
