<template>
  <div class="import-export-modal">
    <div v-if="mode === 'import'" class="import-mode">
      <!-- 容器（BasicModal）已渲染标题时不重复展示；独立使用时保留标题 -->
      <h3 v-if="!modalId">{{ title || '导入数据' }}</h3>

      <form @submit.prevent="handleImport">
        <div class="file-upload-section">
          <label class="file-upload-label">
            <input
              type="file"
              :accept="importAcceptedTypes"
              @change="handleFileSelect"
              ref="fileInput"
            >
            <div class="file-upload-area">
              <i class="fas fa-upload"></i>
              <p v-if="!selectedFile">点击或拖拽文件到此处上传</p>
              <p v-else class="selected-file-name">{{ selectedFile.name }}</p>
              <p class="file-hint">支持格式：{{ importFormatHint }}</p>
            </div>
          </label>
          <p v-if="importHint" class="import-hint">{{ importHint }}</p>
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

        <!-- 预览区：只有真实解析出的行才展示，禁止示例数据（INT-1628） -->
        <div class="preview-section" v-if="showPreview && (previewData.length > 0 || previewError || previewUnsupported)">
          <h4>数据预览</h4>
          <div class="preview-table-container" v-if="previewData.length > 0">
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
            <p class="preview-hint">仅显示前{{ previewData.length }}条数据{{ props.totalItems ? `，共${props.totalItems}条` : '' }}</p>
          </div>
          <p v-else-if="previewError" class="preview-message">{{ previewError }}</p>
          <p v-else class="preview-message">该文件格式不支持本地预览，导入时由服务端解析全部数据。</p>
        </div>

        <!-- 导入结果区：计数 + 逐行错误 + 状态口径说明（INT-1628） -->
        <div class="import-result" v-if="importResult">
          <h4>导入结果</h4>
          <p class="import-result-summary">
            成功导入 {{ importResult.importedCount }} 个，更新 {{ importResult.updatedCount }} 个，跳过 {{ importResult.skippedCount }} 个
          </p>
          <p class="import-result-note">{{ resultNote }}</p>
          <ul class="import-result-errors" v-if="importResult.errors.length > 0">
            <li v-for="(item, index) in importResult.errors" :key="index">{{ item }}</li>
          </ul>
        </div>

        <div class="export-error" role="alert" v-if="submitError">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ submitError }}</span>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="$emit('close')" :disabled="submitting">
            取消
          </button>
          <button
            v-if="importResult"
            type="button"
            class="btn-primary"
            @click="finishImport"
          >
            完成
          </button>
          <button
            v-else
            type="submit"
            class="btn-primary"
            :disabled="!selectedFile || submitting"
          >
            {{ submitting ? '导入中…' : '开始导入' }}
          </button>
        </div>
      </form>
    </div>

    <div v-else-if="mode === 'export'" class="export-mode">
      <h3 v-if="!modalId">{{ title || '导出数据' }}</h3>

      <form @submit.prevent="handleExport">
        <div class="form-group">
          <label for="export-format">导出格式</label>
          <select id="export-format" v-model="exportConfig.format" required>
            <option
              v-for="format in supportedFormats"
              :key="format"
              :value="format"
            >
              {{ formatLabel(format) }}
            </option>
          </select>
        </div>

        <div class="form-group" v-if="hasExportRange">
          <label>导出范围</label>
          <div class="radio-group">
            <div class="radio-item" v-for="range in exportRangeOptions" :key="range.value">
              <input
                :id="`range-${range.value}`"
                type="radio"
                v-model="exportConfig.range"
                :value="range.value"
                :disabled="range.disabled"
              >
              <label :for="`range-${range.value}`" :class="{ 'option-disabled': range.disabled }">{{ range.label }}</label>
              <span class="range-hint" v-if="range.hint">{{ range.hint }}</span>
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

        <div class="export-error" role="alert" v-if="submitError">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ submitError }}</span>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn-secondary" @click="$emit('close')" :disabled="submitting">
            取消
          </button>
          <button type="submit" class="btn-primary" :disabled="submitting">
            {{ submitting ? '导出中…' : '开始导出' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import '../../../assets/styles/test-common.css'
import '../../../assets/styles/components/common.css'
import '../../../assets/styles/components/button.css'
import '../../../assets/styles/components/form.css'
import '../../../assets/styles/components/modal.css'
import '../../../assets/styles/components/table.css'
import '../../../assets/styles/components/log.css'

import { useImportExportModal } from './ImportExportModal'

const props = defineProps({
  modalId: { type: String, default: '' },
  mode: { type: String, default: 'import', validator: (value) => ['import', 'export'].includes(value) },
  title: { type: String, default: '' },
  supportedFormats: { type: Array, default: () => ['excel', 'json'] },
  acceptedFileTypes: { type: String, default: '' },
  importOptions: { type: Array, default: () => [] },
  exportFields: { type: Array, default: () => [] },
  advancedOptions: { type: Array, default: () => [] },
  showPreview: { type: Boolean, default: true },
  totalItems: { type: Number, default: 0 },
  exportRanges: { type: Array, default: () => [] },
  formatLabels: { type: Object, default: () => ({}) },
  importHint: { type: String, default: '' },
  resultNote: { type: String, default: '' },
  allowedImportExtensions: { type: Array, default: () => [] },
  importAction: { type: Function, default: undefined },
  exportAction: { type: Function, default: undefined },
  onImported: { type: Function, default: undefined }
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
  previewError,
  previewUnsupported,
  submitting,
  submitError,
  importResult,
  exportRangeOptions,
  importAcceptedTypes,
  importFormatHint,
  resultNote,
  formatLabel,
  hasImportOptions,
  hasExportRange,
  hasExportFields,
  hasAdvancedOptions,
  handleFileSelect,
  handleImport,
  handleExport,
  finishImport
} = useImportExportModal(props, emit)
</script>

<style scoped>
@import './ImportExportModal.css';
</style>
