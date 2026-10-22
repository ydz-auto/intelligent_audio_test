/**
 * TestCaseListContainer —— 分组展开与筛选编排模块
 *
 * 职责：
 * 1. 编排 useTestCaseGroupExpand：分组/标签展开、懒加载、滚动哨兵
 * 2. 编排 useTestCaseFilters：筛选状态 watch 与重置逻辑
 * 3. 视图模式切换（updateViewMode）与 props.viewMode 同步
 * 4. 选中用例变化上报（updateSelectedCases）
 */
import { computed, watch, ref, onBeforeUnmount } from 'vue';
import { useTestCaseGroupExpand } from '../../../composables/testCase/useTestCaseGroupExpand';
import { useTestCaseFilters } from '../../../composables/testCase/useTestCaseFilters';
import { useTestCaseStore } from '../../../store/testCaseStore';
import { ViewMode } from '@/domain/enums';
import type { ContainerState } from './testCaseListContainer.state';

/** INT-1314：标签视图失败自动降级提示展示时长 */
const FALLBACK_NOTICE_DURATION_MS = 6_000;
/** INT-1314：连续加载超过该时长显示「数据量较大，加载较慢」提示 */
const SLOW_LOADING_THRESHOLD_MS = 10_000;

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
    searchQuery,
    // INT-526：回收站态分组展开透传 trashMode → onlyDeleted
    computed(() => props.trashMode ?? false)
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
  /** INT-1314：标签视图失败自动降级后页内提示（短暂展示，切换视图即清除） */
  const fallbackNotice = ref(false);
  let fallbackNoticeTimer: ReturnType<typeof setTimeout> | null = null;
  const clearFallbackNotice = () => {
    fallbackNotice.value = false;
    if (fallbackNoticeTimer) {
      clearTimeout(fallbackNoticeTimer);
      fallbackNoticeTimer = null;
    }
  };
  const showFallbackNotice = () => {
    clearFallbackNotice();
    fallbackNotice.value = true;
    fallbackNoticeTimer = setTimeout(() => {
      fallbackNotice.value = false;
    }, FALLBACK_NOTICE_DURATION_MS);
  };

  /** INT-1314：首屏连续加载超过阈值显示「加载较慢」提示（替代长时间空白无感知） */
  const slowLoading = ref(false);
  let slowLoadingTimer: ReturnType<typeof setTimeout> | null = null;

  const updateViewMode = (mode: 'group' | 'tag') => {
    innerViewMode.value = mode;
    emit('update:viewMode', mode);
    // 手动切换视图时清除降级提示
    clearFallbackNotice();
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
      clearFallbackNotice();
    }
  });

  // INT-1314：标签视图首拉失败 → 自动降级到分组视图 + 页内提示
  // （tagViewError 由 store fetchTagView 置空后重写，每次失败都能重新触发）
  watch(() => props.tagViewError, (tagErr) => {
    if (tagErr && innerViewMode.value === ViewMode.TAG) {
      updateViewMode('group');
      showFallbackNotice();
    }
  });

  // INT-1314：首屏骨架屏的「加载较慢」提示——连续加载超过阈值才出现，数据到达即消失
  watch(() => props.isLoading ?? false, (loading) => {
    if (loading) {
      if (slowLoadingTimer) clearTimeout(slowLoadingTimer);
      slowLoadingTimer = setTimeout(() => {
        slowLoading.value = true;
      }, SLOW_LOADING_THRESHOLD_MS);
    } else {
      if (slowLoadingTimer) {
        clearTimeout(slowLoadingTimer);
        slowLoadingTimer = null;
      }
      slowLoading.value = false;
    }
  });

  onBeforeUnmount(() => {
    clearFallbackNotice();
    if (slowLoadingTimer) {
      clearTimeout(slowLoadingTimer);
      slowLoadingTimer = null;
    }
  });

  // INT-215/S3：回收站模式进出时重置前端分组分页（对照报告侧 currentPage=1 口径），
  // 数据集整体切换（活跃↔已删）同时清空陈旧选中集
  watch(() => props.trashMode, () => {
    currentPage.value = 1;
    selectedCases.value = [];
    // INT-526：进出回收站清空已加载分组用例缓存——否则普通态展开过的分组在回收站态
    // 复用活跃用例缓存（loadedGroupCases 非空跳过重拉），已删用例仍不可见
    useTestCaseStore().resetGroupCache();
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
    updateViewMode,
    fallbackNotice,
    slowLoading
  };
}

/** 分组展开/筛选编排模块类型（由工厂推断） */
export type GroupExpandModule = ReturnType<typeof createGroupExpandModule>;