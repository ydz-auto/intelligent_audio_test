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
          <h4>body_template JSON</h4>
          <span class="section-hint">rounds 内的字段由左侧表单管理，rounds 外的字段（如 model/prompt）可直接在此编辑</span>
          <textarea
            v-model="bodyTemplateJson"
            class="json-edit"
            rows="20"
            @input="parseBodyTemplate"
          ></textarea>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'

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

const headersJson = ref('')
const bodyTemplateJson = ref('')

watch(() => props.modelValue, (newVal) => {
  const val = (newVal && typeof newVal === 'object') ? newVal : {}
  localValue.method = val.method || 'POST'
  localValue.headers = val.headers ? { ...val.headers } : {}
  localValue.body_template = val.body_template ? JSON.parse(JSON.stringify(val.body_template)) : {}
  localValue.timeout = val.timeout || 30000

  headersJson.value = JSON.stringify(localValue.headers, null, 2)
  bodyTemplateJson.value = JSON.stringify(localValue.body_template, null, 2)
}, { immediate: true, deep: true })

function parseHeaders() {
  try {
    localValue.headers = JSON.parse(headersJson.value || '{}')
    handleChange()
  } catch (e) {
  }
}

function parseBodyTemplate() {
  try {
    const parsed = JSON.parse(bodyTemplateJson.value || '{}')
    localValue.body_template = parsed
    handleChange()
  } catch (e) {
    // JSON 解析失败时不做操作，等用户修好
  }
}

function handleChange() {
  emit('update:modelValue', { ...localValue })
  emit('change', { ...localValue })
}
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

.preview-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.json-edit {
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
  min-height: 200px;
  border: 1px solid #334155;
  resize: vertical;
  width: 100%;
  box-sizing: border-box;
  line-height: 1.5;
}
</style>
