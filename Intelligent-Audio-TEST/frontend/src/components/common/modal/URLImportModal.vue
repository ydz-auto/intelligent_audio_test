<template>
  <div class="url-import-modal">
    <h3>{{ title || 'URL导入音频' }}</h3>
    
    <div class="import-content">
      <div class="form-group">
        <label :for="fieldIds.url" class="form-label">音频URL</label>
        <input 
          type="url" 
          :id="fieldIds.url"
          class="form-input" 
          placeholder="请输入音频文件URL" 
          v-model="importData.url"
        >
        <small class="form-hint">支持HTTP/HTTPS协议的音频文件</small>
      </div>
      
      <div class="form-group">
        <label :for="fieldIds.tags" class="form-label">标签</label>
        <input 
          type="text" 
          :id="fieldIds.tags"
          class="form-input" 
          placeholder="留空将自动生成；多个标签用逗号分隔" 
          v-model="importData.tags"
        >
        <small class="form-hint">留空将自动生成标签</small>
      </div>
      
      <div class="upload-options" v-if="hasUploadOptions">
        <h4>上传选项</h4>
        <div class="options-grid">
          <div class="option-item" v-for="option in visibleUploadOptions" :key="option.key">
            <template v-if="option.type === 'boolean'">
              <input 
                :id="`upload-option-${option.key}`"
                type="checkbox"
                v-model="uploadConfig[option.key]"
                :value="option.value || true"
              >
              <label :for="`upload-option-${option.key}`">{{ option.label }}</label>
            </template>
            <template v-else-if="option.type === 'radio'">
              <label>{{ option.label }}</label>
              <div class="radio-group">
                <label v-for="opt in option.options" :key="opt.value" class="radio-label">
                  <input 
                    type="radio" 
                    :name="option.key" 
                    :value="opt.value" 
                    v-model="uploadConfig[option.key]"
                  >
                  <span class="radio-text">{{ opt.label }}</span>
                </label>
              </div>
            </template>
            <template v-else-if="option.type === 'select'">
              <label>{{ option.label }}</label>
              <select v-model="uploadConfig[option.key]" class="form-input">
                <option v-for="opt in option.options" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </template>
            <template v-else-if="option.type === 'number'">
              <label>{{ option.label }}</label>
              <input 
                type="number" 
                class="form-input"
                v-model="uploadConfig[option.key]"
                :min="option.min"
                :max="option.max"
                :step="option.step || 1"
              >
            </template>
            <p class="option-hint" v-if="option.hint">{{ option.hint }}</p>
          </div>
        </div>
      </div>
    </div>
    
    <div class="modal-footer">
      <button 
        type="button" 
        class="btn-secondary"
        @click="$emit('close')"
        :disabled="importing"
      >
        取消
      </button>
      <button 
        type="button" 
        class="btn-primary"
        @click="handleImport"
        :disabled="!canImport || importing"
      >
        <span v-if="importing" class="loading-spinner"></span>
        {{ importing ? '导入中...' : '开始导入' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  modalId: { type: String, default: '' },
  title: { type: String, default: 'URL导入音频' },
  uploadOptions: { type: Array, default: () => [] }
})

const emit = defineEmits(['close', 'confirm', 'cancel', 'configChange'])

const importing = ref(false)

const fieldIds = { url: 'url', tags: 'tags' }

const importData = ref({
  url: '',
  tags: ''
})

const uploadConfig = ref({
  ...props.uploadOptions.reduce((acc, option) => {
    acc[option.key] = option.defaultValue || false
    return acc
  }, {})
})

watch(uploadConfig, (newConfig) => {
  emit('configChange', newConfig)
}, { deep: true })

const hasUploadOptions = computed(() => props.uploadOptions.length > 0)

const canImport = computed(() => {
  return importData.value.url.trim() !== '' && 
         importData.value.url.startsWith('http')
})

const visibleUploadOptions = computed(() => {
  const options = []
  let showSubOptions = true
  let showE2EOptions = false
  
  for (const option of props.uploadOptions) {
    if (option.key === 'createTestCase') {
      showSubOptions = uploadConfig.value.createTestCase === true
    }
    
    if (option.key === 'testType') {
      if (showSubOptions) {
        showE2EOptions = uploadConfig.value.testType === 'e2e'
      }
    }
    
    if (!showSubOptions) {
      if (['testType', 'playbackDeviceId', 'defaultSpl'].includes(option.key)) {
        continue
      }
    } else if (option.key === 'testType') {
    } else if (['playbackDeviceId', 'defaultSpl'].includes(option.key)) {
      if (!showE2EOptions) {
        continue
      }
    }
    
    options.push(option)
  }
  
  return options
})

const handleImport = async () => {
  if (!canImport.value) return
  
  importing.value = true
  
  try {
    emit('confirm', {
      data: { ...importData.value },
      config: { ...uploadConfig.value }
    })
  } catch (error) {
    console.error('URL导入失败:', error)
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.url-import-modal {
}

h3 {
  margin: 0 0 20px 0;
  font-size: 18px;
  font-weight: 600;
  color: #334155;
}

.import-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
  color: #374151;
}

.form-input {
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  color: #374151;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.form-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-hint {
  font-size: 12px;
  color: #6b7280;
  margin: 0;
}

.upload-options {
  background-color: #f8fafc;
  padding: 16px;
  border-radius: 8px;
  margin-top: 8px;
}

.upload-options h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.options-grid {
  display: grid;
  gap: 12px;
}

.option-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-item input[type="checkbox"],
.option-item input[type="radio"] {
  margin: 0;
}

.option-item label {
  font-size: 14px;
  color: #334155;
  margin: 0;
}

.option-hint {
  margin: 4px 0 0 0 !important;
  font-size: 12px;
  color: #94a3b8;
}

.radio-group {
  display: flex;
  gap: 16px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.radio-label input[type="radio"] {
  margin: 0;
}

.radio-label .radio-text {
  font-size: 14px;
  color: #334155;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e2e8f0;
}

.btn-primary {
  padding: 10px 20px;
  background-color: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.btn-primary:hover:not(:disabled) {
  background-color: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 20px;
  background-color: white;
  color: #374151;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.btn-secondary:hover:not(:disabled) {
  background-color: #f3f4f6;
}

.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 0.8s linear infinite;
  margin-right: 8px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .radio-group {
    flex-direction: column;
    gap: 8px;
  }
}
</style>
