/**
 * TestCaseListContainer —— 分组展开与筛选编排模块
 *
 * 职责：
 * 1. 编排 useTestCaseGroupExpand：分组/标签展开、懒加载、滚动哨兵
 * 2. 编排 useTestCaseFilters：筛选状态 watch 与重置逻辑
 * 3. 视图模式切换（updateViewMode）与 props.viewMode 同步
 * 4. 选中用例变化上报（updateSelectedCases）
 */
import { computed, watch } from 'vue';
import { useTestCaseGroupExpand } from '../../../composables/testCase/useTestCaseGroupExpand';
import { useTestCaseFilters } from '../../../composables/testCase/useTestCaseFilters';
import { ViewMode } from '@/domain/enums';
import type { ContainerState } from './testCaseListContainer.state';

/** 创建分组展开/筛选编排模块 */
export function createGroupExpandModule(props: any, emit: any, state: ContainerState) {
  const {
    algorithmTypeFilter,
    testTypeFilter,
    innerViewMode,
    searchQuery,
    dimensionFilter,
    groupFilter,
    tagFilter,
    sortBy,
    sortOrder,
    paginatedGroupsRef,
    paginatedTagsRef,
    hasMoreGroups,
    hasMoreTagsRef,
    selectedCases
  } = state;

  // ===== 分组展开/加载 composable =====
  // 预先创建占位 ref，待分组/标签分页计算属性定义后再同步。
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
  // 筛选状态 ref 在容器级声明，这里传入 composable 用于管理 watch / reset 逻辑
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

  const { debouncedSearchQuery, resetFilters } = filtersModule;

  // ===== 视图模式切换 =====
  const updateViewMode = (mode: 'group' | 'tag') => {
    innerViewMode.value = mode;
    emit('update:viewMode', mode);
    // 切换视图时重置展开状态和选中状态
    selectedCases.value = [];
    // 重置前端分页（分组视图使用）
    currentPage.value = 1;
    if (mode === ViewMode.TAG) {
      expandedCategories.value = {};
    } else {
      expandedTagCategories.value = {};
    }
  };
  // props.viewMode 外部变更时同步内部视图模式
  watch(() => props.viewMode, (newMode) => {
    if (newMode && newMode !== innerViewMode.value) {
      innerViewMode.value = newMode;
    }
  });

  // INT-215/S3：回收站模式进出时重置前端分组分页（对照报告侧 currentPage=1 口径），
  // 数据集整体切换（活跃↔已删）同时清空陈旧选中集
  watch(() => props.trashMode, () => {
    currentPage.value = 1;
    selectedCases.value = [];
  });

  // ===== 选中用例上报 =====
  watch(selectedCases, (newValue) => {
    emit('updateSelectedCases', newValue);
  }, { deep: true });

  return {
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
  };
}

/** 分组展开/筛选编排模块类型（由工厂推断） */
export type GroupExpandModule = ReturnType<typeof createGroupExpandModule>;