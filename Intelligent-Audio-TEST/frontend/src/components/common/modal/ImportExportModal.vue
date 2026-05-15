<template>
  <div class="import-export-modal">
    <div v-if="mode === 'import'" class="import-mode">
      <h3>{{ title || '导入数据' }}</h3>
      
      <form @submit.prevent="handleImport">
        <div class="file-upload-section">
          <label class="file-upload-label">
            <input 
              type="file" 
              :accept="acceptedFileTypes"
              @change="handleFileSelect"
              ref="fileInput"
            >
            <div class="file-upload-area">
              <i class="fas fa-upload"></i>
              <p v-if="!selectedFile">点击或拖拽文件到此处上传</p>
              <p v-else class="selected-file-name">{{ selectedFile.name }}</p>
              <p class="file-hint">支持格式：{{ supportedFormats.join(', ') }}</p>
            </div>
          </label>
        </div>
        
        <div class="import-options" v-if="hasImportOptions">
          <h4>导入选项</h4>
          <div class="options-grid">
            <div class="option-item" v-for="option in importOptions" :key="option.key">
              <input 
                :id="`option-${option.key}`"
                :type="option.type === 'boolean' ? 'checkbox' : 'radio'"
                v-model="importConfig[option.key]"
                :value="option.value || true"
                :name="option.type === 'radio' ? option.key : undefined"
              >
              <label :for="`option-${option.key}`">{{ option.label }}</label>
              <p class="option-hint" v-if="option.hint">{{ option.hint }}</p>
            </div>
          </div>
        </div>
        
        <div class="preview-section" v-if="showPreview && previewData.length > 0">
          <h4>数据预览</h4>
          <div class="preview-table-container">
            <table>
              <thead>
                <tr>
                  <th v-for="column in previewColumns" :key="column">{{ column }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in previewData" :key="index">
                  <td v-for="column in previewColumns" :key="column">
                    {{ row[column] || '-' }}
                  </td>
                </tr>
              </tbody>
            </table>
            <p class="preview-hint">仅显示前{{ previewData.length }}条数据，共{{ props.totalItems || previewData.length }}条</p>
          </div>
        </div>
        
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="$emit('close')">
            取消
          </button>
          <button 
            type="submit" 
            class="btn-primary"
            :disabled="!selectedFile"
          >
            开始导入
          </button>
        </div>
      </form>
    </div>
    
    <div v-else-if="mode === 'export'" class="export-mode">
      <h3>{{ title || '导出数据' }}</h3>
      
      <form @submit.prevent="handleExport">
        <div class="form-group">
          <label for="export-format">导出格式</label>
          <select id="export-format" v-model="exportConfig.format" required>
            <option 
              v-for="format in supportedFormats" 
              :key="format" 
              :value="format"
            >
              {{ format.toUpperCase() }}
            </option>
          </select>
        </div>
        
        <div class="form-group" v-if="hasExportRange">
          <label>导出范围</label>
          <div class="radio-group">
            <div class="radio-item">
              <input 
                id="range-all" 
                type="radio" 
                v-model="exportConfig.range" 
                value="all"
              >
              <label for="range-all">全部数据</label>
            </div>
            <div class="radio-item">
              <input 
                id="range-selected" 
                type="radio" 
                v-model="exportConfig.range" 
                value="selected"
              >
              <label for="range-selected">选中数据</label>
            </div>
            <div class="radio-item">
              <input 
                id="range-filtered" 
                type="radio" 
                v-model="exportConfig.range" 
                value="filtered"
              >
              <label for="range-filtered">筛选后数据</label>
            </div>
          </div>
        </div>
        
        <div class="form-group" v-if="hasExportFields">
          <label>选择导出字段</label>
          <div class="fields-grid">
            <div 
              v-for="field in exportFields" 
              :key="field.key" 
              class="checkbox-item"
            >
              <input 
                :id="`field-${field.key}`" 
                type="checkbox" 
                v-model="selectedFields"
                :value="field.key"
                :checked="field.defaultChecked"
              >
              <label :for="`field-${field.key}`">{{ field.label }}</label>
            </div>
          </div>
        </div>
        
        <div class="advanced-options" v-if="hasAdvancedOptions">
          <h4>高级选项</h4>
          <div class="options-grid">
            <div class="option-item" v-for="option in advancedOptions" :key="option.key">
              <div v-if="option.type === 'boolean'">
                <input 
                  :id="`adv-option-${option.key}`"
                  type="checkbox"
                  v-model="exportConfig[option.key]"
                  :value="option.value || true"
                >
                <label :for="`adv-option-${option.key}`">{{ option.label }}</label>
              </div>
              <div v-else-if="option.type === 'select'">
                <label :for="`adv-option-${option.key}`">{{ option.label }}</label>
                <select 
                  :id="`adv-option-${option.key}`"
                  v-model="exportConfig[option.key]"
                >
                  <option 
                    v-for="(value, index) in option.options || []" 
                    :key="index"
                    :value="value.value"
                  >{{ value.label }}</option>
                </select>
              </div>
              <div v-else>
                <input 
                  :id="`adv-option-${option.key}`"
                  type="text"
                  v-model="exportConfig[option.key]"
                >
                <label :for="`adv-option-${option.key}`">{{ option.label }}</label>
              </div>
            </div>
          </div>
        </div>
        
        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="$emit('close')">
            取消
          </button>
          <button type="submit" class="btn-primary">
            开始导出
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const props = defineProps({
  modalId: { type: String, default: '' },
  mode: { type: String, default: 'import', validator: (value) => ['import', 'export'].includes(value) },
  title: { type: String, default: '' },
  supportedFormats: { type: Array, default: () => ['excel', 'json'] },
  acceptedFileTypes: { type: String, default: '.xlsx, .xls, .json' },
  importOptions: { type: Array, default: () => [] },
  exportFields: { type: Array, default: () => [] },
  advancedOptions: { type: Array, default: () => [] },
  showPreview: { type: Boolean, default: true },
  totalItems: { type: Number, default: 0 }
})

const emit = defineEmits(['close', 'confirm', 'cancel', 'update:props'])

const fileInput = ref(null)
const selectedFile = ref(null)

const importConfig = ref({
  format: props.supportedFormats[0],
  ...props.importOptions.reduce((acc, option) => {
    acc[option.key] = option.defaultValue || false
    return acc
  }, {})
})

const exportConfig = ref({
  format: props.supportedFormats[0],
  range: 'all',
  ...props.advancedOptions.reduce((acc, option) => {
    acc[option.key] = option.defaultValue || false
    return acc
  }, {})
})

const selectedFields = ref(
  props.exportFields.filter(field => field.defaultChecked).map(field => field.key)
)

const previewData = ref([])
const previewColumns = ref([])

const hasImportOptions = computed(() => props.importOptions.length > 0)
const hasExportRange = computed(() => true)
const hasExportFields = computed(() => props.exportFields.length > 0)
const hasAdvancedOptions = computed(() => props.advancedOptions.length > 0)

const handleFileSelect = (event) => {
  const file = event.target.files[0]
  if (file) {
    selectedFile.value = file
    if (props.showPreview) {
      generatePreview(file)
    }
  }
}

const generatePreview = (file) => {
  previewData.value = [
    { id: 1, name: '示例数据1', status: 'active' },
    { id: 2, name: '示例数据2', status: 'inactive' },
    { id: 3, name: '示例数据3', status: 'active' }
  ]
  previewColumns.value = Object.keys(previewData.value[0] || {})
}

const handleImport = () => {
  if (!selectedFile.value) return
  
  const importData = {
    mode: 'import',
    file: selectedFile.value,
    config: importConfig.value,
    previewData: previewData.value
  }
  
  emit('confirm', importData)
}

const handleExport = () => {
  const exportData = {
    mode: 'export',
    config: { ...exportConfig.value, fields: selectedFields.value }
  }
  
  emit('confirm', exportData)
}

onMounted(() => {
  if (props.exportFields.length > 0 && selectedFields.value.length === 0) {
    selectedFields.value = props.exportFields.map(field => field.key)
  }
})
</script>

<style scoped>
.import-export-modal {
}

h3 {
  margin: 0 0 20px 0;
  font-size: 18px;
  font-weight: 600;
  color: #334155;
}

h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
  color: #334155;
}

input, select {
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s ease;
}

input:focus, select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.file-upload-section {
  margin-bottom: 24px;
}

.file-upload-label {
  display: block;
  cursor: pointer;
}

.file-upload-area {
  border: 2px dashed #cbd5e1;
  border-radius: 8px;
  padding: 40px 20px;
  text-align: center;
  transition: all 0.2s ease;
  background-color: #f8fafc;
}

.file-upload-area:hover {
  border-color: #3b82f6;
  background-color: #eff6ff;
}

.file-upload-area i {
  font-size: 32px;
  color: #94a3b8;
  margin-bottom: 12px;
}

.file-upload-area p {
  margin: 0;
  color: #64748b;
  font-size: 14px;
}

.selected-file-name {
  font-weight: 600;
  color: #334155;
  margin-bottom: 8px !important;
}

.file-hint {
  font-size: 12px !important;
  color: #94a3b8;
}

.import-options {
  margin-bottom: 24px;
  padding: 16px;
  background-color: #f8fafc;
  border-radius: 8px;
}

.options-grid {
  display: grid;
  gap: 12px;
}

.option-item {
  display: flex;
  align-items: center;
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
  margin: 4px 0 0 24px !important;
  font-size: 12px;
  color: #94a3b8;
}

.preview-section {
  margin-bottom: 24px;
  padding: 16px;
  background-color: #f8fafc;
  border-radius: 8px;
}

.preview-table-container {
  overflow-x: auto;
  background-color: white;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.preview-table-container table {
  width: 100%;
  border-collapse: collapse;
}

.preview-table-container th,
.preview-table-container td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid #e2e8f0;
  font-size: 13px;
}

.preview-table-container th {
  background-color: #f1f5f9;
  font-weight: 600;
  color: #334155;
  white-space: nowrap;
}

.preview-table-container td {
  color: #475569;
}

.preview-hint {
  margin: 8px 0 0 0 !important;
  font-size: 12px;
  color: #94a3b8;
  text-align: right;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.radio-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.radio-item input {
  margin: 0;
}

.radio-item label {
  margin: 0;
  font-size: 14px;
  color: #334155;
}

.fields-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  max-height: 200px;
  overflow-y: auto;
  padding: 8px;
  background-color: white;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.checkbox-item input {
  margin: 0;
}

.checkbox-item label {
  margin: 0;
  font-size: 14px;
  color: #334155;
}

.advanced-options {
  margin-bottom: 24px;
  padding: 16px;
  background-color: #f8fafc;
  border-radius: 8px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #e2e8f0;
}

.btn-primary {
  padding: 10px 24px;
  background-color: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  background-color: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 24px;
  background-color: white;
  color: #64748b;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-secondary:hover {
  background-color: #f1f5f9;
  color: #475569;
}

@media (max-width: 768px) {
  .fields-grid {
    grid-template-columns: 1fr;
  }
  
  .preview-table-container th,
  .preview-table-container td {
    padding: 6px 8px;
    font-size: 12px;
  }
}
</style>
