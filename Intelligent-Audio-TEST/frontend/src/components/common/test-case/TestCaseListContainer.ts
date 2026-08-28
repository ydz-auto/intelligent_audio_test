import { ref, computed, watch, onMounted, onUnmounted, onBeforeUnmount, nextTick } from 'vue';
import { playbackApi, algorithmApi, evaluationApi } from '../../../utils/api';
import { normalizeTestCaseConfig } from '../../../utils/utils';
import { useTestCaseStore } from '../../../store/testCaseStore';
import { useTestCaseBatchActions } from '../../../composables/testCase/useTestCaseBatchActions';
import { useTestCaseAudioPreview } from '../../../composables/testCase/useTestCaseAudioPreview';
import { useTestCaseGroupExpand } from '../../../composables/testCase/useTestCaseGroupExpand';
import { useTestCaseFilters } from '../../../composables/testCase/useTestCaseFilters';
import type { TestCase, PaginationInfo, PlaybackDevice } from '../../../shared/types';

export function useTestCaseListContainer(props: any, emit: any) {
  // ===== 本地状态（组件级，跨 composable 共享） =====
  const selectedCases = ref<(string | number)[]>([]);
  const playbackDevices = ref<PlaybackDevice[]>([]);
  const algorithmOptions = ref<{ value: string; label: string }[]>([]);

  // 视图模式：'group' 分组视图 | 'tag' 标签视图
  const innerViewMode = ref<'group' | 'tag'>(props.viewMode || 'group');

  // 筛选状态在组件级声明，供 groupExpand / filters / batchActions 共享同一份响应式状态
  const searchQuery = ref('');
  const testTypeFilter = ref('all');
  const algorithmTypeFilter = ref('all');
  const groupFilter = ref('all');
  const tagFilter = ref('all');
  const sortBy = ref('count');
  const sortOrder = ref('desc');
  const dimensionFilter = ref<number | 'all'>('all');
  const dimensionOptions = ref<{ id: number; name: string }[]>([]);

  // hasMoreGroups 由分组分页计算属性驱动，先占位再被 composable 引用
  const hasMoreGroups = ref(true);

  // ===== 分组展开/加载 composable =====
  // 预先创建占位 ref，待分组/标签分页计算属性定义后再同步。
  const paginatedGroupsRef = ref<string[]>([]);
  const paginatedTagsRef = ref<string[]>([]);
  const hasMoreTagsRef = ref(false);

  const groupExpandModule = useTestCaseGroupExpand(
    algorithmTypeFilter,
    testTypeFilter,
    innerViewMode,
    paginatedGroupsRef,
    paginatedTagsRef,
    hasMoreGroups,
    hasMoreTagsRef,
    computed(() => props.tagViewLoading ?? false),
    () => emit('loadMoreTags'),
    dimensionFilter,
    searchQuery
  );

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
    cleanupObserver
  } = groupExpandModule;

  // ===== 筛选/搜索 composable =====
  // 筛选状态 ref 在组件级声明，这里传入 composable 用于管理 watch / reset 逻辑
  const filtersModule = useTestCaseFilters(
    props,
    {
      searchQuery,
      testTypeFilter,
      algorithmTypeFilter,
      groupFilter,
      tagFilter,
      sortBy,
      sortOrder,
      dimensionFilter
    },
    {
      currentPage,
      innerViewMode,
      emitTagFilterChange: (filters) => emit('tagFilterChange', filters),
      emitGroupFilterChange: (filters) => emit('groupFilterChange', filters)
    }
  );

  const {
    debouncedSearchQuery,
    resetFilters
  } = filtersModule;

  // ===== 计算属性：分组视图 =====
  const availableGroups = computed(() => {
    console.log('[availableGroups] props.testCaseGroups:', props.testCaseGroups);
    console.log('[availableGroups] props.testCaseGroups keys:', Object.keys(props.testCaseGroups || {}));
    return Object.keys(props.testCaseGroups || {});
  });

  const filteredTestCases = computed(() => {
    const result: Record<string, TestCase[]> = {};
    const testCasesData = props.testCaseGroups || {};

    const query = debouncedSearchQuery.value?.toLowerCase() || '';
    const testType = testTypeFilter.value;
    const algorithmType = algorithmTypeFilter.value;
    const selectedGroup = groupFilter.value;
    const selectedTag = tagFilter.value;

    Object.keys(testCasesData).forEach((group: string) => {
      if (selectedGroup !== 'all' && group !== selectedGroup) {
        return;
      }

      const groupCases = testCasesData[group] || [];
      if (groupCases.length === 0) {
        result[group] = [];
        return;
      }

      let filtered = groupCases;

      if (query) {
        filtered = filtered.filter((testCase: TestCase) => {
          if (!testCase) return false;
          const idStr = String(testCase.id || '').toLowerCase();
          const name = (testCase.name || '').toLowerCase();
          const desc = (testCase.description || '').toLowerCase();

          if (idStr.includes(query) || name.includes(query) || desc.includes(query)) {
            return true;
          }

          if (testCase.tags && testCase.tags.length > 0) {
            return testCase.tags.some((tag: any) => {
              const tagName = typeof tag === 'string' ? tag : (tag.name || '');
              return tagName.toLowerCase().includes(query);
            });
          }
          return false;
        });
      }

      if (testType !== 'all') {
        filtered = filtered.filter((testCase: TestCase) => {
          if (!testCase) return false;
          const config = testCase.config || {};
          const types = testCase.type || config.type;

          if (types) {
            const typeArray = Array.isArray(types) ? types : [types];
            const normalizedTypes = typeArray.map(t => String(t).toLowerCase());

            if (testType === 'api') {
              return normalizedTypes.includes('api') || normalizedTypes.includes('apitest');
            } else if (testType === 'e2e') {
              return normalizedTypes.includes('e2e') || normalizedTypes.includes('e2etest');
            }
            return normalizedTypes.includes(testType.toLowerCase());
          }

          const normalizedConfig = normalizeTestCaseConfig(config);
          const rounds = normalizedConfig.rounds || [];
          const hasAudios = rounds.some((r: any) => Array.isArray(r.audios) && r.audios.length > 0);
          // In dual-record architecture, test_type is at record level
          const recordTestType = (testCase as any).test_type || '';
          if (recordTestType) {
            if (testType === 'api') return recordTestType === 'api';
            if (testType === 'e2e') return recordTestType === 'e2e';
          }
          // Fallback: if has audios, assume matches current filter
          return hasAudios;
        });
      }

      if (algorithmType !== 'all') {
        filtered = filtered.filter((testCase: TestCase) => {
          return testCase && testCase.algorithmType === algorithmType;
        });
      }

      if (selectedTag !== 'all') {
        filtered = filtered.filter((testCase: TestCase) => {
          if (!testCase || !testCase.tags) return false;
          return testCase.tags.some((tag: any) => {
            const tagName = typeof tag === 'string' ? tag : tag.name;
            return tagName === selectedTag;
          });
        });
      }

      result[group] = filtered;
    });

    return result;
  });

  // ===== 批量操作 composable =====
  const batchActionsModule = useTestCaseBatchActions(
    computed(() => filteredTestCases.value),
    selectedCases,
    algorithmTypeFilter,
    computed(() => filteredTagCases.value)
  );

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
    handleTagUpdateSPL,
    handleTagUpdatePlaybackDevice,
    handleTagUpdateNoise,
    handleTagUpdateAlgorithmParams,
    handleTagUpdateDimensions,
    handleTagAdjustGroup,
    handleTagAutoGenerateName,
    handleTagUpdateTags,
    handleTagRefreshReference
  } = batchActionsModule;

  // ===== 音频预览 composable =====
  const audioPreviewModule = useTestCaseAudioPreview(
    (testCase) => emit('openEditModal', testCase),
    (testCase) => emit('deleteTestCase', testCase),
    selectedCases
  );

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
  } = audioPreviewModule;

  // ===== 视图模式切换 =====
  const updateViewMode = (mode: 'group' | 'tag') => {
    innerViewMode.value = mode;
    emit('update:viewMode', mode);
    // 切换视图时重置展开状态和选中状态
    selectedCases.value = [];
    // 重置前端分页（分组视图使用）
    currentPage.value = 1;
    if (mode === 'tag') {
      expandedCategories.value = {};
    } else {
      expandedTagCategories.value = {};
    }
  };
  watch(() => props.viewMode, (newMode) => {
    if (newMode && newMode !== innerViewMode.value) {
      innerViewMode.value = newMode;
    }
  });

  // ===== 选中用例上报 =====
  watch(selectedCases, (newValue) => {
    emit('updateSelectedCases', newValue);
  }, { deep: true });

  const formattedTestCases = computed(() => {
    const result: Record<string, (TestCase & { lastEditTime?: string; selected: boolean })[]> = {};
    const filteredValue = filteredTestCases.value;

    Object.keys(filteredValue).forEach((group: string) => {
      result[group] = filteredValue[group]
        .filter((testCase: TestCase) => testCase && testCase.id)
        .map((testCase: TestCase) => ({
          ...testCase,
          lastEditTime: testCase.updatedAt || testCase.createdAt,
          selected: selectedCases.value.includes(testCase.id)
        }));
    });
    return result;
  });

  const groupSelectionStates = computed(() => {
    const result: Record<string, boolean> = {};
    const filteredValue = filteredTestCases.value;
    const selectedSet = new Set(selectedCases.value.map(id => String(id)));

    Object.keys(filteredValue).forEach((group: string) => {
      const groupCases = filteredValue[group];
      // 用后端总数判断全选状态，而非已加载的用例数
      const totalCount = getGroupTotalCount(group);
      if (totalCount === 0) {
        result[group] = false;
      } else {
        // 统计该分组下已选中的用例数
        const selectedInGroup = groupCases.filter((tc: TestCase) => tc && tc.id && selectedSet.has(String(tc.id))).length;
        // 如果已加载数 < 总数，只能判断部分选中；只有全部加载且全选才算全选
        // 但 toggleGroupSelection 会从后端拉全量ID，所以已加载的用例数可能 < 选中数
        // 此处用 totalCount === selectedInGroup 判断不够准确（selectedInGroup 只数已加载的）
        // 改为：如果 selectedCases 长度 >= totalCount 且已加载的全部选中，则全选
        result[group] = groupCases.length > 0 && groupCases
          .filter((caseItem: TestCase) => caseItem && caseItem.id)
          .every((caseItem: TestCase) => selectedSet.has(String(caseItem.id)))
          && selectedInGroup >= totalCount;
      }
    });

    return result;
  });

  const getGroupDurationStats = (group: string) => {
    const cases = filteredTestCases.value[group] || [];
    let totalDuration = 0;

    cases.forEach((tc: TestCase) => {
      if (tc.totalDuration) totalDuration += tc.totalDuration;
    });

    return { totalDuration };
  };

  const formatGroupDuration = (seconds: number): string => {
    if (!seconds || seconds === 0) return '0s';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    if (minutes < 60) return `${minutes}m${remainingSeconds > 0 ? ` ${remainingSeconds.toFixed(0)}s` : ''}`;
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    return `${hours}h ${remainingMinutes}m`;
  };

  const getTagDurationStats = (tagName: string) => {
    const cases = filteredTagCases.value[tagName] || [];
    let totalDuration = 0;
    cases.forEach((tc: TestCase) => {
      if (tc.totalDuration) totalDuration += tc.totalDuration;
    });
    return { totalDuration };
  };

  const sortedGroups = computed(() => {
    const filteredValue = filteredTestCases.value;
    const groups = Object.keys(filteredValue);
    const currentSortBy = sortBy.value;
    const currentSortOrder = sortOrder.value;

    return groups.sort((a, b) => {
      let result = 0;

      switch (currentSortBy) {
        case 'count':
          // 按分组真实用例总数排序（来自后端 test_case_count），而非已加载数量，
          // 否则展开分组触发懒加载后已加载数量从 0 跳变，分组会被降序重排到顶部。
          result = getGroupTotalCount(b) - getGroupTotalCount(a);
          return currentSortOrder === 'asc' ? result * -1 : result;
        case 'name':
          result = a.localeCompare(b, 'zh-CN');
          return currentSortOrder === 'desc' ? result * -1 : result;
        case 'createTime':
          const aCases = filteredValue[a] || [];
          const bCases = filteredValue[b] || [];

          if (aCases.length === 0 && bCases.length === 0) {
            result = a.localeCompare(b, 'zh-CN');
            return currentSortOrder === 'desc' ? result * -1 : result;
          } else if (aCases.length === 0) {
            return currentSortOrder === 'asc' ? 1 : -1;
          } else if (bCases.length === 0) {
            return currentSortOrder === 'asc' ? -1 : 1;
          }

          const aTime = aCases[0]?.createdAt ? new Date(aCases[0].createdAt).getTime() : 0;
          const bTime = bCases[0]?.createdAt ? new Date(bCases[0].createdAt).getTime() : 0;
          result = bTime - aTime;
          return currentSortOrder === 'asc' ? result * -1 : result;
        default:
          result = getGroupTotalCount(b) - getGroupTotalCount(a);
          return currentSortOrder === 'asc' ? result * -1 : result;
      }
    });
  });

  // Paginated groups computed property
  const paginatedGroups = computed(() => {
    const allGroups = sortedGroups.value;
    const endIndex = currentPage.value * itemsPerPage.value;
    return allGroups.slice(0, endIndex);
  });

  // Pagination info computed property
  const paginationInfo = computed(() => {
    const totalItems = sortedGroups.value.length;
    const totalPages = Math.ceil(totalItems / itemsPerPage.value);
    hasMoreGroups.value = paginatedGroups.value.length < totalItems;

    return {
      totalItems,
      totalPages,
      currentPage: currentPage.value,
      itemsPerPage: itemsPerPage.value,
      hasPrev: currentPage.value > 1,
      hasNext: currentPage.value < totalPages
    };
  });

  // ===== 计算属性：标签视图 =====
  const availableTags = computed(() => {
    return Object.keys(props.tagViewData || {});
  });

  const filteredTagCases = computed(() => {
    const result: Record<string, TestCase[]> = {};
    const tagData = props.tagViewData || {};

    const selectedTag = tagFilter.value;

    // 后端已对 keyword/testType/algorithmType 做筛选，前端只做标签选择器过滤
    Object.keys(tagData).forEach((tagName: string) => {
      if (selectedTag !== 'all' && tagName !== selectedTag) {
        return;
      }
      result[tagName] = tagData[tagName] || [];
    });

    return result;
  });

  const formattedTagCases = computed(() => {
    const result: Record<string, (TestCase & { lastEditTime?: string; selected: boolean })[]> = {};
    const filteredValue = filteredTagCases.value;

    Object.keys(filteredValue).forEach((tagName: string) => {
      result[tagName] = filteredValue[tagName]
        .filter((testCase: TestCase) => testCase && testCase.id)
        .map((testCase: TestCase) => ({
          ...testCase,
          lastEditTime: testCase.updatedAt || testCase.createdAt,
          selected: selectedCases.value.includes(testCase.id)
        }));
    });
    return result;
  });

  const sortedTags = computed(() => {
    const filteredValue = filteredTagCases.value;
    const tagsList = Object.keys(filteredValue);
    const currentSortBy = sortBy.value;
    const currentSortOrder = sortOrder.value;

    return tagsList.sort((a, b) => {
      let result = 0;
      switch (currentSortBy) {
        case 'count':
          result = (filteredValue[b]?.length || 0) - (filteredValue[a]?.length || 0);
          return currentSortOrder === 'asc' ? result * -1 : result;
        case 'name':
          result = a.localeCompare(b, 'zh-CN');
          return currentSortOrder === 'desc' ? result * -1 : result;
        case 'createTime':
          const aCases = filteredValue[a] || [];
          const bCases = filteredValue[b] || [];
          const aTime = aCases[0]?.createdAt ? new Date(aCases[0].createdAt).getTime() : 0;
          const bTime = bCases[0]?.createdAt ? new Date(bCases[0].createdAt).getTime() : 0;
          result = bTime - aTime;
          return currentSortOrder === 'asc' ? result * -1 : result;
        default:
          result = (filteredValue[b]?.length || 0) - (filteredValue[a]?.length || 0);
          return currentSortOrder === 'asc' ? result * -1 : result;
      }
    });
  });

  // 标签视图是否还有更多未从后端加载的标签（基于后端分页信息）
  const hasMoreTagsFromBackend = computed(() => {
    const pagination = props.tagViewPagination;
    if (!pagination) return false;
    return pagination.page < pagination.pages;
  });

  // 兼容旧引用：标签视图的前端分页标志，后端分页模式下始终为 false（由 hasMoreTagsFromBackend 接管）
  const hasMoreTags = computed(() => false);

  // 同步分页结果到 groupExpand composable 引用（用于哨兵 watch）
  watch([paginatedGroups, hasMoreTagsFromBackend], () => {
    paginatedGroupsRef.value = paginatedGroups.value;
    paginatedTagsRef.value = sortedTags.value;
    hasMoreTagsRef.value = hasMoreTagsFromBackend.value;
  }, { immediate: true });

  // ===== 用例卡片操作 =====
  const getTestCaseActions = () => {
    return [
      { id: 'preview', icon: 'fa-play', title: '预览音频' },
      { id: 'copy', icon: 'fa-copy', title: '复制用例' },
      { id: 'edit', icon: 'fa-edit', title: '编辑用例' },
      { id: 'delete', icon: 'fa-trash', title: '删除用例' }
    ];
  };

  const toggleTestCaseSelection = (caseId: string | number) => {
    const index = selectedCases.value.indexOf(caseId);
    if (index > -1) {
      selectedCases.value.splice(index, 1);
    } else {
      selectedCases.value.push(caseId);
    }
  };

  const toggleGroupSelection = async (group: string) => {
    const allSelected = groupSelectionStates.value[group];
    const store = useTestCaseStore();
    const algorithmType = algorithmTypeFilter.value === 'all' ? undefined : algorithmTypeFilter.value;
    const keyword = debouncedSearchQuery.value || undefined;
    const testType = testTypeFilter.value !== 'all' ? testTypeFilter.value : undefined;
    const dimensionId = dimensionFilter.value !== 'all' ? dimensionFilter.value : undefined;

    // 始终从后端拉全量ID，确保取消全选时也能移除未加载的用例
    const allIds = await store.fetchCaseIdsByFilter({
      group,
      testType,
      search: keyword,
      algorithmType,
      dimensionId,
    });

    if (allSelected) {
      // 取消全选：移除该分组下全量用例ID
      const idSet = new Set(allIds);
      selectedCases.value = selectedCases.value.filter(id => !idSet.has(id));
    } else {
      // 全选：添加该分组下全量用例ID
      allIds.forEach((id: string | number) => {
        if (!selectedCases.value.includes(id)) {
          selectedCases.value.push(id);
        }
      });
    }
  };

  const tagSelectionStates = computed(() => {
    const result: Record<string, boolean> = {};
    const filteredValue = filteredTagCases.value;
    const selectedSet = new Set(selectedCases.value.map(id => String(id)));

    Object.keys(filteredValue).forEach((tagName: string) => {
      const tagCases = filteredValue[tagName];
      const tagCaseCount = tagCases.length;
      if (tagCaseCount === 0) {
        result[tagName] = false;
      } else {
        const selectedInTag = tagCases.filter((tc: TestCase) => tc && tc.id && selectedSet.has(String(tc.id))).length;
        result[tagName] = tagCases
          .filter((caseItem: TestCase) => caseItem && caseItem.id)
          .every((caseItem: TestCase) => selectedSet.has(String(caseItem.id)))
          && selectedInTag >= tagCaseCount;
      }
    });

    return result;
  });

  const toggleTagSelection = async (tagName: string) => {
    const allSelected = tagSelectionStates.value[tagName];
    const store = useTestCaseStore();
    const algorithmType = algorithmTypeFilter.value === 'all' ? undefined : algorithmTypeFilter.value;
    const keyword = debouncedSearchQuery.value || undefined;
    const testType = testTypeFilter.value !== 'all' ? testTypeFilter.value : undefined;
    const dimensionId = dimensionFilter.value !== 'all' ? dimensionFilter.value : undefined;

    // 始终从后端拉全量ID，确保取消全选时也能移除未加载的用例
    const allIds = await store.fetchCaseIdsByFilter({
      tag: tagName,
      testType,
      search: keyword,
      algorithmType,
      dimensionId,
    });

    if (allSelected) {
      // 取消全选：移除该标签下全量用例ID
      const idSet = new Set(allIds);
      selectedCases.value = selectedCases.value.filter(id => !idSet.has(id));
    } else {
      // 全选：添加该标签下全量用例ID
      allIds.forEach((id: string | number) => {
        if (!selectedCases.value.includes(id)) {
          selectedCases.value.push(id);
        }
      });
    }
  };

  const handleGroupDelete = (group: string) => {
    emit('deleteGroup', group);
  };

  // ===== 批量菜单开关 =====
  const openBatchMenuGroup = ref<string | null>(null);

  const toggleBatchMenu = (group: string) => {
    if (openBatchMenuGroup.value === group) {
      openBatchMenuGroup.value = null;
    } else {
      openBatchMenuGroup.value = group;
    }
  };

  const closeAllBatchMenus = () => {
    openBatchMenuGroup.value = null;
  };

  // ===== 数据加载 =====
  async function loadAlgorithmOptions() {
    try {
      const data = await algorithmApi.getOptions();
      algorithmOptions.value = [
        { value: 'all', label: '所有算法' },
        ...(data?.algorithms || []).map((algo: any) => ({
          value: algo.value,
          label: algo.name || algo.value
        }))
      ];
    } catch (error) {
      console.error('加载算法选项失败:', error);
      algorithmOptions.value = [
        { value: 'all', label: '所有算法' },
        { value: 'translation', label: '翻译' },
        { value: 'asr', label: 'ASR识别' },
        { value: 'speaker_recognition', label: '说话人识别' },
        { value: 'tts', label: '语音合成' }
      ];
    }
  }

  async function loadDimensionOptions() {
    try {
      const data = await evaluationApi.getOptions();
      dimensionOptions.value = (data?.dimensions || [])
        .filter((d: any) => d.dimension_type !== 'sub')
        .map((d: any) => ({ id: d.id, name: d.name }));
    } catch (error) {
      console.error('加载评估维度选项失败:', error);
      dimensionOptions.value = [];
    }
  }

  const loadPlaybackDevices = async () => {
    try {
      const result = await playbackApi.getAll();
      playbackDevices.value = (result as any).items || [];
    } catch (error) {
      console.error('加载播放设备列表失败:', error);
      playbackDevices.value = [];
    }
  };

  // ===== 键盘快捷键 =====
  const handleGlobalKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      if (showAudioTypeModal.value) {
        handleCloseAudioTypeModal();
      }
      if (showAudioPreviewModal.value) {
        handleAudioPreviewModalClose();
      }
      if (showPlaybackDeviceModal.value) {
        showPlaybackDeviceModal.value = false;
      }
      if (showAudioPlayer.value) {
        handleAudioPlayerClose();
      }
    }
  };

  // ===== 生命周期 =====
  onMounted(() => {
    document.addEventListener('click', closeAllBatchMenus);
    window.addEventListener('keydown', handleGlobalKeyDown);
    setupLoadMoreObserver();
    Promise.all([
      loadPlaybackDevices(),
      loadAlgorithmOptions(),
      loadDimensionOptions()
    ]);
  });

  onUnmounted(() => {
    document.removeEventListener('click', closeAllBatchMenus);
  });

  onBeforeUnmount(() => {
    window.removeEventListener('keydown', handleGlobalKeyDown);
    cleanupObserver();
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
