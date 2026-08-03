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
import { useImportExportModal } from './ImportExportModal'

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

const {
  fileInput,
  selectedFile,
  importConfig,
  exportConfig,
  selectedFields,
  previewData,
  previewColumns,
  hasImportOptions,
  hasExportRange,
  hasExportFields,
  hasAdvancedOptions,
  handleFileSelect,
  handleImport,
  handleExport
} = useImportExportModal(props, emit)
</script>

<style scoped>
@import './ImportExportModal.css';
</style>
