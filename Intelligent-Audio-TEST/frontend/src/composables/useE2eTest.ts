import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useTestCaseStore } from '../store';
import { useTestCaseCard } from './useTestCaseCard';
import { useModal } from './useModal';
import { testcasesApi  } from '../utils/api';
import { MODAL_TYPES, type TestCase, type TestCaseFormData } from '../shared/types';

export function useE2eTest() {
  const testCaseStore = useTestCaseStore();
  const { 
    testCases, 
    testCaseGroups,
    tags,
    isLoading,
    paginationInfo
  } = storeToRefs(testCaseStore);
  
  const {
    fetchTestCases, 
    addTestCase, 
    updateTestCase, 
    deleteTestCase, 
    copyTestCase,
    deleteGroup
  } = testCaseStore;
  
  const {
    handleTestCaseAction,
    openImportTestCaseModal,
    openExportTestCaseModal,
    openCreateGroupModal,
    openEditGroupModal
  } = useTestCaseCard();

  const modalManager = useModal();

  const isE2eTestCase = (caseItem: TestCase): boolean => {
    // 只过滤已删除的用例，显示所有非删除的用例
    return !caseItem.deleted;
  };

  const e2eTestCases = computed(() => {
    const cases = (testCases.value || []) as TestCase[];
    return cases.filter(isE2eTestCase);
  });

  const e2eTestCaseGroups = computed(() => {
    const groups: Record<string, TestCase[]> = {};
    const currentGroups = (testCaseGroups.value || {}) as Record<string, TestCase[]>;
    
    Object.entries(currentGroups).forEach(([groupName, cases]) => {
      const e2eCases = (cases || []).filter(isE2eTestCase);
      // 移除过滤条件，确保所有分组都能显示，包括用例数量为0的分组
      groups[groupName] = e2eCases;
    });
    return groups;
  });

  const addE2eTestCase = (newTestCase: Partial<TestCase>) => {
    const e2eTestCase = { ...newTestCase, type: 'e2e', config: {
        ...(newTestCase.config || {}),
        type: 'e2e'
      }
    };
    return addTestCase(e2eTestCase as any);
  };

  const updateE2eTestCase = (updatedTestCase: TestCase) => {
    if (!updatedTestCase?.id) {
      throw new Error('Update requires a valid test case ID');
    }
    const e2eTestCase = { ...updatedTestCase, type: 'e2e', config: {
        ...(updatedTestCase.config || {}),
        type: 'e2e'
      }
    };
    return updateTestCase(e2eTestCase.id, e2eTestCase as any);
  };

  const deleteE2eTestCase = (caseId: string | number) => {
    return deleteTestCase(caseId);
  };

  const copyE2eTestCase = (originalCase: TestCase) => {
    return copyTestCase(originalCase.id);
  };

  const openAddE2eTestCaseModal = (group = '默认分组') => {
    handleTestCaseAction({
      action: { id: 'add' },
      testCase: { group: group, config: { type: 'e2e_test' } } as unknown as TestCase
    });
  };

  const runE2eTest = async (testCase: TestCase) => {
    console.log('运行E2E测试:', testCase.id);
    try {
      if (typeof (testcasesApi as any).preview === 'function') {
        return await testcasesApi.preview(testCase.id);
      } else {
        console.warn('后端暂不支持单条E2E用例预览，请通过任务流运行');
      }
    } catch (error) {
      console.error('运行E2E测试失败:', error);
      throw error;
    }
  };

  const openImportE2eTestCaseModal = () => {
    openImportTestCaseModal();
  };

  const openExportE2eTestCaseModal = (ids?: (string | number)[]) => {
    openExportTestCaseModal();
  };

  const openAddGroupModal = () => {
    openCreateGroupModal();
  };

  const openEditE2eGroupModal = (groupName: string) => {
    openEditGroupModal(groupName);
  };

  const initializeE2eTests = async (algorithmType?: string) => {
    await fetchTestCases({ algorithmType });
  };

  const handleE2eTestCaseSave = async (data: TestCaseFormData & { id?: string }) => {
    try {
      data.type = 'e2e_test';
      if (!data.config) data.config = {};
      data.config.type = 'e2e_test';

      if (data.id) {
        return await updateE2eTestCase(data as unknown as TestCase);
      } else {
        return await addE2eTestCase(data as unknown as TestCase);
      }
    } catch (error) {
      console.error('保存E2E测试用例失败:', error);
      throw error;
    }
  };

  return {
    isLoading,
    testCases,
    testCaseGroups,
    e2eTestCases,
    e2eTestCaseGroups,
    tags,
    paginationInfo,
    initializeE2eTests,
    openAddE2eTestCaseModal,
    handleTestCaseAction,
    runE2eTest,
    openImportE2eTestCaseModal,
    openExportE2eTestCaseModal,
    openAddGroupModal,
    openEditE2eGroupModal,
    addE2eTestCase,
    updateE2eTestCase,
    deleteE2eTestCase,
    copyE2eTestCase,
    deleteGroup,
    handleE2eTestCaseSave
  };
}
