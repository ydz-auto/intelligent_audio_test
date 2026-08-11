<!-- MVC role: View -->
<template>
  <div class="audio-import-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title" style="color: var(--primary-color);">
          <i class="fas fa-music"></i>
          音频管理
        </h2>
        <p class="page-description">管理和维护语音测试使用的音频文件</p>
      </div>
      <div class="header-right">
        <div class="action-buttons">
            <button class="btn btn-primary" @click="openUploadModal">
              <i class="fas fa-upload btn-icon"></i>
              上传音频
            </button>
            <button class="btn btn-secondary" @click="batchImportFromFolder">
            <i class="fas fa-folder-open btn-icon"></i>
            批量从文件夹导入
            </button>
          <button class="btn btn-secondary" @click="openBatchAnnotationModal">
            <i class="fas fa-file-import btn-icon"></i>
            批量更新标注
            </button>
          <button class="btn btn-secondary" @click="batchDelete" :disabled="selectedAudios.length === 0">
            <i class="fas fa-trash btn-icon">
            </i>
            批量删除
          </button>
          <button class="btn btn-secondary" @click="batchExport" :disabled="selectedAudios.length === 0">
            <i class="fas fa-file-export btn-icon"></i>
            批量导出
          </button>
        </div>
      </div>
    </div>

    <!-- 全局上传进度显示 -->
    <UploadProgressCard
      v-if="uploadProgress > 0 && uploadStatus !== 'idle'"
      :upload-progress="uploadProgress"
      :current-task="currentTask"
      :current-uploading-file="currentUploadingFile"
      :is-retrying-failed="isRetryingFailed"
      @dismiss="handleDismiss"
      @pause="handlePause"
      @retry="handleRetry"
    />

    <!-- 音频列表内容 -->
    <div class="audio-content-card">
      <AudioListComponent
          :audios="formattedAudios"
          :loading="loading"
          :view-mode="viewMode"
          :selected-audios="selectedAudios"
          :total-audios="totalAudios"
          :current-page="currentPage"
          :page-size="pageSize"
          :all-tags="allTags || []"
          :selected-tags="selectedTags || []"
          :tag-modes="tagModesObject || {}"
          :enable-selection="true"
          :show-status="true"
          :audio-type="audioTypeFilter"
          :server-folder-tree="serverFolderTree"
          :folder-loading="folderLoading"
          :expanded-folder-paths="expandedFolderPaths"
          :is-folder-all-selected-fn="isFolderAllSelected"
          :is-folder-partial-selected-fn="isFolderPartialSelected"
          @view-change="switchView"
          @search="searchAudios"
          @filterChange="filterAudios"
          @toggleTag="toggleTag"
          @selectionChange="toggleAudioSelection"
          @toggle-folder-selection="toggleFolderSelection"
          @toggleSelectAll="toggleSelectAll"
          @selectCurrentPage="selectCurrentPage"
          @selectAllPages="selectAllPages"
          @preview="previewAudio"
          @edit="editMetadata"
          @download="downloadAudio"
          @delete="deleteAudio"
          @convert="convertAudio"
          @pageChange="handleGoToPage"
          @sizeChange="handlePageSizeChange"
          @expand-folder="handleExpandFolder"
        >
          <template #actions></template>
          <template #file-actions></template>
        </AudioListComponent>
    </div>

    <!-- 转换模态框 -->
    <ConvertModal
      :visible="showConvertModal"
      :info="convertAudioInfo"
      @close="showConvertModal = false"
      @confirm="() => convertAudio()"
    />

    
    <!-- 音频播放器模态窗 -->
    <AudioPlayerModal
      :visible="showAudioPlayerModal"
      :title="'音频播放'"
      :audio-id="currentPreviewAudioId"
      :audio-title="audioTitle"
      :audio-type="currentPreviewAudioType"
      :selected-devices="[]"
      @close="showAudioPlayerModal = false"
    />

    <!-- 用例生成提示：Teleport 到 body，避免被 .main-content 的 transform 截获 fixed 包含块导致随页面滚动 -->
    <Teleport to="body">
      <div v-if="showTestCaseGeneratedTip" class="test-case-generated-tip">
        <div class="tip-content">
          <i class="fas fa-check-circle tip-icon"></i>
          <div class="tip-text">
            <span class="tip-title">已生成 {{ testCaseGeneratedCount }} 个草稿用例</span>
            <span class="tip-desc">用例参数（播放设备、声压级、噪声等）请在用例管理页面完善</span>
          </div>
          <div class="tip-actions">
            <button class="btn btn-primary btn-sm" @click="goToTestCaseManager">
              <i class="fas fa-edit"></i> 去编辑
            </button>
            <button class="btn btn-text btn-sm" @click="showTestCaseGeneratedTip = false">
              稍后
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 批量更新标注模态窗 -->
    <div class="modal-overlay" v-if="showBatchAnnotationModal" style="opacity: 1 !important; visibility: visible !important; pointer-events: auto !important; display: flex !important;">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3>批量更新标注</h3>
          <div class="modal-close" @click="showBatchAnnotationModal = false">
            <i class="fas fa-times"></i>
          </div>
        </div>
        <div class="modal-body">
          <BatchAnnotationModal
            @close="showBatchAnnotationModal = false"
            @success="handleAnnotationSuccess"
          />
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref, watch, nextTick, type Ref } from 'vue';

// 监听键盘事件，处理 ESC 退出
const handleGlobalKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    if (showConvertModal.value) {
      showConvertModal.value = false;
    }
  }
};
import AudioListComponent from '../../components/common/audio/AudioListComponent.vue';
import UploadProgressCard from '../../components/common/misc/UploadProgressCard.vue';
import AudioPlayerModal from '../../components/common/audio/AudioPlayerModal.vue';
import BatchAnnotationModal from '../../components/common/modal/BatchAnnotationModal.vue';
import ConvertModal from './ConvertModal.vue';
import { useAudioImport } from './audioImport';
import { useUploadState } from '../../composables/upload/useUploadState';
import { formatAudioData } from '../../utils/audioUtils';

interface AudioUploadTask {
  id: string | number;
  taskId: string | number;
  totalFiles: number;
  completedFiles: number;
  failedFiles: number;
  totalSize: number;
  uploadedSize: number;
  status: 'pending' | 'uploading' | 'completed' | 'failed' | 'paused';
  files: Array<{
    name: string;
    size: number;
    uploadedSize: number;
    status: 'pending' | 'uploading' | 'completed' | 'failed';
    errorMessage?: string;
  }>;
}

const {
  audioList: audioList,
  viewMode: viewMode, 
  currentPage: currentPage, 
  pageSize: pageSize, 
  loading,
  totalAudios: totalAudios,
  searchQuery: searchQuery, 
  uploadProgress: uploadProgress, 
  showConvertModal: showConvertModal, 
  selectedAudios: selectedAudios, 
  filters, 
  selectedTags: selectedTags,
  tagModes: tagModes,
  tagModesObject: tagModesObject,
  allTags: allTags, 
  urlImportData: urlImportData, 
  convertAudioInfo: convertAudioInfo, 
  stats, 
  filteredAudios: filteredAudios, 
  totalPages: totalPages, 
  flattenedFolderTree: flattenedFolderTree,
  serverFolderTree,
  folderLoading,
  expandedFolderPaths,
  fetchFolderTree,
  toggleFolderExpand,
  isFolderExpanded,
  loadSubTree,
  mergeSubTree,
  expandedFolders: expandedFolders,
  switchView: switchView, 
  applyFilters: applyFilters, 
  resetFilters: resetFilters, 
  searchAudios: originalSearchAudios,
  filterAudios: originalFilterAudios,
  toggleTag: toggleTag,
  toggleSelectAll: toggleSelectAll,
  toggleAudioSelection: toggleAudioSelection,
  toggleFolderSelection: toggleFolderSelection,
  isFolderAllSelected: isFolderAllSelected,
  isFolderPartialSelected: isFolderPartialSelected,
  selectCurrentPage: selectCurrentPage,
  selectAllPages: selectAllPages,
  showSelectAllOptions: showSelectAllOptions,
  openUploadModal: openUploadModal, 
  closeModal: closeModal, 
  pickFiles: pickFiles,
  handleDrop: handleDrop, 
  selectedFilesForUpload: selectedFilesForUpload,
  batchImportFromFolder: batchImportFromFolder,
  batchDelete: batchDelete, 
  batchExport: batchExport, 
  previewAudio: previewAudio, 
  editMetadata: editMetadata, 
  downloadAudio: downloadAudio, 
  deleteAudio: deleteAudio, 
  shareAudio: shareAudio, 
  prevPage: prevPage, 
  nextPage: nextPage, 
  handleGoToPage: handleGoToPage, 
  handlePageSizeChange: handlePageSizeChange, 
  convertAudio: convertAudio, 
  resetAllStates: resetAllStates,
  fetchAudios: fetchAudios,
  uploadOptions: uploadOptions,
  playbackDevices: playbackDevices,
  fetchPlaybackDevices: fetchPlaybackDevices,
  folderImportOptions: folderImportOptions,
  initModalWatchers: initModalWatchers,
  uploadTasks: rawUploadTasks,
  currentTask: rawCurrentTask,
  fileList: fileList,
  uploadStatus: uploadStatus,
  currentUploadingFile: currentUploadingFile,
  isRetryingFailed: isRetryingFailed,
  resumeUploadTask: resumeUploadTask,
  checkAndResumeTasks: checkAndResumeTasks,
  removeLocalTask: removeLocalTask,
  retryFailedFiles: retryFailedFiles,
  dismissTask: dismissTask,
  toggleFolder: toggleFolder,
  pauseUploadTask: pauseUploadTask,
  showAudioPlayerModal: showAudioPlayerModal,
  audioTitle: audioTitle,
  currentPreviewAudioId,
  currentPreviewAudioType,
  pathBasename: pathBasename,
  testCaseGeneratedCount,
  showTestCaseGeneratedTip,
  goToTestCaseManager
} = useAudioImport();

const { pendingAction, consumeAction } = useUploadState();

watch(pendingAction, (payload) => {
  const { action, taskId } = payload;
  if (!action) return;
  consumeAction();
  if (action === 'openUploadModal') {
    openUploadModal();
  } else if (action === 'openFolderImport') {
    batchImportFromFolder();
  } else if (action === 'dismissTask' && taskId) {
    dismissTask(taskId);
  } else if (action === 'pauseTask' && taskId) {
    pauseUploadTask(taskId);
  } else if (action === 'retryTask' && taskId) {
    retryFailedFiles(taskId);
  }
});

// 进度条事件处理
const handleDismiss = (taskId: string) => {
  dismissTask(taskId);
};

const handlePause = (taskId: string) => {
  pauseUploadTask(taskId);
};

const handleRetry = (taskId: string) => {
  retryFailedFiles(taskId);
};

// 修复搜索功能：更新searchQuery并调用fetchAudios
const searchAudios = (query: string) => {
  searchQuery.value = query;
  originalSearchAudios();
};

// 重置搜索功能：清空搜索词并刷新列表
const resetSearch = () => {
  searchQuery.value = '';
  originalSearchAudios();
};

// 修复筛选功能：确保所有筛选条件都被正确处理
const filterAudios = (newFilters?: any) => {
  if (newFilters) {
    if (newFilters.format) filters.value.format = newFilters.format;
    if (newFilters.sampleRate) filters.value.sampleRate = newFilters.sampleRate;
    if (newFilters.duration) filters.value.duration = newFilters.duration;
    if (newFilters.audioType) filters.value.audioType = newFilters.audioType;
    if (newFilters.tags) {
      selectedTags.value = newFilters.tags || [];
    }
    if (newFilters.tagModes) {
      tagModes.value = new Map(Object.entries(newFilters.tagModes));
    }
    if (newFilters.keyword) {
      searchQuery.value = newFilters.keyword;
    }
  }
  originalFilterAudios(newFilters);
};

const uploadTasks = rawUploadTasks as unknown as Ref<AudioUploadTask[]>;
const currentTask = rawCurrentTask as unknown as Ref<AudioUploadTask | null>;


const handleExpandFolder = async (folderPath: string) => {
  toggleFolderExpand(folderPath);
  if (isFolderExpanded(folderPath)) {
    const subTree = await loadSubTree(folderPath);
    if (subTree) {
      mergeSubTree(folderPath, subTree);
    }
  }
};

onMounted(() => {
  window.addEventListener('keydown', handleGlobalKeyDown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleGlobalKeyDown);
});

// 格式化音频数据以适配 AudioListComponent
const formattedAudios = computed(() => {
    const result = (filteredAudios.value || []).map(audio => formatAudioData(audio));
    return result;
  });

  // 音频类型过滤器，用于AudioListComponent
  const audioTypeFilter = ref('all');

// 批量更新标注模态窗
const showBatchAnnotationModal = ref(false);

const openBatchAnnotationModal = () => {
  showBatchAnnotationModal.value = true;
};

const handleAnnotationSuccess = (_result: { updatedCount: number; failedCount: number; refreshedTestCaseIds: string[] }) => {
  showBatchAnnotationModal.value = false;
  fetchAudios();
};

// 播放设备选择模态窗状态

// 音频播放器模态窗状态

// 修改预览音频函数，直接打开音频播放器模态窗

// 处理设备选择
</script>

<style>
@import '../../assets/styles/main.css';
</style>

<style scoped>
@import './audioImport.css';

.test-case-generated-tip {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 380px;
  max-width: 480px;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

.tip-content {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.tip-icon {
  font-size: 24px;
  color: #10b981;
  flex-shrink: 0;
}

.tip-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tip-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}

.tip-desc {
  font-size: 12px;
  color: #6b7280;
}

.tip-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>
