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
import { ref, onMounted, onUnmounted, watch, computed } from 'vue';
import AudioListComponent from './AudioListComponent.vue';
import UploadProgressCard from './UploadProgressCard.vue';
import { useAudioList, type AudioItem } from '../../composables/useAudioList';
import { useUploadState } from '../../composables/useUploadState';
import { useFolderSelection } from '../../composables/useFolderSelection';
import { getModalManager } from '../../composables/useModal';
import { MODAL_TYPES } from '../../shared/types';
import { audiosApi } from '../../utils/api';
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
  (e: 'uploadRequest'): void;
  (e: 'folderImportRequest'): void;
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

const { uploadProgress, currentTask, currentUploadingFile, isRetryingFailed, uploadStatus, requestAction } = useUploadState();

const modalManager = getModalManager();

const openUploadModal = () => {
  emit('uploadRequest');
};

const batchImportFromFolder = () => {
  emit('folderImportRequest');
};

// 上传任务相关方法

const selectedAudios = ref<(string | number)[]>([]);
const allAudiosCache = ref<any[]>([]);

// 文件夹视图状态
const serverFolderTree = ref<any>({
  name: '音频文件',
  path: '',
  count: 0,
  file_count: 0,
  has_children: false,
  files: [],
  folders: []
});
const folderLoading = ref(false);
const expandedFolderPaths = ref<Set<string>>(new Set(['']));

// 复用文件夹批量勾选逻辑
const { toggleFolderSelection, isFolderAllSelected, isFolderPartialSelected } = useFolderSelection(selectedAudios);

async function fetchFolderTree() {
  folderLoading.value = true;
  try {
    const response: any = await audiosApi.getFolderTree({
      audioType: props.audioType ? props.audioType : undefined,
      depth: 1
    }, { unwrapResponse: false });
    if (response?.success && response?.data?.tree) {
      serverFolderTree.value = normalizeTreeNode(response.data.tree);
    }
  } catch (e) {
    console.error('加载文件夹树失败:', e);
  } finally {
    folderLoading.value = false;
  }
}

function normalizeFile(file: any): any {
  return {
    ...file,
    id: file.id,
    name: file.name || '',
    filename: file.filename || file.name || '',
    format: file.format || '',
    duration: file.duration || 0,
    size: file.size || 0,
    audio_type: file.audio_type || file.audioType || file.type || 'dry',
    type: file.type || file.audio_type || file.audioType || file.type || 'dry',
    created_at: file.created_at || file.createdAt || '',
  };
}

function normalizeTreeNode(node: any): any {
  if (!node) return { name: 'root', path: '', count: 0, file_count: 0, has_children: false, files: [], folders: [] };
  return {
    name: node.name || 'unnamed',
    path: node.path ?? '',
    count: node.count ?? node.total ?? 0,
    file_count: node.file_count ?? node.fileCount ?? (Array.isArray(node.files) ? node.files.length : 0),
    has_children: node.has_children ?? node.hasChildren ?? false,
    files: Array.isArray(node.files) ? node.files.map(normalizeFile) : [],
    folders: Array.isArray(node.folders) ? node.folders.map(normalizeTreeNode) : [],
  };
}

function toggleFolderExpand(folderPath: string) {
  const newSet = new Set(expandedFolderPaths.value);
  if (newSet.has(folderPath)) {
    newSet.delete(folderPath);
  } else {
    newSet.add(folderPath);
  }
  expandedFolderPaths.value = newSet;
}

async function loadSubTree(folderPath: string): Promise<any | null> {
  folderLoading.value = true;
  try {
    const response: any = await audiosApi.getFolderTree({
      audioType: props.audioType ? props.audioType : undefined,
      parentPath: folderPath,
      depth: 10
    }, { unwrapResponse: false });
    if (response?.success && response?.data?.tree) {
      return normalizeTreeNode(response.data.tree);
    }
  } catch (e) {
    console.error('加载子树失败:', e);
  } finally {
    folderLoading.value = false;
  }
  return null;
}

function mergeSubTree(targetPath: string, fullTree: any) {
  function findNode(node: any, path: string): any {
    if (node.path === path) return node;
    if (node.folders) {
      for (const child of node.folders) {
        const found = findNode(child, path);
        if (found) return found;
      }
    }
    return null;
  }
  const subNode: any = findNode(fullTree, targetPath);
  if (!subNode) return;
  function findAndUpdate(node: any): boolean {
    if (node.path === targetPath) {
      node.files = subNode.files;
      node.file_count = subNode.file_count ?? subNode.files?.length ?? 0;
      node.has_children = subNode.has_children;
      const existingFolders = new Map<string, any>((node.folders || []).map((f: any) => [f.path as string, f]));
      const merged: any[] = [];
      for (const newFolder of (subNode.folders || [])) {
        const existing: any = existingFolders.get(newFolder.path);
        if (existing) {
          existing.name = newFolder.name;
          existing.count = newFolder.count;
          existing.file_count = newFolder.file_count;
          existing.has_children = newFolder.has_children;
          if (newFolder.files && newFolder.files.length > 0) existing.files = newFolder.files;
          merged.push(existing);
        } else {
          merged.push(newFolder);
        }
      }
      node.folders = merged;
      return true;
    }
    if (node.folders) {
      for (const child of node.folders) {
        if (findAndUpdate(child)) return true;
      }
    }
    return false;
  }
  findAndUpdate(serverFolderTree.value);
}

const handleExpandFolder = async (folderPath: string) => {
  toggleFolderExpand(folderPath);
  if (expandedFolderPaths.value.has(folderPath)) {
    const subTree = await loadSubTree(folderPath);
    if (subTree) mergeSubTree(folderPath, subTree);
  }
};

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
  requestAction('dismissTask', taskId);
};

const handlePause = (taskId: string) => {
  requestAction('pauseTask', taskId);
};

const handleRetry = (taskId: string) => {
  requestAction('retryTask', taskId);
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
    expandedFolderPaths.value = new Set(['']);
    resetFilters({ audioType: props.audioType });
    loadAllTags();
    fetchFolderTree();
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

watch(uploadStatus, (newStatus) => {
  if (newStatus === 'completed') {
    setTimeout(() => {
      loadAudios();
    }, 500);
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
