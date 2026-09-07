/**
 * TestCaseListContainer —— 用例选择与批量菜单模块
 *
 * 职责：用例卡片操作项、单选/分组全选/标签全选逻辑、分组删除，以及批量菜单开关状态。
 */
import { ref, computed } from 'vue';
import { useTestCaseStore } from '../../../store/testCaseStore';
import type { ComputedRef, Ref } from 'vue';
import type { TestCase } from '../../../domain';
import type { ContainerState } from './testCaseListContainer.state';

/** 选择模块依赖（来自筛选/视图计算属性模块） */
interface SelectionModuleDeps {
  /** 防抖后的搜索关键词 */
  debouncedSearchQuery: Ref<string>;
  /** 分组全选状态 */
  groupSelectionStates: ComputedRef<Record<string, boolean>>;
  /** 过滤后的标签用例 */
  filteredTagCases: ComputedRef<Record<string, TestCase[]>>;
}

/** 创建用例选择与批量菜单模块 */
export function createSelectionModule(props: any, emit: any, state: ContainerState, deps: SelectionModuleDeps) {
  const {
    algorithmTypeFilter,
    testTypeFilter,
    dimensionFilter,
    selectedCases
  } = state;

  const { debouncedSearchQuery, groupSelectionStates, filteredTagCases } = deps;

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

  // ===== 分组全选/取消全选 =====
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

  // ===== 标签全选状态与切换 =====
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

  return {
    getTestCaseActions,
    toggleTestCaseSelection,
    toggleGroupSelection,
    tagSelectionStates,
    toggleTagSelection,
    handleGroupDelete,
    openBatchMenuGroup,
    toggleBatchMenu,
    closeAllBatchMenus
  };
}

/** 用例选择与批量菜单模块类型（由工厂推断） */
export type SelectionModule = ReturnType<typeof createSelectionModule>;