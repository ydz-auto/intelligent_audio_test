import { ref, onMounted, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useTestCaseCard } from '../../composables/testCase/useTestCaseCard';
import { useTestCaseStore } from '../../store/testCaseStore';
import { useDeleteConfirm } from '../../composables/modal/useDeleteConfirm';
import type { TestCase, ModalSaveData } from '../../shared/types';

export function useTestCaseManager() {
  const {
    formData,
    groupFormData,
    editingTestCase,
    editingGroup,
    openAddTestCaseModal,
    openEditTestCaseModal,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
    handleModalSave,
    handleTestCaseAction
  } = useTestCaseCard();

  const store = useTestCaseStore();
  const { testCaseGroups, tagViewData, tags, paginationInfo, isLoading, tagViewPagination } = storeToRefs(store);
  const { fetchTestCases, fetchTagView, deleteGroup: deleteGroupFromStore, deleteTestCase } = store;

  // 视图模式：'group' 分组视图 | 'tag' 标签视图
  const viewMode = ref<'group' | 'tag'>('group');

  // 当前筛选条件（由 TestCaseListContainer 上报）
  const currentFilters = ref<{ keyword?: string; testType?: string; algorithmType?: string }>({});

  const refreshCurrentView = async () => {
    if (viewMode.value === 'tag') {
      await fetchTagView({
        keyword: currentFilters.value.keyword,
        testType: currentFilters.value.testType,
        algorithmType: currentFilters.value.algorithmType,
      });
    } else {
      await fetchTestCases({
        keyword: currentFilters.value.keyword,
        testType: currentFilters.value.testType,
        algorithmType: currentFilters.value.algorithmType,
      });
    }
  };

  watch(viewMode, async (newMode) => {
    console.log('[TestCaseManager] 视图切换:', newMode);
    await refreshCurrentView();
  });

  // 由 TestCaseListContainer 上报筛选条件变化
  const handleTagFilterChange = (filters: { keyword?: string; testType?: string; algorithmType?: string }) => {
    currentFilters.value = filters;
    if (viewMode.value === 'tag') {
      fetchTagView({
        keyword: filters.keyword,
        testType: filters.testType,
        algorithmType: filters.algorithmType,
      });
    }
  };

  const { confirmDeleteGroup, confirmDeleteTestCase } = useDeleteConfirm();

  const handleDeleteGroup = async (groupName: string) => {
    try {
      const confirmed = await confirmDeleteGroup(groupName);
      if (confirmed) {
        await deleteGroupFromStore(groupName);
      }
    } catch (error) {
      console.error('删除分组失败:', error);
      alert('删除分组失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const handleDeleteTestCase = async (testCase: TestCase) => {
    try {
      console.log('[TestCaseManager] 调用handleDeleteTestCase:', testCase.id, testCase.name);
      const confirmed = await confirmDeleteTestCase(testCase.name);
      if (confirmed) {
        await deleteTestCase(testCase.id);
      }
    } catch (error) {
      console.error('删除测试用例失败:', error);
      alert('删除测试用例失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const handleOpenEditModal = async (testCase: TestCase) => {
    const result = await openEditTestCaseModal(testCase);
    if (result?.needRefresh) {
      await refreshCurrentView();
    }
  };

  const handleOpenAddModal = async (group = '', options?: { algorithmType?: string; testType?: 'api' | 'e2e' }) => {
    const result = await openAddTestCaseModal(group, options);
    if (result?.needRefresh) {
      await refreshCurrentView();
    }
  };

  const handleSaveModal = async (data: ModalSaveData) => {
    const result = await handleModalSave(data);
    if (result?.needRefresh) {
      console.log('刷新测试用例数据...');
      await refreshCurrentView();
    }
  };

  onMounted(async () => {
    console.log('[TestCaseManager] 初始加载测试用例');
    await fetchTestCases();
  });

  return {
    testCaseGroups,
    tagViewData,
    tags,
    paginationInfo,
    tagViewPagination,
    isLoading,
    viewMode,
    handleDeleteGroup,
    handleDeleteTestCase,
    openAddTestCaseModal,
    handleOpenAddModal,
    handleOpenEditModal,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
    handleSaveModal,
    handleTestCaseAction,
    refreshCurrentView,
    handleTagFilterChange
  };
}
