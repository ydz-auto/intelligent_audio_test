<template>
  <div class="upload-file-modal">
    <h3>{{ title || '批量从文件夹导入' }}</h3>
    
    <div class="upload-content">
      <!-- 拖放区域 -->
      <div 
        class="drop-zone"
        :class="{ 'drop-zone-active': isDragActive }"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <div class="drop-zone-content">
          <i class="fas fa-folder-open"></i>
          <h4>{{ dragMessage }}</h4>
          <p class="drop-zone-hint">
            支持格式：{{ supportedFormats.join(', ') }}<br>
            选择包含音频文件的文件夹进行批量导入
          </p>
          <label class="browse-btn">
            <input 
              type="file" 
              ref="folderInput"
              webkitdirectory
              multiple
              @change="handleFolderSelect"
              :disabled="importing"
              accept=".mp3,.wav,.flac,.aac,.m4a,.ogg,.txt,.json,.jsonl,.rttm,.stm"
            >
            选择文件夹
          </label>
        </div>
      </div>
      
      <!-- 文件统计信息 -->
      <div class="file-stats" v-if="selectedFiles.length > 0">
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-label">音频文件数量</span>
            <span class="stat-value">{{ audioFilesCount }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">总大小</span>
            <span class="stat-value">{{ formatFileSize(totalFileSize) }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">文件夹数量</span>
            <span class="stat-value">{{ selectedFolders.length }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">支持的文件格式</span>
            <span class="stat-value">{{ supportedFormats.join(', ') }}</span>
          </div>
        </div>
      </div>
      
      <!-- 文件夹分组设置 -->
      <div class="folder-groups" v-if="selectedFolders.length > 0 && uploadConfig.createTestCase && uploadConfig.groupNameType === 'custom'">
        <h4>文件夹分组设置</h4>
        <div class="folder-group-list">
          <div class="folder-group-item" v-for="folder in selectedFolders" :key="folder">
            <div class="folder-name">{{ folder }}</div>
            <div class="folder-group-input">
              <input 
                type="text" 
                class="form-input" 
                :placeholder="`为文件夹 '${folder}' 设置自定义分组名`"
                :value="folderGroupNames.get(folder)"
                @input="handleFolderGroupInput(folder, $event)"
              >
            </div>
          </div>
        </div>
      </div>
      
      <!-- 上传选项 -->
      <UploadOptions
        v-if="hasUploadOptions"
        v-model="uploadConfig"
        v-model:tags="tags"
        :audio-type-options="audioTypeOptions"
        :playback-device-options="playbackDeviceOptions"
        :device-options="deviceOptions"
        :algorithm-options="algorithmOptions"
        :show-tags-input="true"
      />

      <!-- 标注 Code 选择 -->
      <div class="annotation-code-config" v-if="selectedFiles.length > 0 && referenceParamOptions.length > 0">
        <div class="form-row">
          <label>标注代码：</label>
          <select v-model="annotationCode" class="form-input">
            <option value="">留空则使用 JSON 内 code/name 字段</option>
            <option v-for="opt in referenceParamOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>
      </div>
    </div>
    
    <!-- 按钮区域 -->
    <div class="modal-footer">
      <button 
        type="button" 
        class="btn-secondary"
        @click="handleCancel"
        :disabled="false"
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
        {{ importing ? '导入中...' : '开始上传' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import UploadOptions from '../misc/UploadOptions.vue'
import { useFolderImportModal } from './FolderImportModal'

interface UploadOption {
  key: string
  type: 'boolean' | 'radio' | 'checkbox' | 'select' | 'number' | 'text' | 'dimensions'
  label: string
  defaultValue?: any
  options?: Array<{ value: any; label: string }>
  disabled?: boolean
  min?: number
  max?: number
  step?: number
  placeholder?: string
  hint?: string
}

const props = defineProps<{
  modalId?: string
  title?: string
  uploadOptions?: UploadOption[]
  supportedFormats?: string[]
  deviceOptions?: any[]
  algorithmOptions?: any[]
  playbackDeviceOptions?: any[]
  audioTypeOptions?: any[]
}>()

const emit = defineEmits([
  'close',
  'confirm',
  'cancel',
  'configChange',
  'selectFolder'
])

const {
  folderInput,
  importing,
  isDragActive,
  importProgress,
  selectedFiles,
  tags,
  annotationCode,
  referenceParamOptions,
  uploadConfig,
  audioTypeOptions,
  playbackDeviceOptions,
  algorithmOptions,
  selectedFolders,
  folderGroupNames,
  audioFilesCount,
  dragMessage,
  canImport,
  hasUploadOptions,
  totalFileSize,
  handleDragOver,
  handleDragLeave,
  handleDrop,
  handleFolderSelect,
  handleFolderGroupInput,
  handleImport,
  handleCancel,
  formatFileSize,
} = useFolderImportModal(props, emit)
</script>

<style scoped>
@import './FolderImportModal.css';
</style>
