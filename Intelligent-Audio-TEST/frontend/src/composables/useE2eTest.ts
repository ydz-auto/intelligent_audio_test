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
    paginationInfo,
    tagViewData
  } = storeToRefs(testCaseStore);

  const {
    fetchTestCases,
    fetchTagView,
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
    if (caseItem.deleted) return false;
    // 优先使用 test_type 字段（voice_llm 新架构）；后端列表接口返回的字段名为 type
    const testType = ((caseItem as any).testType || (caseItem as any).test_type || (caseItem as any).type || '').toLowerCase();
    if (testType) return testType === 'e2e' || testType === 'e2e_test';
    // 向后兼容：config 级别检查
    const config = (caseItem.config || {}) as any;
    const configType = (config.type || '').toLowerCase();
    if (configType === 'e2e' || configType === 'e2e_test') return true;
    // 向后兼容：audios 级别检查（支持 rounds 格式）
    const rounds = config.rounds || [];
    if (Array.isArray(rounds) && rounds.length > 0) {
      // rounds 格式：检查是否有任何 round 包含音频
      return rounds.some((r: any) => Array.isArray(r.audios) && r.audios.length > 0);
    }
    // 旧 flat 格式
    const audios = config.audios || [];
    return audios.some((a: any) => (a.testType || a.test_type) === 'e2e');
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
    tagViewData,
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
    handleE2eTestCaseSave,
    fetchTagView
  };
}
