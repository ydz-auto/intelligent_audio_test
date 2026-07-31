<template>
  <div class="batch-annotation-modal">
    <div class="upload-content">
      <!-- 拖放区域（紧凑：有文件后收缩） -->
      <div
        class="drop-zone"
        :class="{ 'drop-zone-active': isDragging, 'drop-zone-compact': annotationItems.length > 0 || md5Calculating }"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <div class="drop-zone-content">
          <i v-if="annotationItems.length === 0 && !md5Calculating" class="fas fa-file-import"></i>
          <i v-else-if="md5Calculating" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-check-circle"></i>

          <template v-if="annotationItems.length === 0 && !md5Calculating">
            <h4>拖拽音频+标注文件到此处或点击选择</h4>
            <p class="drop-zone-hint">
              同时选择音频文件和对应的标注文件<br>
              支持音频：.wav, .mp3, .m4a, .flac 等；标注：.json, .jsonl, .rttm, .stm, .txt<br>
              按文件名匹配（如 audio1.wav ↔ audio1.json）
            </p>
            <label class="browse-btn">
              <input
                type="file"
                ref="fileInput"
                accept=".wav,.mp3,.m4a,.flac,.aac,.ogg,.json,.jsonl,.rttm,.stm,.txt"
                multiple
                @change="handleFileSelect"
              >
              选择文件
            </label>
          </template>

          <template v-else-if="md5Calculating">
            <h4>正在处理... {{ progress.processed }} / {{ progress.total }}</h4>
            <div class="progress-bar-wrap">
              <div class="progress-bar" :style="{ width: progressPercent + '%' }"></div>
            </div>
            <p class="drop-zone-hint">{{ progress.stage }} · {{ progressPercent }}%</p>
            <button class="btn-cancel" @click="cancelProcessing">取消</button>
          </template>

          <template v-else>
            <div class="compact-summary">
              <span>已解析 <strong>{{ annotationItems.length }}</strong> 个标注</span>
              <span class="dot">·</span>
              <span class="matched">匹配 {{ matchedCount }}</span>
              <span class="dot">·</span>
              <span class="unmatched">未匹配 {{ annotationItems.length - matchedCount }}</span>
            </div>
            <label class="browse-btn">
              <input
                type="file"
                ref="fileInput"
                accept=".wav,.mp3,.m4a,.flac,.aac,.ogg,.json,.jsonl,.rttm,.stm,.txt"
                multiple
                @change="handleFileSelect"
              >
              重新选择
            </label>
          </template>
        </div>
      </div>

      <!-- 算法 + checkbox 并排 -->
      <div class="options-row" v-if="annotationItems.length > 0">
        <div class="algorithm-col">
          <AlgorithmSelector
            v-model="algorithmType"
            :show-params="false"
            :single="true"
          />
        </div>
        <div class="checkbox-col">
          <label class="checkbox-label">
            <input type="checkbox" v-model="refreshTestCases" />
            <span>同步刷新关联测试用例的参考参数</span>
          </label>
          <p class="checkbox-hint">更新后自动重新提取用例参数</p>
        </div>
      </div>

      <!-- 结果列表（虚拟/限量渲染） -->
      <div class="file-list" v-if="annotationItems.length > 0">
        <div class="file-list-header">
          <h4>标注匹配结果</h4>
          <div class="file-list-actions">
            <button v-if="unmatchedItems.length > 0" class="link-btn" @click="exportUnmatched">
              <i class="fas fa-download"></i> 导出未匹配 ({{ unmatchedItems.length }})
            </button>
            <label class="filter-toggle">
              <input type="checkbox" v-model="showUnmatchedOnly" :disabled="unmatchedItems.length === 0">
              <span>仅看未匹配</span>
            </label>
          </div>
        </div>
        <div class="files-container" ref="filesContainerRef" @scroll="onScroll">
          <div
            class="file-item"
            v-for="item in visibleItems"
            :key="item.annotationFileName"
          >
            <i class="fas" :class="item.matched ? 'fa-link has-match' : 'fa-unlink no-match'"></i>
            <div class="file-details">
              <span class="file-name">{{ item.annotationFileName }}</span>
              <span class="file-meta" v-if="item.matched">
                <span class="meta-tag has-match">→ {{ item.audioName }} (ID: {{ item.audioId }})</span>
              </span>
              <span class="file-meta" v-else>
                <span class="meta-tag no-match">未匹配到音频</span>
              </span>
              <div class="annotation-summary" v-if="item.annotations.length > 0">
                <span class="ann-tag" v-for="(ann, idx) in item.annotations" :key="idx">
                  {{ ann.code }} ({{ ann.format }})
                </span>
              </div>
            </div>
          </div>
          <div v-if="displayedItems.length < filteredItems.length" class="load-more-hint">
            已加载 {{ displayedItems.length }} / {{ filteredItems.length }} 条（滚动加载更多）
          </div>
        </div>
      </div>
    </div>

    <!-- 完成统计 toast -->
    <div v-if="resultToast.visible" class="result-toast" :class="resultToast.type">
      <i class="fas" :class="resultToast.type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'"></i>
      <div class="toast-body">
        <strong>{{ resultToast.title }}</strong>
        <span>{{ resultToast.detail }}</span>
      </div>
      <button class="toast-close" @click="resultToast.visible = false">×</button>
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ errorMsg }}</span>
      <button class="toast-close" @click="errorMsg = ''">×</button>
    </div>

    <div class="modal-footer">
      <button
        type="button"
        class="btn-secondary"
        @click="$emit('close')"
        :disabled="submitting"
      >
        取消
      </button>
      <button
        type="button"
        class="btn-primary"
        @click="handleSubmit"
        :disabled="matchedCount === 0 || submitting"
      >
        <span v-if="submitting" class="loading-spinner"></span>
        {{ submitting ? '提交中...' : `更新标注 (${matchedCount})` }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import AlgorithmSelector from '../audio/AlgorithmSelector.vue'

import { useBatchAnnotationModal } from './BatchAnnotationModal'

defineProps({})
const emit = defineEmits(['close', 'success'])

const {
  fileInput,
  isDragging,
  submitting,
  md5Calculating,
  algorithmType,
  refreshTestCases,
  annotationItems,
  errorMsg,
  progress,
  progressPercent,
  cancelProcessing,
  resultToast,
  showUnmatchedOnly,
  filesContainerRef,
  matchedCount,
  unmatchedItems,
  filteredItems,
  displayedItems,
  visibleItems,
  onScroll,
  handleFileSelect,
  handleDragOver,
  handleDragLeave,
  handleDrop,
  exportUnmatched,
  handleSubmit
} = useBatchAnnotationModal({}, emit)
</script>

<style scoped>
@import './BatchAnnotationModal.css';
</style>
