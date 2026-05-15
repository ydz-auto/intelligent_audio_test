<template>
  <div class="api-settings-editor">
    <div class="api-settings-grid">
      <div class="api-settings-left">
        <div class="editor-section">
          <h4>请求配置</h4>
          <div class="config-row">
            <div class="config-item">
              <label>请求方法</label>
              <select v-model="localValue.method" @change="handleChange">
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="DELETE">DELETE</option>
                <option value="PATCH">PATCH</option>
              </select>
            </div>
            <div class="config-item">
              <label>超时时间 (ms)</label>
              <input 
                type="number" 
                v-model.number="localValue.timeout" 
                placeholder="如: 30000"
                @input="handleChange"
              />
            </div>
          </div>
          
          <div class="config-row">
            <div class="config-item full-width">
              <label>Headers</label>
              <textarea 
                v-model="headersJson" 
                placeholder='{"Content-Type": "application/json"}'
                rows="2"
                @input="parseHeaders"
              ></textarea>
            </div>
          </div>
        </div>
      </div>
      
      <div class="api-settings-right">
        <div class="editor-section preview-section">
          <h4>JSON预览</h4>
          <pre class="json-preview">{{ previewJson }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({
      method: 'POST',
      headers: {},
      body_template: {},
      timeout: 30000
    })
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const localValue = reactive({
  method: 'POST',
  headers: {},
  body_template: {},
  timeout: 30000
})

const localInputs = ref([])
const headersJson = ref('')

watch(() => props.modelValue, (newVal) => {
  if (newVal && typeof newVal === 'object') {
    localValue.method = newVal.method || 'POST'
    localValue.headers = newVal.headers ? { ...newVal.headers } : {}
    localValue.body_template = newVal.body_template ? { ...newVal.body_template } : {}
    localValue.timeout = newVal.timeout || 30000
    
    headersJson.value = JSON.stringify(localValue.headers, null, 2)
    
    const bodyTemplate = localValue.body_template || {}
    const inputKeys = Object.keys(bodyTemplate)
    if (inputKeys.length > 0) {
      localInputs.value = inputKeys.map(key => ({
        param_code: key,
        param_name: '',
        field_type: 'text',
        required: true,
        help_text: ''
      }))
    } else {
      localInputs.value = []
    }
  }
}, { immediate: true, deep: true })

function parseHeaders() {
  try {
    localValue.headers = JSON.parse(headersJson.value || '{}')
    handleChange()
  } catch (e) {
  }
}

function addInput() {
  if (!localInputs.value) {
    localInputs.value = []
  }
  localInputs.value.push({
    param_code: '',
    param_name: '',
    field_type: 'text',
    required: true,
    help_text: ''
  })
  handleChange()
}

function removeInput(index) {
  const removedInput = localInputs.value[index]
  if (removedInput && removedInput.param_code) {
    delete localValue.body_template[removedInput.param_code]
  }
  localInputs.value.splice(index, 1)
  handleChange()
}

function handleInputChange() {
  syncBodyTemplate()
  handleChange()
}

function syncBodyTemplate() {
  localInputs.value.forEach(input => {
    if (input.param_code && !localValue.body_template[input.param_code]) {
      localValue.body_template[input.param_code] = `{{${input.param_code}}}`
    }
  })
  
  const inputKeys = new Set(localInputs.value.map(i => i.param_code).filter(k => k))
  Object.keys(localValue.body_template).forEach(key => {
    if (!inputKeys.has(key)) {
      delete localValue.body_template[key]
    }
  })
}

function handleChange() {
  emit('update:modelValue', { ...localValue })
  emit('change', { ...localValue })
}

const previewJson = computed(() => {
  return JSON.stringify(localValue, null, 2)
})
</script>

<style scoped>
.api-settings-editor {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  background: #fafafa;
}

.api-settings-grid {
  display: grid;
  grid-template-columns: 1fr 350px;
  gap: 20px;
}

.api-settings-left {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.api-settings-right {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.editor-section {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  flex: 1;
}

.editor-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  flex-shrink: 0;
}

.section-hint {
  margin: 0 0 12px 0;
  font-size: 12px;
  color: #64748b;
}

.config-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.config-row:last-child {
  margin-bottom: 0;
}

.config-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.config-item.full-width {
  flex: 100%;
}

.config-item label {
  font-size: 12px;
  font-weight: 500;
  color: #64748b;
}

.config-item input,
.config-item select,
.config-item textarea {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
  width: 100%;
  box-sizing: border-box;
}

.config-item input:focus,
.config-item select:focus,
.config-item textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.config-item textarea {
  font-family: monospace;
  resize: vertical;
}

.inputs-table {
  display: flex;
  flex-direction: column;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  background: white;
  margin-bottom: 12px;
}

.table-header {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
}

.table-body {
  display: flex;
  flex-direction: column;
  max-height: 300px;
  overflow-y: auto;
}

.input-row {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #f1f5f9;
  align-items: center;
}

.input-row:last-child {
  border-bottom: none;
}

.row-index {
  width: 24px;
  text-align: center;
  font-weight: 600;
  color: #64748b;
  font-size: 12px;
  flex-shrink: 0;
}

.th-index {
  width: 24px;
  text-align: center;
  flex-shrink: 0;
}

.th-key {
  flex: 1;
}

.th-label {
  flex: 1;
}

.th-source {
  width: 80px;
  flex-shrink: 0;
}

.th-required {
  width: 50px;
  text-align: center;
  flex-shrink: 0;
}

.th-desc {
  flex: 1;
}

.th-action {
  width: 40px;
  flex-shrink: 0;
}

.key-input,
.label-input,
.desc-input {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  width: 100%;
  box-sizing: border-box;
}

.key-input {
  flex: 1;
}

.label-input {
  flex: 1;
}

.desc-input {
  flex: 1;
}

.source-select {
  width: 80px;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  flex-shrink: 0;
}

.key-input:focus,
.label-input:focus,
.desc-input:focus,
.source-select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.checkbox-wrapper {
  width: 50px;
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}

.checkbox-wrapper input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.btn-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: #ef4444;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.btn-remove:hover {
  background: #fee2e2;
}

.btn-add {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
  width: fit-content;
}

.btn-add:hover {
  background: #2563eb;
}

.empty-state {
  text-align: center;
  padding: 20px;
  color: #94a3b8;
  background: white;
  border: 1px dashed #e2e8f0;
  border-radius: 8px;
  margin-bottom: 12px;
}

.empty-state i {
  font-size: 32px;
  margin-bottom: 8px;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.preview-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.json-preview {
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 6px;
  font-family: monospace;
  font-size: 12px;
  overflow-x: auto;
  margin: 0;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
</style>
