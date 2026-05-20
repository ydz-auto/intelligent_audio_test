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
              :all-tags="allTags.value || []"
              :selected-tags="selectedTags.value || []"
              :tag-modes="tagModesObject.value || {}"
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
import { ref, onMounted, onUnmounted, watch, computed } from 'vue';
import AudioListComponent from './AudioListComponent.vue';
import UploadProgressCard from './UploadProgressCard.vue';
import { useAudioList, type AudioItem } from '../../composables/useAudioList';
import { useUploadState } from '../../composables/useUploadState';
import { useAudioImport } from '../../views/AudioImportLogic/audioImport';
import { getModalManager } from '../../composables/useModal';
import { MODAL_TYPES } from '../../shared/types';
import { parseDuration, formatDurationLong } from '../../utils/audioUtils';

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
}>();

const {
  audios,
  totalAudios,
  currentPage,
  pageSize,
  searchQuery,
  allTags,
  selectedTags,
  tagModes,
  tagModesObject,
  filters,
  loadAudios,
  loadAllTags,
  handleSearch,
  handleFilterChange,
  handleToggleTag,
  handleTagClick,
  handlePageChange,
  handleSizeChange,
  resetFilters
} = useAudioList();

const loading = ref(false);

const { uploadProgress, currentTask, currentUploadingFile, isRetryingFailed, uploadStatus } = useUploadState();

let audioImport: ReturnType<typeof useAudioImport> | null = null;

const getAudioImport = () => {
  if (!audioImport) {
    audioImport = useAudioImport();
  }
  return audioImport;
};

const modalManager = getModalManager();

const dismissTask = (taskId: string) => {
  getAudioImport().dismissTask(taskId);
};

const pauseUploadTask = (taskId: string) => {
  getAudioImport().pauseUploadTask(taskId);
};

const retryFailedFiles = async (taskId: string) => {
  await getAudioImport().retryFailedFiles(taskId);
};

const openUploadModal = async () => {
  try {
    await getAudioImport().openUploadModal();
  } catch (error) {
    console.error('打开上传模态窗失败:', error);
  }
};

const batchImportFromFolder = async () => {
  try {
    await getAudioImport().batchImportFromFolder();
  } catch (error) {
    console.error('打开文件夹导入模态窗失败:', error);
  }
};

// 上传任务相关方法

const selectedAudios = ref<(string | number)[]>([]);
const allAudiosCache = ref<any[]>([]);

const formattedAudios = computed((): AudioItem[] => {
  return audios.value;
});

const totalFilteredDuration = computed(() => {
  let totalSeconds = 0;
  for (const audio of audios.value) {
    totalSeconds += parseDuration(audio.duration);
  }
  return formatDurationLong(totalSeconds);
});

const selectedAudiosDuration = computed(() => {
  let totalSeconds = 0;
  const audioListToUse = allAudiosCache.value.length > 0 ? allAudiosCache.value : audios.value;
  for (const audio of audioListToUse) {
    if (selectedAudios.value.includes(audio.id)) {
      totalSeconds += parseDuration(audio.duration);
    }
  }
  return formatDurationLong(totalSeconds);
});

const handleClose = () => {
  emit('close');
};

const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && props.visible) {
    event.stopPropagation();
    handleClose();
  }
};

const handleDismiss = (taskId: string) => {
  dismissTask(taskId);
};

const handlePause = (taskId: string) => {
  pauseUploadTask(taskId);
};

const handleRetry = (taskId: string) => {
  retryFailedFiles(taskId);
};

const handleSelectionChange = (audioId: string | number) => {
  const index = selectedAudios.value.indexOf(audioId);
  if (index > -1) {
    selectedAudios.value = selectedAudios.value.filter(id => id !== audioId);
  } else {
    selectedAudios.value = [...selectedAudios.value, audioId];
  }
};

watch(() => props.visible, (newVal) => {
  if (newVal) {
    window.addEventListener('keydown', handleKeyDown);
    selectedAudios.value = [];
    allAudiosCache.value = [];
    resetFilters({ audioType: props.audioType });
    loadAudios();
    loadAllTags();
  } else {
    window.removeEventListener('keydown', handleKeyDown);
  }
}, { immediate: true });

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown);
});

const selectAudio = (audio: AudioItem) => {
  if (props.isMultiSelect) {
    const audioId = audio.id;
    const index = selectedAudios.value.indexOf(audioId);
    if (index > -1) {
      selectedAudios.value = selectedAudios.value.filter(id => id !== audioId);
    } else {
      selectedAudios.value = [...selectedAudios.value, audioId];
    }
    emit('selectionChange', audioId);
  } else {
    emit('select', audio);
    emit('close');
  }
};

const handleConfirmSelect = () => {
  const audioListToUse = allAudiosCache.value.length > 0 ? allAudiosCache.value : audios.value;
  const selectedAudioObjects = audioListToUse.filter((a: any) => selectedAudios.value.includes(a.id));
  emit('selectMultiple', selectedAudioObjects);
  emit('close');
};

const handleSelectCurrentPage = () => {
  const currentPageIds = audios.value.map(a => a.id);
  const newSelected = [...selectedAudios.value];
  for (const id of currentPageIds) {
    if (!newSelected.includes(id)) {
      newSelected.push(id);
    }
  }
  selectedAudios.value = newSelected;
};

const handleDeselectCurrentPage = () => {
  const currentPageIds = new Set(audios.value.map(a => a.id));
  selectedAudios.value = selectedAudios.value.filter(id => !currentPageIds.has(id));
};

const handleDeselectAll = () => {
  selectedAudios.value = [];
  allAudiosCache.value = [];
};

const handleToggleSelectAll = () => {
  if (audios.value.length === 0) return;

  const currentPageIds = new Set(audios.value.map(a => a.id));
  const allSelected = currentPageIds.size > 0 && currentPageIds.size === audios.value.length &&
    audios.value.every(a => selectedAudios.value.includes(a.id));

  if (allSelected) {
    selectedAudios.value = selectedAudios.value.filter(id => !currentPageIds.has(id));
  } else {
    const newSelected = [...selectedAudios.value];
    for (const audio of audios.value) {
      if (!newSelected.includes(audio.id)) {
        newSelected.push(audio.id);
      }
    }
    selectedAudios.value = newSelected;
  }
};

const openAudioMetadataModal = async (audioId: string | number) => {
  let audio: any | undefined = audios.value.find(a => a.id === audioId);

  try {
    const fullAudio = await import('../../utils/api').then(m => m.audiosApi.getOne(audioId));
    if (fullAudio) {
      audio = fullAudio;
    }
  } catch (error) {
    console.error('加载音频详情失败:', error);
  }

  if (!audio) return;

  let tagsArray: string[] = [];
  if (Array.isArray(audio.tags)) {
    tagsArray = audio.tags;
  } else if (audio.tags) {
    const tagsString = String(audio.tags);
    if (tagsString) {
      tagsArray = tagsString.split(',').map((tag: string) => tag.trim());
    }
  }

  const metadata = {
    id: audio.id,
    fileName: audio.name || audio.filename || audio.originalFilename || audio.filename || '',
    category: audio.filepath || audio.filePath || audio.path || '',
    audioType: audio.audioType || audio.type || 'dry',
    asrText: audio.asrText || '',
    translations: audio.translations || [{ direction: 'zh-en', text: '' }],
    tags: tagsArray.join(','),
    annotations: audio.annotations || []
  };

  try {
    const payload: any = await modalManager.open(MODAL_TYPES.DETAIL_VIEW, {
      title: '编辑元数据',
      data: metadata,
      fields: [
        { key: 'fileName', label: '文件名' },
        { key: 'category', label: '分类' },
        { key: 'audioType', label: '音频类型' },
        { key: 'asrText', label: 'ASR文本' },
        { key: 'tags', label: '标签' },
        { key: 'translations', label: '翻译语向' },
        { key: 'annotations', label: '标注' }
      ],
      width: '900px',
      maxWidth: '95vw',
      maxHeight: '90vh'
    });

    if (payload && payload.action === 'save') {
      const editedData = payload.data;
      const response: any = await import('../../utils/api').then(m => m.audiosApi.updateMetadata(editedData.id, editedData, { unwrapResponse: false }));
      if (response?.success) {
        await loadAudios();
      } else {
        alert('保存失败: ' + (response?.message || '未知错误'));
      }
    }
  } catch (err: any) {
    if (err !== 'canceled') {
      console.error('打开/保存元数据失败:', err);
    }
  }
};

watch(uploadProgress, (newProgress) => {
  if (newProgress === 100) {
    console.log('AudioSelectModal: 检测到上传完成，刷新音频列表');
    setTimeout(() => {
      loadAudios();
    }, 1000);
  }
});
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: calc(var(--z-index-modal-top, 13000) + 1) !important;
  animation: fadeIn 0.3s ease;
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
}

.modal-container {
  background-color: white;
  border: var(--card-border);
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-sm);
  width: 95%;
  max-width: 1400px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-lg);
  background-color: var(--background-primary);
  border-bottom: var(--card-border);
}

.modal-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.modal-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--text-secondary);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--border-radius-full);
  transition: all 0.2s;
}

.modal-close:hover {
  background-color: var(--background-secondary);
  color: var(--text-primary);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: var(--spacing-lg);
  border-top: var(--card-border);
  background-color: var(--background-primary);
  gap: var(--spacing-md);
}

.selected-count {
  flex: 1;
  color: var(--text-secondary);
  font-size: 14px;
}

.selection-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.info-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  color: var(--text-secondary);
  font-size: 14px;
}

.info-label {
  color: var(--text-secondary);
}

.info-value {
  color: var(--text-primary);
  font-weight: var(--font-weight-medium);
}

.info-duration {
  color: var(--primary-color);
  font-size: 13px;
}

.audio-select-modal-content {
  padding: 0;
}

.header-action-buttons {
  display: flex;
  gap: var(--spacing-sm);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    visibility: hidden;
  }
  to {
    opacity: 1;
    visibility: visible;
  }
}
</style>
