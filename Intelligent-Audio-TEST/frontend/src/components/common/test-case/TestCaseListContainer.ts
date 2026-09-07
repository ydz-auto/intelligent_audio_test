/**
 * TestCaseListContainer —— 组合根（Composition Root）
 *
 * 原单一超大文件已按职责拆分为 testCaseListContainer.*.ts 子模块：
 * - state       容器级共享响应式状态
 * - groupExpand 分组展开/筛选编排
 * - groupView   分组视图计算属性
 * - tagView     标签视图计算属性
 * - selection   用例选择与批量菜单
 * - lifecycle   数据加载与生命周期
 * 本文件仅负责编排各模块与外部 composable（批量操作、音频预览），并聚合原有全部具名导出，
 * 模块路径与导出面保持不变，消费方零改动。
 */
import { computed, watch } from 'vue';
import { useTestCaseBatchActions } from '../../../composables/testCase/useTestCaseBatchActions';
import { useTestCaseAudioPreview } from '../../../composables/testCase/useTestCaseAudioPreview';
import { createContainerState } from './testCaseListContainer.state';
import { createGroupExpandModule } from './testCaseListContainer.groupExpand';
import { createGroupViewData } from './testCaseListContainer.groupView';
import { createTagViewData } from './testCaseListContainer.tagView';
import { createSelectionModule } from './testCaseListContainer.selection';
import { createLifecycleModule } from './testCaseListContainer.lifecycle';

export function useTestCaseListContainer(props: any, emit: any) {
  // 1. 容器级共享状态（选择集、筛选器、视图模式、分页占位等）
  const state = createContainerState(props);
  const {
    selectedCases,
    algorithmTypeFilter,
    playbackDevices,
    algorithmOptions,
    innerViewMode,
    searchQuery,
    testTypeFilter,
    groupFilter,
    tagFilter,
    sortBy,
    sortOrder,
    dimensionFilter,
    dimensionOptions,
    hasMoreGroups,
    paginatedGroupsRef,
    paginatedTagsRef,
    hasMoreTagsRef
  } = state;

  // 2. 分组展开 + 筛选编排
  const {
    expandedCategories,
    expandedTagCategories,
    currentPage,
    itemsPerPage,
    isLoadingMore,
    listContainerRef,
    loadMoreTriggerRef,
    toggleCategory,
    toggleTagCategory,
    isGroupLoading,
    hasMoreGroupCases,
    getGroupTotalCount,
    loadMoreCases,
    loadMoreGroups,
    handleScroll,
    setupLoadMoreObserver,
    cleanupObserver,
    debouncedSearchQuery,
    resetFilters,
    updateViewMode
  } = createGroupExpandModule(props, emit, state);

  // 3. 分组视图 / 标签视图计算属性
  const {
    availableGroups,
    filteredTestCases,
    formattedTestCases,
    groupSelectionStates,
    getGroupDurationStats,
    formatGroupDuration,
    sortedGroups,
    paginatedGroups,
    paginationInfo
  } = createGroupViewData(props, state, {
    debouncedSearchQuery,
    getGroupTotalCount,
    currentPage,
    itemsPerPage
  });

  const {
    availableTags,
    filteredTagCases,
    formattedTagCases,
    sortedTags,
    hasMoreTagsFromBackend,
    hasMoreTags,
    getTagDurationStats
  } = createTagViewData(props, state);

  // ===== 批量操作 composable =====
  const {
    handleCopyGroup,
    handleUpdateAlgorithmParams,
    handleUpdatePlaybackDevice,
    handleUpdateSPL,
    handleAdjustGroup,
    handleUpdateDimensions,
    handleUpdateNoise,
    handleAutoGenerateName,
    handleUpdateTags,
    handleRefreshReference,
    handleTagDelete,
    handleTagCopyGroup,
    handleTagUpdateSPL,
    handleTagUpdatePlaybackDevice,
    handleTagUpdateNoise,
    handleTagUpdateAlgorithmParams,
    handleTagUpdateDimensions,
    handleTagAdjustGroup,
    handleTagAutoGenerateName,
    handleTagUpdateTags,
    handleTagRefreshReference
  } = useTestCaseBatchActions(
    computed(() => filteredTestCases.value),
    selectedCases,
    algorithmTypeFilter,
    computed(() => filteredTagCases.value)
  );

  // ===== 音频预览 composable =====
  const {
    showAudioPlayer,
    currentTestCaseCaseId,
    showAudioTypeModal,
    currentTestCase,
    currentHasAPIConfig,
    currentHasE2eConfig,
    selectedAudioType,
    showAudioPreviewModal,
    previewPlaybackMode,
    showPlaybackDeviceModal,
    handleCloseAudioTypeModal,
    selectAudioType,
    handleAudioPreviewModalClose,
    handleAudioPreviewConfirm,
    handleAudioPlayerClose,
    handleAction
  } = useTestCaseAudioPreview(
    (testCase) => emit('openEditModal', testCase),
    (testCase) => emit('deleteTestCase', testCase),
    selectedCases
  );

  // 4. 用例选择与批量菜单
  const {
    getTestCaseActions,
    toggleTestCaseSelection,
    toggleGroupSelection,
    tagSelectionStates,
    toggleTagSelection,
    handleGroupDelete,
    openBatchMenuGroup,
    toggleBatchMenu,
    closeAllBatchMenus
  } = createSelectionModule(props, emit, state, {
    debouncedSearchQuery,
    groupSelectionStates,
    filteredTagCases
  });

  // 同步分页结果到 groupExpand composable 引用（用于哨兵 watch）
  watch([paginatedGroups, hasMoreTagsFromBackend], () => {
    paginatedGroupsRef.value = paginatedGroups.value;
    paginatedTagsRef.value = sortedTags.value;
    hasMoreTagsRef.value = hasMoreTagsFromBackend.value;
  }, { immediate: true });

  // 5. 数据加载与生命周期（含全局快捷键、滚动哨兵、选项加载）
  createLifecycleModule(props, emit, state, {
    setupLoadMoreObserver,
    cleanupObserver,
    closeAllBatchMenus,
    audioPreview: {
      showAudioTypeModal,
      handleCloseAudioTypeModal,
      showAudioPreviewModal,
      handleAudioPreviewModalClose,
      showPlaybackDeviceModal,
      showAudioPlayer,
      handleAudioPlayerClose
    }
  });

  return {
    // props 暴露给模板的别名
    tags: props.tags,
    isLoading: props.isLoading,
    // 本地状态
    selectedCases,
    playbackDevices,
    algorithmOptions,
    innerViewMode,
    searchQuery,
    testTypeFilter,
    algorithmTypeFilter,
    groupFilter,
    tagFilter,
    sortBy,
    sortOrder,
    dimensionFilter,
    dimensionOptions,
    hasMoreGroups,
    // 分组展开
    expandedCategories,
    expandedTagCategories,
    currentPage,
    itemsPerPage,
    isLoadingMore,
    listContainerRef,
    loadMoreTriggerRef,
    toggleCategory,
    toggleTagCategory,
    isGroupLoading,
    hasMoreGroupCases,
    getGroupTotalCount,
    loadMoreCases,
    loadMoreGroups,
    handleScroll,
    // 筛选
    resetFilters,
    // 批量操作
    handleCopyGroup,
    handleUpdateAlgorithmParams,
    handleUpdatePlaybackDevice,
    handleUpdateSPL,
    handleAdjustGroup,
    handleUpdateDimensions,
    handleUpdateNoise,
    handleAutoGenerateName,
    handleUpdateTags,
    handleRefreshReference,
    // 标签视图级操作
    handleTagDelete,
    handleTagCopyGroup,
    // 标签视图批量操作
    handleTagUpdateSPL,
    handleTagUpdatePlaybackDevice,
    handleTagUpdateNoise,
    handleTagUpdateAlgorithmParams,
    handleTagUpdateDimensions,
    handleTagAdjustGroup,
    handleTagAutoGenerateName,
    handleTagUpdateTags,
    handleTagRefreshReference,
    // 音频预览
    showAudioPlayer,
    currentTestCaseCaseId,
    showAudioTypeModal,
    currentTestCase,
    currentHasAPIConfig,
    currentHasE2eConfig,
    selectedAudioType,
    showAudioPreviewModal,
    previewPlaybackMode,
    handleCloseAudioTypeModal,
    selectAudioType,
    handleAudioPreviewModalClose,
    handleAudioPreviewConfirm,
    handleAudioPlayerClose,
    handleAction,
    // 视图模式
    updateViewMode,
    // 计算属性：分组视图
    availableGroups,
    filteredTestCases,
    formattedTestCases,
    groupSelectionStates,
    getGroupDurationStats,
    formatGroupDuration,
    sortedGroups,
    paginatedGroups,
    paginationInfo,
    // 计算属性：标签视图
    availableTags,
    filteredTagCases,
    formattedTagCases,
    sortedTags,
    hasMoreTagsFromBackend,
    hasMoreTags,
    getTagDurationStats,
    // 用例操作
    getTestCaseActions,
    toggleTestCaseSelection,
    toggleGroupSelection,
    tagSelectionStates,
    toggleTagSelection,
    handleGroupDelete,
    // 批量菜单
    openBatchMenuGroup,
    toggleBatchMenu
  }
}