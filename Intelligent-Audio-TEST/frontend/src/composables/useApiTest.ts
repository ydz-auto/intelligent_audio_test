import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useTestCaseStore } from '../store';
import { useTestCaseCard } from './useTestCaseCard';
import { useModal } from './useModal';
import { testcasesApi } from '../utils/api';
import { MODAL_TYPES, type TestCase, type TestCaseFormData } from '../shared/types';

export function useApiTest() {
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
    handleTestCaseAction
  } = useTestCaseCard();

  const modalManager = useModal();

  const isApiTestCase = (caseItem: TestCase): boolean => {
    if (caseItem.deleted) return false;
    
    // 优先检查记录级 testType 字段
    const recordType = (caseItem.testType || caseItem.test_type || caseItem.type || '').toLowerCase();
    if (recordType === 'api' || recordType === 'api_test') return true;
    
    // 回退：检查 config 中是否有音频（支持 rounds 格式）
    const config: any = caseItem.config || {};
    const rounds = config.rounds || [];
    if (Array.isArray(rounds) && rounds.length > 0) {
      // rounds 格式：检查是否有任何 round 包含音频
      return rounds.some((r: any) => Array.isArray(r.audios) && r.audios.length > 0);
    }
    // 旧 flat 格式
    const audios = config.audios || [];
    return audios.some((a: any) => (a.testType || a.test_type) === 'api');
  };

  const apiTestCases = computed(() => {
    const cases = (testCases.value || []) as TestCase[];
    return cases.filter(isApiTestCase);
  });

  const apiTestCaseGroups = computed(() => {
    const groups: Record<string, TestCase[]> = {};
    const currentGroups = (testCaseGroups.value || {}) as Record<string, TestCase[]>;

    Object.entries(currentGroups).forEach(([groupName, cases]) => {
      const filteredCases = (cases || []).filter(isApiTestCase);
      if (filteredCases.length > 0) {
        groups[groupName] = filteredCases;
      }
    });
    return groups;
  });

  const initializeApiTests = async () => {
    await fetchTestCases();
  };

  const runApiTest = async (testCase: TestCase) => {
    console.log('运行API测试:', testCase.id);
    try {
      await testcasesApi.preview(testCase.id);
      return true;
    } catch (error: any) {
      console.error('运行预览失败:', error);
      // 向用户显示错误提示
      alert(`运行API测试失败: ${error.message || '未知错误'}`);
      throw error;
    }
  };

  const stopApiTest = async (testCase: TestCase) => {
    try {
      await testcasesApi.stopPreview(testCase.id);
      return true;
    } catch (error: any) {
      console.error('停止预览失败:', error);
      // 向用户显示错误提示
      alert(`停止API测试失败: ${error.message || '未知错误'}`);
      throw error;
    }
  };

  const addApiTestCase = (testCaseData: Partial<TestCase>) => {
    const apiTestCase = { ...testCaseData, type: 'api', config: {
        ...(testCaseData.config || {}),
        type: 'api'
      }
    };
    return addTestCase(apiTestCase as any);
  };

  const updateApiTestCase = (updatedTestCase: TestCase) => {
    if (!updatedTestCase?.id) {
      throw new Error('Update requires a valid test case ID');
    }
    const apiTestCase = { ...updatedTestCase, type: 'api', config: {
        ...(updatedTestCase.config || {}),
        type: 'api'
      }
    };
    return updateTestCase(apiTestCase.id, apiTestCase as any);
  };

  const deleteApiTestCase = (caseId: string | number) => {
    return deleteTestCase(caseId);
  };

  const copyApiTestCase = (testCase: TestCase) => {
    return copyTestCase(testCase.id);
  };

  const openAddApiTestCaseModal = (group = '默认分组') => {
    modalManager.open(MODAL_TYPES.ADD_TEST_CASE, {
      group: group,
      config: { type: 'api' },
      mode: 'add'
    });
  };

  const handleApiTestCaseSave = async (data: TestCaseFormData & { id?: string }) => {
    try {
      data.type = 'api';
      if (!data.config) data.config = {};
      data.config.type = 'api';

      if (data.id) {
        return await updateApiTestCase(data as unknown as TestCase);
      } else {
        return await addApiTestCase(data as unknown as TestCase);
      }
    } catch (error: any) {
      console.error('保存API测试用例失败:', error);
      // 向用户显示错误提示
      alert(`保存API测试用例失败: ${error.message || '未知错误'}`);
      throw error;
    }
  };

  return {
    isLoading,
    apiTestCases,
    apiTestCaseGroups,
    tags,
    paginationInfo,
    initializeApiTests,
    runApiTest,
    stopApiTest,
    addApiTestCase,
    updateApiTestCase,
    deleteApiTestCase,
    copyApiTestCase,
    deleteGroup,
    openAddApiTestCaseModal,
    handleApiTestCaseSave,
    handleTestCaseAction
  };
}
