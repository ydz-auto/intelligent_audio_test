import { onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import { useTestCaseCard } from '../../composables/useTestCaseCard';
import { useTestCaseStore } from '../../store/testCaseStore';
import { useDeleteConfirm } from '../../composables/useDeleteConfirm';
import type { TestCase, ModalSaveData } from '../../shared/types';

export function useTestCaseManager() {
  const {
    showTestCaseModal,
    showGroupModal,
    showImportModal,
    showExportModal,
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
    handleModalClose,
    handleModalSave,
    handleTestCaseAction
  } = useTestCaseCard();

  const store = useTestCaseStore();
  const { testCaseGroups, tags, paginationInfo, isLoading } = storeToRefs(store);
  const { fetchTestCases, deleteGroup: deleteGroupFromStore, deleteTestCase } = store;

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

  const handleOpenEditModal = (testCase: TestCase) => {
    openEditTestCaseModal(testCase);
  };

  const handleSaveModal = async (data: ModalSaveData) => {
    const result = await handleModalSave(data);
    if (result?.needRefresh) {
      console.log('刷新测试用例数据...');
      await fetchTestCases();
    }
  };

  onMounted(async () => {
    console.log('[TestCaseManager] 初始加载测试用例');
    await fetchTestCases();
  });

  return {
    testCaseGroups,
    tags,
    paginationInfo,
    showTestCaseModal,
    showGroupModal,
    showImportModal,
    showExportModal,
    formData,
    groupFormData,
    editingTestCase,
    editingGroup,
    isLoading,
    handleDeleteGroup,
    handleDeleteTestCase,
    openAddTestCaseModal,
    handleOpenEditModal,
    openCreateGroupModal,
    openEditGroupModal,
    openImportTestCaseModal,
    openExportTestCaseModal,
    handleModalClose,
    handleSaveModal,
    handleTestCaseAction
  };
}
