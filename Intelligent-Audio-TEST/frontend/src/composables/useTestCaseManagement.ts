import { ref, computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useTestCaseStore } from '../store';
import { useTestCaseCard } from './useTestCaseCard';

// 页面重置composable
export function usePageReset() {
  const resetPage = () => {
    // 重置页面相关状态
    console.log('重置页面状态');
  };

  return {
    resetPage
  };
}

export function useTestCaseManagement() {
  const testCaseStore = useTestCaseStore();
  const { 
    testCases, 
    testCaseGroups, 
    tags, 
    isLoading, 
    allGroups, 
    paginationInfo 
  } = storeToRefs(testCaseStore);

  const {
    fetchTestCases, 
    addTestCase, 
    updateTestCase, 
    deleteTestCase, 
    copyTestCase, 
    addGroup, 
    deleteGroup 
  } = testCaseStore;

  const { 
    editingTestCase, 
    editingGroup, 
    formData, 
    groupFormData, 
    openAddTestCaseModal, 
    openEditTestCaseModal, 
    openEditGroupModal, 
    openCreateGroupModal,
    deleteTestCase: cardDeleteTestCase
  } = useTestCaseCard();

  // 搜索和筛选状态
  const searchQuery = ref('');
  const testTypeFilter = ref('all');
  const tagFilter = ref('all');
  const expandedCategories = ref<Record<string, boolean>>({});
  const selectedCases = ref<(string | number)[]>([]);
  const groupSelectionStates = ref<Record<string, boolean>>({});

  // 初始化
  const initialize = async () => {
    await fetchTestCases();
    // 默认展开所有分组
    const currentGroups = (testCaseGroups.value || {}) as Record<string, any[]>;
    Object.keys(currentGroups).forEach(group => {
      expandedCategories.value[group] = true;
    });
  };

  // 过滤后的测试用例
  const filteredTestCases = computed(() => {
    const result: Record<string, any[]> = {};
    const currentGroups = (testCaseGroups.value || {}) as Record<string, any[]>;
    
    // 遍历所有分组
    Object.keys(currentGroups).forEach(group => {
      // 确保groupCases总是数组
      const groupCases = Array.isArray(currentGroups[group]) ? currentGroups[group] : [];
      
      // 应用搜索过滤
      let filtered = [...groupCases];
      if (searchQuery.value) {
        const query = searchQuery.value.toLowerCase();
        filtered = filtered.filter(testCase => {
          return (testCase.name || '').toLowerCase().includes(query) ||
                 (testCase.description || '').toLowerCase().includes(query) ||
                 (testCase.tags && testCase.tags.some((tag: string) => tag.toLowerCase().includes(query)));
        });
      }
      
      // 应用类型过滤
      if (testTypeFilter.value !== 'all') {
        filtered = filtered.filter(testCase => {
          const type = testCase.type || testCase.config?.type;
          if (type === testTypeFilter.value) return true;
          
          // 兼容短名称
          if (testTypeFilter.value === 'e2e' && type === 'e2e_test') return true;
          if (testTypeFilter.value === 'api' && type === 'api_test') return true;
          
          if (testCase.config?.dryAudios && testTypeFilter.value === 'e2e') return true;
          if (testCase.config?.apiAudio && testTypeFilter.value === 'api') return true;
          return false;
        });
      }
      
      // 应用标签过滤
      if (tagFilter.value !== 'all') {
        filtered = filtered.filter(testCase => {
          return testCase.tags && testCase.tags.includes(tagFilter.value);
        });
      }
      
      if (filtered.length > 0) {
        result[group] = filtered;
      }
    });
    
    return result;
  });

  // 格式化后的测试用例
  const formattedTestCases = computed(() => {
    const result: Record<string, any[]> = {};
    Object.keys(filteredTestCases.value).forEach(group => {
      // 确保groupCases总是数组
      const groupCases = Array.isArray(filteredTestCases.value[group]) ? filteredTestCases.value[group] : [];
      result[group] = groupCases.map(testCase => ({
        ...testCase,
        lastEditTime: testCase.updatedAt || testCase.createdAt,
        selected: selectedCases.value.includes(testCase.id)
      }));
    });
    return result;
  });

  // 更新分组选择状态
  const updateGroupSelectionStates = () => {
    const states: Record<string, boolean> = {};
    
    // 获取所有分组
    const groups = Object.keys(filteredTestCases.value);
    
    // 遍历每个分组
    groups.forEach(group => {
      // 获取当前分组的所有测试用例，确保是数组
      const groupCases = Array.isArray(filteredTestCases.value[group]) ? filteredTestCases.value[group] : [];
      
      // 如果分组为空，直接设为未选中
      if (groupCases.length === 0) {
        states[group] = false;
      } else {
        // 检查分组内所有测试用例是否都被选中
        const allSelected = groupCases.every(caseItem => {
          // 直接检查selectedCases数组是否包含当前用例ID
          return selectedCases.value.includes(caseItem.id);
        });
        
        states[group] = allSelected;
      }
    });
    
    groupSelectionStates.value = states;
  };

  // 切换分组展开状态
  const toggleCategory = (group: string) => {
    expandedCategories.value[group] = !expandedCategories.value[group];
  };

  // 切换测试用例选中状态
  const toggleTestCaseSelection = (caseId: string | number) => {
    const index = selectedCases.value.indexOf(caseId);
    if (index > -1) {
      selectedCases.value.splice(index, 1);
    } else {
      selectedCases.value.push(caseId);
    }
    updateGroupSelectionStates();
  };

  // 切换分组全选状态
  const toggleGroupSelection = (group: string) => {
    // 确保groupCases总是数组
    const groupCases = Array.isArray(filteredTestCases.value[group]) ? filteredTestCases.value[group] : [];
    const allSelected = groupSelectionStates.value[group];
    
    groupCases.forEach(testCase => {
      const index = selectedCases.value.indexOf(testCase.id);
      if (allSelected) {
        // 如果全选，移除所有选中状态
        if (index > -1) {
          selectedCases.value.splice(index, 1);
        }
      } else {
        // 如果未全选，添加所有选中状态
        if (index === -1) {
          selectedCases.value.push(testCase.id);
        }
      }
    });
    updateGroupSelectionStates();
  };

  // 重置筛选条件
  const resetFilters = () => {
    searchQuery.value = '';
    testTypeFilter.value = 'all';
    tagFilter.value = 'all';
  };

  return {
    testCases,
    testCaseGroups,
    tags,
    isLoading,
    allGroups,
    paginationInfo,
    fetchTestCases,
    addTestCase,
    updateTestCase,
    deleteTestCase,
    copyTestCase,
    addGroup,
    deleteGroup,
    editingTestCase,
    editingGroup,
    formData,
    groupFormData,
    openAddTestCaseModal,
    openEditTestCaseModal,
    openEditGroupModal,
    openCreateGroupModal,
    searchQuery,
    testTypeFilter,
    tagFilter,
    expandedCategories,
    selectedCases,
    groupSelectionStates,
    filteredTestCases,
    formattedTestCases,
    initialize,
    toggleCategory,
    toggleTestCaseSelection,
    toggleGroupSelection,
    resetFilters
  };
}
