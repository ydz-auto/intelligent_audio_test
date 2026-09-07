/**
 * apiTest —— 测试用例管理（cases）
 *
 * 负责用例选择、删除/编辑弹窗编排（含保存后刷新）、用例详情查看与占位操作。
 */
import { MODAL_TYPES } from '../../composables/modal/useModal'
import { useNotification } from '../../composables/modal/useNotification'
import { TestType } from '@/domain/enums'
import type { Ref } from 'vue'
import type { useModalControl } from '../../composables/modal/useModal'
import type { useTestCaseCard } from '../../composables/testCase/useTestCaseCard'
import type { useDeleteConfirm } from '../../composables/modal/useDeleteConfirm'
import type { useTestCaseStore } from '../../store/testCaseStore'
import type { TestCase } from '../../domain'
import type { ModalSaveData } from '../../composables/modal/types'

/** 测试用例管理模块依赖 */
export interface ApiTestCasesDeps {
  selectedTestCaseIds: Ref<(string | number)[]>;
  currentTaskId: Ref<string | number | null>;
  modalManager: ReturnType<typeof useModalControl>;
  testCaseCard: ReturnType<typeof useTestCaseCard>;
  deleteConfirm: ReturnType<typeof useDeleteConfirm>;
  testCaseStore: ReturnType<typeof useTestCaseStore>;
  selectedAlgorithmType: Ref<string | null>;
}

/** 创建测试用例管理模块 */
export function createApiTestCasesModule(deps: ApiTestCasesDeps) {
  const notification = useNotification()
  const { selectedTestCaseIds, currentTaskId, modalManager, testCaseCard, deleteConfirm, testCaseStore, selectedAlgorithmType } = deps
  const { openAddTestCaseModal, openEditTestCaseModal, handleModalSave } = testCaseCard
  const { confirmDeleteGroup, confirmDeleteTestCase } = deleteConfirm
  const { deleteGroup, deleteTestCase, fetchTestCases } = testCaseStore

  const updateSelectedCases = (caseIds: (string | number)[]) => {
    selectedTestCaseIds.value = caseIds
    console.log('useAPITest: 更新选中的测试用例:', selectedTestCaseIds.value)
  }

  const handleDeleteGroup = async (groupName: string) => {
    try {
      const confirmed = await confirmDeleteGroup(groupName);
      if (confirmed) {
        deleteGroup(groupName);
        await fetchTestCases({ algorithmType: selectedAlgorithmType.value || undefined });
      }
    } catch (error) {
      console.error('删除分组失败:', error);
      notification.error('删除分组失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const handleDeleteTestCase = async (testCase: TestCase) => {
    try {
      const confirmed = await confirmDeleteTestCase(testCase.name);
      if (confirmed) {
        deleteTestCase(testCase.id);
        await fetchTestCases({ algorithmType: selectedAlgorithmType.value || undefined });
      }
    } catch (error) {
      console.error('删除测试用例失败:', error);
      notification.error('删除测试用例失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  const handleOpenEditModal = (testCase: TestCase) => {
    openEditTestCaseModal(testCase);
  };

  const handleSaveModal = async (data: ModalSaveData) => {
    const result = await handleModalSave(data);
    if (result?.needRefresh) {
      await fetchTestCases({ algorithmType: selectedAlgorithmType.value || undefined });
    }
  };

  const showTestCaseDetails = (testCaseId: string | number) => {
    if (currentTaskId.value) {
      modalManager.open(MODAL_TYPES.TEST_CASE_DETAIL, {
        taskId: currentTaskId.value,
        caseId: testCaseId,
        options: { width: '1200px' }
      });
    }
  }

  const skipTestCase = (testCaseId: string | number) => {
    console.log(`Skipping test case ${testCaseId}...`)
  }

  const showAddTestCaseModalHandler = () => {
    openAddTestCaseModal('默认分组', { testType: TestType.API })
  }

  const removeTestCase = (testCaseId: string | number) => {
    console.log(`Removing test case ${testCaseId}...`)
  }

  return {
    updateSelectedCases,
    handleDeleteGroup,
    handleDeleteTestCase,
    handleOpenEditModal,
    handleSaveModal,
    showTestCaseDetails,
    skipTestCase,
    showAddTestCaseModalHandler,
    removeTestCase
  }
}