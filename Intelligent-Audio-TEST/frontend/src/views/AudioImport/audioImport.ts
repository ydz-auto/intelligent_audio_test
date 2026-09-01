import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAudioList } from '../../composables/audio/useAudioList';
import { useAudioUpload } from '../../composables/audio/useAudioUpload';
import { useFolderTree } from '../../composables/shared/useFolderTree';
import { useAlgorithmParams } from '../../composables/algorithm/useAlgorithmParams';
import { useDeviceManagement } from '../../composables/device/useDeviceManagement';
import { useAudioBatchOps } from '../../composables/audio/useAudioBatchOps';
import { useUploadModal } from '../../composables/upload/useUploadModal';
import { TestType, UploadStatus } from '@/shared/types/enums';

/**
 * useAudioImport - 轻量级协调层
 *
 * 组合以下子模块，暴露统一接口给 AudioImport.vue 使用：
 * - useAudioList: 音频列表管理（获取、过滤、分页、选择）
 * - useAudioUpload: 文件上传处理（分片上传、暂停/恢复/重试）
 * - useFolderTree: 文件夹树管理（懒加载、展开/折叠）
 * - useAlgorithmParams: 算法参数处理（缓存、解析、分发）
 * - useDeviceManagement: 设备管理（播放设备列表）
 * - useAudioBatchOps: 批量操作和单文件操作（删除/导出/预览/编辑）
 * - useUploadModal: 上传/文件夹导入模态框管理
 */
export function useAudioImport() {
  const router = useRouter();

  // 组合子模块
  const audioListModule = useAudioList();
  const folderTreeModule = useFolderTree();
  const algorithmModule = useAlgorithmParams();
  const deviceModule = useDeviceManagement();

  // 上传模块需要算法参数处理能力
  const uploadModule = useAudioUpload({
    resolveAlgorithmParamsFromAnnotations: algorithmModule.resolveAlgorithmParamsFromAnnotations,
    dispatchParamsToRounds: algorithmModule.dispatchParamsToRounds,
  });

  // 批量操作模块需要音频列表和刷新回调
  const batchOpsModule = useAudioBatchOps(
    audioListModule.audioList,
    audioListModule.selectedAudios,
    () => audioListModule.fetchAudios()
  );

  // 上传模态框模块
  const uploadModalModule = useUploadModal(
    {
      playbackDevices: deviceModule.playbackDevices,
      deviceList: deviceModule.deviceList,
      fetchPlaybackDevices: deviceModule.fetchPlaybackDevices,
      fetchDevices: deviceModule.fetchDevices,
    },
    {
      algorithmOptions: algorithmModule.algorithmOptions,
      fetchAlgorithmOptions: algorithmModule.fetchAlgorithmOptions,
    },
    {
      uploadOptions: uploadModule.uploadOptions,
      updateUploadOptionsFromModal: uploadModule.updateUploadOptionsFromModal,
      startUploadProcess: uploadModule.startUploadProcess,
      selectedFilesForUpload: uploadModule.selectedFilesForUpload,
    },
    () => audioListModule.fetchAudios()
  );

  // ========== 协调逻辑 ==========

  // 上传完成后的用例生成提示跳转
  const goToTestCaseManager = () => {
    uploadModule.showTestCaseGeneratedTip.value = false;
    const types = uploadModule.uploadOptions.testTypes || [];
    if (types.length === 1 && types[0] === TestType.E2E) {
      router.push('/E2ETest');
    } else {
      router.push('/TestCaseManager');
    }
  };

  // 搜索：同时刷新列表和文件夹树
  const searchAudios = () => {
    audioListModule.fetchAudios();
    if (audioListModule.viewMode.value === 'folder') {
      folderTreeModule.fetchFolderTree(
        audioListModule.searchQuery,
        audioListModule.filters,
        audioListModule.selectedTags,
        audioListModule.tagModes,
        uploadModule.uploadOptions.algorithmType
      );
    }
  };

  // 应用过滤器：同时刷新列表和文件夹树
  const applyFilters = () => {
    audioListModule.applyFilters();
    audioListModule.fetchAudios();
    if (audioListModule.viewMode.value === 'folder') {
      folderTreeModule.fetchFolderTree(
        audioListModule.searchQuery,
        audioListModule.filters,
        audioListModule.selectedTags,
        audioListModule.tagModes,
        uploadModule.uploadOptions.algorithmType
      );
    }
  };

  // 切换视图模式
  const switchView = (mode: 'list' | 'folder') => {
    audioListModule.switchView(mode);
    if (mode === 'folder') {
      folderTreeModule.fetchFolderTree(
        audioListModule.searchQuery,
        audioListModule.filters,
        audioListModule.selectedTags,
        audioListModule.tagModes,
        uploadModule.uploadOptions.algorithmType
      );
    }
  };

  // 重置过滤器
  const resetFilters = () => {
    audioListModule.resetFilters();
    applyFilters();
  };

  // 标签切换：刷新列表
  const toggleTag = (tag: string, mode?: 'or' | 'and') => {
    audioListModule.toggleTag(tag, mode);
    audioListModule.fetchAudios();
  };

  // 加载子树
  const loadSubTree = (folderPath: string) => {
    return folderTreeModule.loadSubTree(
      folderPath,
      audioListModule.searchQuery,
      audioListModule.filters,
      audioListModule.selectedTags,
      audioListModule.tagModes,
      uploadModule.uploadOptions.algorithmType
    );
  };

  // 获取文件夹树
  const fetchFolderTree = (params: any = {}) => {
    return folderTreeModule.fetchFolderTree(
      audioListModule.searchQuery,
      audioListModule.filters,
      audioListModule.selectedTags,
      audioListModule.tagModes,
      uploadModule.uploadOptions.algorithmType,
      params
    );
  };

  // 客户端扁平文件夹树计算
  const flattenedFolderTree = computed(() => {
    return folderTreeModule.computeFlattenedFolderTree(audioListModule.audioList.value);
  });

  // 重置所有状态
  const resetAllStates = () => {
    audioListModule.resetAllStates();
  };

  // ========== 生命周期 ==========

  onMounted(() => {
    // 先获取所有标签，再获取音频列表
    audioListModule.fetchAllTags().then(() => {
      audioListModule.fetchAudios();
    });
    deviceModule.fetchPlaybackDevices();
    uploadModule.uploadTasks.value = uploadModule.getLocalTasks();
    uploadModule.checkAndResumeTasks(() => audioListModule.fetchAudios());

    // 初始化 currentTask，如果有未完成的任务
    const tasks = uploadModule.getLocalTasks();
    const unfinished = tasks.find(t => t.status === UploadStatus.UPLOADING || t.status === UploadStatus.PAUSED || t.status === UploadStatus.FAILED);
    if (unfinished) {
      uploadModule.currentTask.value = unfinished;
      uploadModule.updateOverallProgress();
      if (uploadModule.uploadProgress.value === 0) {
        uploadModule.uploadProgress.value = 1;
      }
    }

    batchOpsModule.initModalWatchers();
  });

  onUnmounted(() => {
    if (uploadModule.uploadStatus.value === 'uploading') {
      // abortController 是内部的，无法直接访问，通过暂停来中止
      // 实际上 onUnmounted 中不需要额外处理，因为组件销毁后 ref 会被 GC
    }
  });

  // 跨页全选时的 watch
  watch(() => audioListModule.currentPage.value, () => {
    if (audioListModule.selectAllAcrossPages.value) {
      const currentPageIds = audioListModule.audioList.value.map(a => a.id);
      currentPageIds.forEach(id => {
        if (!audioListModule.selectedAudios.value.includes(id)) {
          audioListModule.selectedAudios.value.push(id);
        }
      });
    }
  });

  // ========== 暴露统一接口（与原 useAudioImport 完全兼容） ==========

  return {
    // 音频列表相关
    audioList: audioListModule.audioList,
    totalAudios: audioListModule.totalAudios,
    loading: audioListModule.loading,
    currentPage: audioListModule.currentPage,
    pageSize: audioListModule.pageSize,
    searchTerm: audioListModule.searchTerm,
    searchQuery: audioListModule.searchQuery,
    audioTypeFilter: audioListModule.audioTypeFilter,
    viewMode: audioListModule.viewMode,
    filters: audioListModule.filters,
    selectedTags: audioListModule.selectedTags,
    tagModes: audioListModule.tagModes,
    tagModesObject: audioListModule.tagModesObject,
    allTags: audioListModule.allTags,
    stats: audioListModule.stats,
    filteredAudios: audioListModule.filteredAudios,
    totalPages: audioListModule.totalPages,
    selectedAudios: audioListModule.selectedAudios,
    showSelectAllOptions: audioListModule.showSelectAllOptions,
    expandedFolders: folderTreeModule.expandedFolders,

    // 文件夹树相关
    flattenedFolderTree,
    serverFolderTree: folderTreeModule.serverFolderTree,
    folderLoading: folderTreeModule.folderLoading,
    expandedFolderPaths: folderTreeModule.expandedFolderPaths,
    fetchFolderTree,
    toggleFolderExpand: folderTreeModule.toggleFolderExpand,
    isFolderExpanded: folderTreeModule.isFolderExpanded,
    loadSubTree,
    mergeSubTree: folderTreeModule.mergeSubTree,
    toggleFolder: folderTreeModule.toggleFolder,

    // 选择相关
    toggleSelectAll: audioListModule.toggleSelectAll,
    toggleAudioSelection: audioListModule.toggleAudioSelection,
    toggleFolderSelection: audioListModule.toggleFolderSelection,
    isFolderAllSelected: audioListModule.isFolderAllSelected,
    isFolderPartialSelected: audioListModule.isFolderPartialSelected,
    selectCurrentPage: audioListModule.selectCurrentPage,
    selectAllPages: audioListModule.selectAllPages,

    // 列表操作
    fetchAudios: audioListModule.fetchAudios,
    searchAudios,
    filterAudios: audioListModule.filterAudios,
    switchView,
    applyFilters,
    resetFilters,
    toggleTag,

    // 分页
    prevPage: audioListModule.prevPage,
    nextPage: audioListModule.nextPage,
    handleGoToPage: audioListModule.handleGoToPage,
    handlePageSizeChange: audioListModule.handlePageSizeChange,

    // 上传相关
    uploadOptions: uploadModule.uploadOptions,
    uploadTasks: uploadModule.uploadTasks,
    selectedFilesForUpload: uploadModule.selectedFilesForUpload,
    fileList: uploadModule.fileList,
    uploadStatus: uploadModule.uploadStatus,
    uploadProgress: uploadModule.uploadProgress,
    currentTask: uploadModule.currentTask,
    currentUploadingFile: uploadModule.currentUploadingFile,
    isRetryingFailed: uploadModule.isRetryingFailed,
    testCaseGeneratedCount: uploadModule.testCaseGeneratedCount,
    showTestCaseGeneratedTip: uploadModule.showTestCaseGeneratedTip,
    goToTestCaseManager,
    startUploadProcess: uploadModule.startUploadProcess,
    pickFiles: () => uploadModule.pickFiles(() => audioListModule.fetchAudios()),
    handleDrop: uploadModule.handleDrop,
    pauseUploadTask: uploadModule.pauseUploadTask,
    resumeUploadTask: (taskId: string) => uploadModule.resumeUploadTask(taskId, false, () => audioListModule.fetchAudios()),
    retryFailedFiles: (taskId: string, autoSelectFiles = false) => uploadModule.retryFailedFiles(taskId, autoSelectFiles, () => audioListModule.fetchAudios()),
    removeLocalTask: uploadModule.removeLocalTask,
    dismissTask: (taskId: string) => uploadModule.dismissTask(taskId, () => audioListModule.fetchAudios()),
    checkAndResumeTasks: () => uploadModule.checkAndResumeTasks(() => audioListModule.fetchAudios()),
    pathBasename: uploadModule.pathBasename,
    folderImportOptions: uploadModule.folderImportOptions,

    // 模态框
    openUploadModal: uploadModalModule.openUploadModal,
    batchImportFromFolder: uploadModalModule.batchImportFromFolder,
    closeModal: batchOpsModule.closeModal,
    closeActiveModal: batchOpsModule.closeActiveModal,
    initModalWatchers: batchOpsModule.initModalWatchers,

    // 批量操作和单文件操作
    showConvertModal: batchOpsModule.showConvertModal,
    batchDelete: batchOpsModule.batchDelete,
    batchExport: batchOpsModule.batchExport,
    previewAudio: batchOpsModule.previewAudio,
    editMetadata: batchOpsModule.editMetadata,
    downloadAudio: batchOpsModule.downloadAudio,
    deleteAudio: batchOpsModule.deleteAudio,
    shareAudio: batchOpsModule.shareAudio,
    convertAudio: batchOpsModule.convertAudio,
    urlImportData: batchOpsModule.urlImportData,
    convertAudioInfo: batchOpsModule.convertAudioInfo,
    showAudioPlayerModal: batchOpsModule.showAudioPlayerModal,
    audioTitle: batchOpsModule.audioTitle,
    currentPreviewAudioId: batchOpsModule.currentPreviewAudioId,
    currentPreviewAudioType: batchOpsModule.currentPreviewAudioType,

    // 设备管理
    playbackDevices: deviceModule.playbackDevices,
    playbackDevicePage: deviceModule.playbackDevicePage,
    playbackDevicePages: deviceModule.playbackDevicePages,
    playbackDeviceLoading: deviceModule.playbackDeviceLoading,
    playbackDeviceHasMore: deviceModule.playbackDeviceHasMore,
    fetchPlaybackDevices: deviceModule.fetchPlaybackDevices,
    loadMorePlaybackDevices: deviceModule.loadMorePlaybackDevices,
    deviceList: deviceModule.deviceList,
    fetchDevices: deviceModule.fetchDevices,

    // 算法参数
    algorithmOptions: algorithmModule.algorithmOptions,
    fetchAlgorithmOptions: algorithmModule.fetchAlgorithmOptions,

    // 状态重置
    resetAllStates,
  };
}
