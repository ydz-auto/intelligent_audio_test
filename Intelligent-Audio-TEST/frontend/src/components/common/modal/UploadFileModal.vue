<template>
  <div class="upload-file-modal">
    <h3>{{ title || '上传文件' }}</h3>
    
    <div class="upload-content">
      <!-- 拖放区域 -->
      <div 
        class="drop-zone"
        :class="{ 'drop-zone-active': isDragging }"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <div class="drop-zone-content">
          <i v-if="selectedFiles.length === 0" class="fas fa-cloud-upload-alt"></i>
          <i v-else class="fas fa-folder-open"></i>
          
          <template v-if="selectedFiles.length === 0">
            <h4>{{ dragMessage }}</h4>
            <p class="drop-zone-hint">
              支持格式：{{ acceptedTypes.join(', ') }}<br>
              选择或拖拽音频文件进行上传
            </p>
            <label class="browse-btn">
              <input 
                type="file" 
                :id="inputId"
                ref="fileInput"
                :accept="acceptedTypes"
                :multiple="multiple"
                @change="handleFileSelect"
              >
              选择文件
            </label>
          </template>
          
          <template v-else>
            <h4>已选择 {{ selectedFiles.length }} 个文件</h4>
            <p class="drop-zone-hint">
              支持格式：{{ acceptedTypes.join(', ') }}
            </p>
            <label class="browse-btn">
              <input 
                type="file" 
                :id="inputId"
                ref="fileInput"
                :accept="acceptedTypes"
                :multiple="multiple"
                @change="handleFileSelect"
              >
              重新选择
            </label>
          </template>
        </div>
      </div>
      
      <!-- 文件统计信息 -->
      <div class="file-stats" v-if="selectedFiles.length > 0 || selectedTxtFiles.length > 0">
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-label">音频文件数量</span>
            <span class="stat-value">{{ audioFilesCount }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">文本文件数量</span>
            <span class="stat-value">{{ selectedTxtFiles.length }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">总大小</span>
            <span class="stat-value">{{ formatFileSize(totalFileSize) }}</span>
          </div>
        </div>
      </div>
      
      <!-- 选中的文本文件列表 -->
      <div class="file-list" v-if="selectedTxtFiles.length > 0">
        <h4>已选择的文本文件</h4>
        <div class="files-container">
          <div class="file-item" v-for="(txtFile, index) in selectedTxtFiles" :key="index">
            <i class="fas fa-file-alt txt-file-icon"></i>
            <div class="file-details">
              <span class="file-name">{{ txtFile.name }}</span>
              <span class="file-size">{{ formatFileSize(txtFile.file.size) }}</span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 音频文件关联信息 -->
      <div class="file-list" v-if="selectedFiles.length > 0">
        <h4>音频文件关联信息</h4>
        <div class="files-container">
          <div class="file-item audio-file-item" v-for="(fileItem, index) in selectedFiles" :key="index">
            <i class="fas fa-file-audio audio-file-icon"></i>
            <div class="file-details">
              <span class="file-name">{{ fileItem.name }}</span>
              <span class="file-size">{{ formatFileSize(fileItem.file.size) }}</span>
              <div class="file-meta" v-if="fileItem.hasTxtFile">
                <span class="meta-tag has-txt">已关联文本文件</span>
                <div class="meta-content" v-if="fileItem.asrText">
                  <div class="meta-label">ASR文本:</div>
                  <div class="meta-value">{{ fileItem.asrText }}</div>
                </div>
                <div class="meta-content" v-if="fileItem.translations && fileItem.translations.length > 0">
                  <div class="meta-label">翻译:</div>
                  <div class="translations-list">
                    <div class="translation-item" v-for="(trans, idx) in fileItem.translations" :key="idx">
                      <span class="direction">{{ trans.direction }}</span>
                      <span class="text">{{ trans.text }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="file-meta" v-else>
                <span class="meta-tag no-txt">未关联文本文件</span>
              </div>
            </div>
          </div>
        </div>
      </div>

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
      
      <!-- 上传选项 -->
      <UploadOptions
        v-if="hasUploadOptions"
        v-model="uploadConfig"
        v-model:tags="tags"
        :audio-type-options="audioTypeOptions"
        :playback-device-options="playbackDeviceOptions"
        :device-options="deviceOptions"
        :algorithm-options="algorithmOptions"
        :show-tags-input="showTagsInput"
      />
    </div>
    
    <div class="modal-footer">
      <button 
        type="button" 
        class="btn-secondary"
        @click="$emit('close')"
        :disabled="uploading"
      >
        取消
      </button>
      <button 
        type="button" 
        class="btn-primary"
        @click="handleUpload"
        :disabled="!canUpload || uploading"
      >
        <span v-if="uploading" class="loading-spinner"></span>
        {{ uploading ? '上传中...' : '开始上传' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import UploadOptions from '../misc/UploadOptions.vue'
import { useUploadFileModal } from './UploadFileModal'

const props = defineProps({
  modalId: { type: String, default: '' },
  title: { type: String, default: '上传文件' },
  acceptedTypes: { type: Array, default: () => ['audio/*', 'video/*', '.txt', '.json', '.rttm', '.stm'] },
  maxSize: { type: Number, default: 100 * 1024 * 1024 },
  multiple: { type: Boolean, default: false },
  uploadOptions: { type: Array, default: () => [] },
  showTagsInput: { type: Boolean, default: true },
  autoUpload: { type: Boolean, default: false },
  supportedFormats: { type: Array, default: () => ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg'] },
  deviceOptions: { type: Array, default: () => [] },
  algorithmOptions: { type: Array, default: () => [] }
})

const emit = defineEmits(['close', 'confirm', 'selectFolder'])

const {
  fileInput,
  selectedFiles,
  selectedTxtFiles,
  isDragging,
  uploading,
  tags,
  annotationCode,
  referenceParamOptions,
  inputId,
  hasUploadOptions,
  uploadConfig,
  audioTypeOptions,
  playbackDeviceOptions,
  deviceOptions,
  algorithmOptions,
  canUpload,
  audioFilesCount,
  totalFileSize,
  formatFileSize,
  dragMessage,
  handleFileSelect,
  handleDragOver,
  handleDragLeave,
  handleDrop,
  removeFile,
  handleUpload
} = useUploadFileModal(props, emit)
</script>

<style scoped>
@import './UploadFileModal.css';
</style>
