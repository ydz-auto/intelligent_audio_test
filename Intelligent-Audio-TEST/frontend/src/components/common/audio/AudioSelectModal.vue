<template>
  <teleport to="body">
    <div class="modal-overlay" v-if="visible">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3 class="modal-title">{{ title }}</h3>
          <div class="modal-close" @click="handleClose">
            <i class="fas fa-times"></i>
          </div>
        </div>
        <div class="modal-body">
          <div class="audio-select-modal-content">
            <UploadProgressCard
              v-if="uploadProgress > 0"
              :upload-progress="uploadProgress"
              :current-task="currentTask"
              :current-uploading-file="currentUploadingFile"
              :is-retrying-failed="isRetryingFailed"
              @dismiss="handleDismiss"
              @pause="handlePause"
              @retry="handleRetry"
            />
            <AudioListComponent
              :audios="formattedAudios"
              :enable-selection="true"
              :show-status="true"
              :audio-type="props.audioType"
              :selected-audios="selectedAudios"
              :total-audios="totalAudios"
              :current-page="currentPage"
              :page-size="pageSize"
              :all-tags="allTags || []"
              :selected-tags="selectedTags || []"
              :tag-modes="tagModesObject || {}"
              :server-folder-tree="serverFolderTree"
              :folder-loading="folderLoading"
              :expanded-folder-paths="expandedFolderPaths"
              :is-folder-all-selected-fn="isFolderAllSelected"
              :is-folder-partial-selected-fn="isFolderPartialSelected"
              @search="handleSearch"
              @filterChange="handleFilterChange"
              @toggleTag="(tag, mode) => handleTagClick(tag, mode)"
              @select="selectAudio"
              @selectionChange="handleSelectionChange"
              @edit="openAudioMetadataModal"
              @pageChange="handlePageChange"
              @sizeChange="handleSizeChange"
              @selectCurrentPage="handleSelectCurrentPage"
              @deselectCurrentPage="handleDeselectCurrentPage"
              @deselectAll="handleDeselectAll"
              @toggleSelectAll="handleToggleSelectAll"
              @expand-folder="handleExpandFolder"
              @toggle-folder-selection="toggleFolderSelection"
            >
              <template #header-actions>
                <div class="header-action-buttons">
                  <div class="btn btn-primary" @click="openUploadModal">
                    <i class="fas fa-upload btn-icon"></i>
                    上传音频
                  </div>
                  <div class="btn btn-secondary" @click="batchImportFromFolder">
                    <i class="fas fa-folder-plus btn-icon"></i>
                    批量从文件夹导入
                  </div>
                </div>
              </template>
              <template #actions="{ audio }">
                <div class="btn btn-secondary" @click.stop="selectAudio(audio)">
                  <i class="fas fa-check btn-icon"></i>
                  选择
                </div>
              </template>
              <template #file-actions="{ audio }">
                <div class="btn btn-secondary" @click.stop="selectAudio(audio)">
                  <i class="fas fa-check btn-icon"></i>
                  选择
                </div>
              </template>
            </AudioListComponent>
          </div>
        </div>
        <div class="modal-footer">
          <div class="selection-info">
            <div class="info-item">
              <span class="info-label">当前页：</span>
              <span class="info-value">{{ totalAudios }} 个音频</span>
              <span class="info-duration">({{ totalFilteredDuration }})</span>
            </div>
            <div class="info-item" v-if="props.isMultiSelect && selectedAudios.length > 0">
              <span class="info-label">已选择：</span>
              <span class="info-value">{{ selectedAudios.length }} 个音频</span>
              <span class="info-duration">({{ selectedAudiosDuration }})</span>
            </div>
          </div>
          <div class="btn btn-secondary" @click="handleClose">取消</div>
          <div class="btn btn-primary" v-if="props.isMultiSelect" @click="handleConfirmSelect" :disabled="selectedAudios.length === 0">
            确认选择
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import AudioListComponent from './AudioListComponent.vue';
import UploadProgressCard from '../misc/UploadProgressCard.vue';
import { useAudioSelectModal } from './AudioSelectModal';
import type { AudioItem } from '../../../composables/audio/useAudioList';

const props = defineProps<{
  visible: boolean;
  title: string;
  audioType: string;
  isMultiSelect?: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'select', audio: AudioItem): void;
  (e: 'selectMultiple', audios: AudioItem[]): void;
  (e: 'uploadRequest'): void;
  (e: 'folderImportRequest'): void;
}>();

const {
  uploadProgress,
  currentTask,
  currentUploadingFile,
  isRetryingFailed,
  handleDismiss,
  handlePause,
  handleRetry,
  formattedAudios,
  selectedAudios,
  totalAudios,
  currentPage,
  pageSize,
  allTags,
  selectedTags,
  tagModesObject,
  serverFolderTree,
  folderLoading,
  expandedFolderPaths,
  isFolderAllSelected,
  isFolderPartialSelected,
  handleSearch,
  handleFilterChange,
  handleTagClick,
  selectAudio,
  handleSelectionChange,
  openAudioMetadataModal,
  handlePageChange,
  handleSizeChange,
  handleSelectCurrentPage,
  handleDeselectCurrentPage,
  handleDeselectAll,
  handleToggleSelectAll,
  handleExpandFolder,
  toggleFolderSelection,
  openUploadModal,
  batchImportFromFolder,
  selectedAudiosDuration,
  totalFilteredDuration,
  handleClose,
  handleConfirmSelect
} = useAudioSelectModal(props, emit)
</script>

<style scoped>
@import './AudioSelectModal.css';
</style>
