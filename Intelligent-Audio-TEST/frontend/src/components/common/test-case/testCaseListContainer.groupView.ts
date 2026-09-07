/**
 * TestCaseListContainer —— 分组视图计算属性模块
 *
 * 职责：分组视图的可用分组、用例筛选、格式化、全选状态、时长统计、排序与前端分页计算属性。
 */
import { computed } from 'vue';
import { normalizeTestCaseConfig } from '../../../utils/utils';
import type { Ref } from 'vue';
import type { TestCase } from '../../../domain';
import type { ContainerState } from './testCaseListContainer.state';

/** 分组视图依赖（来自分组展开/筛选模块） */
export interface GroupViewDeps {
  debouncedSearchQuery: Ref<string>;
  getGroupTotalCount: (groupName: string) => number;
  currentPage: Ref<number>;
  itemsPerPage: Ref<number>;
}

/** 创建分组视图计算属性模块 */
export function createGroupViewData(props: any, state: ContainerState, deps: GroupViewDeps) {
  const {
    testTypeFilter,
    algorithmTypeFilter,
    groupFilter,
    tagFilter,
    sortBy,
    sortOrder,
    selectedCases,
    hasMoreGroups
  } = state;

  const { debouncedSearchQuery, getGroupTotalCount, currentPage, itemsPerPage } = deps;

  // ===== 计算属性：分组视图 =====
  const availableGroups = computed(() => {
    console.log('[availableGroups] props.testCaseGroups:', props.testCaseGroups);
    console.log('[availableGroups] props.testCaseGroups keys:', Object.keys(props.testCaseGroups || {}));
    return Object.keys(props.testCaseGroups || {});
  });

  const filteredTestCases = computed(() => {
    const result: Record<string, TestCase[]> = {};
    const testCasesData = props.testCaseGroups || {};

    const query = debouncedSearchQuery.value?.toLowerCase() || '';
    const testType = testTypeFilter.value;
    const algorithmType = algorithmTypeFilter.value;
    const selectedGroup = groupFilter.value;
    const selectedTag = tagFilter.value;

    Object.keys(testCasesData).forEach((group: string) => {
      if (selectedGroup !== 'all' && group !== selectedGroup) {
        return;
      }

      const groupCases = testCasesData[group] || [];
      if (groupCases.length === 0) {
        result[group] = [];
        return;
      }

      let filtered = groupCases;

      if (query) {
        filtered = filtered.filter((testCase: TestCase) => {
          if (!testCase) return false;
          const idStr = String(testCase.id || '').toLowerCase();
          const name = (testCase.name || '').toLowerCase();
          const desc = (testCase.description || '').toLowerCase();

          if (idStr.includes(query) || name.includes(query) || desc.includes(query)) {
            return true;
          }

          if (testCase.tags && testCase.tags.length > 0) {
            return testCase.tags.some((tag: any) => {
              const tagName = typeof tag === 'string' ? tag : (tag.name || '');
              return tagName.toLowerCase().includes(query);
            });
          }
          return false;
        });
      }

      if (testType !== 'all') {
        filtered = filtered.filter((testCase: TestCase) => {
          if (!testCase) return false;
          const config = testCase.config || {};
          const types = testCase.type || config.type;

          if (types) {
            const typeArray = Array.isArray(types) ? types : [types];
            const normalizedTypes = typeArray.map(t => String(t).toLowerCase());

            if (testType === 'api') {
              return normalizedTypes.includes('api') || normalizedTypes.includes('apitest');
            } else if (testType === 'e2e') {
              return normalizedTypes.includes('e2e') || normalizedTypes.includes('e2etest');
            }
            return normalizedTypes.includes(testType.toLowerCase());
          }

          const normalizedConfig = normalizeTestCaseConfig(config);
          const rounds = normalizedConfig.rounds || [];
          const hasAudios = rounds.some((r: any) => Array.isArray(r.audios) && r.audios.length > 0);
          // In dual-record architecture, testType is at record level
          const recordTestType = (testCase as any).testType || '';
          if (recordTestType) {
            if (testType === 'api') return recordTestType === 'api';
            if (testType === 'e2e') return recordTestType === 'e2e';
          }
          // Fallback: if has audios, assume matches current filter
          return hasAudios;
        });
      }

      if (algorithmType !== 'all') {
        filtered = filtered.filter((testCase: TestCase) => {
          return testCase && testCase.algorithmType === algorithmType;
        });
      }

      if (selectedTag !== 'all') {
        filtered = filtered.filter((testCase: TestCase) => {
          if (!testCase || !testCase.tags) return false;
          return testCase.tags.some((tag: any) => {
            const tagName = typeof tag === 'string' ? tag : tag.name;
            return tagName === selectedTag;
          });
        });
      }

      result[group] = filtered;
    });

    return result;
  });

  // ===== 格式化：为每个用例补全展示字段 =====
  const formattedTestCases = computed(() => {
    const result: Record<string, (TestCase & { lastEditTime?: string; selected: boolean })[]> = {};
    const filteredValue = filteredTestCases.value;

    Object.keys(filteredValue).forEach((group: string) => {
      result[group] = filteredValue[group]
        .filter((testCase: TestCase) => testCase && testCase.id)
        .map((testCase: TestCase) => ({
          ...testCase,
          lastEditTime: testCase.updatedAt || testCase.createdAt,
          selected: selectedCases.value.includes(testCase.id)
        }));
    });
    return result;
  });

  // ===== 分组全选状态 =====
  const groupSelectionStates = computed(() => {
    const result: Record<string, boolean> = {};
    const filteredValue = filteredTestCases.value;
    const selectedSet = new Set(selectedCases.value.map(id => String(id)));

    Object.keys(filteredValue).forEach((group: string) => {
      const groupCases = filteredValue[group];
      // 用后端总数判断全选状态，而非已加载的用例数
      const totalCount = getGroupTotalCount(group);
      if (totalCount === 0) {
        result[group] = false;
      } else {
        // 统计该分组下已选中的用例数
        const selectedInGroup = groupCases.filter((tc: TestCase) => tc && tc.id && selectedSet.has(String(tc.id))).length;
        // 如果已加载数 < 总数，只能判断部分选中；只有全部加载且全选才算全选
        // 但 toggleGroupSelection 会从后端拉全量ID，所以已加载的用例数可能 < 选中数
        // 此处用 totalCount === selectedInGroup 判断不够准确（selectedInGroup 只数已加载的）
        // 改为：如果 selectedCases 长度 >= totalCount 且已加载的全部选中，则全选
        result[group] = groupCases.length > 0 && groupCases
          .filter((caseItem: TestCase) => caseItem && caseItem.id)
          .every((caseItem: TestCase) => selectedSet.has(String(caseItem.id)))
          && selectedInGroup >= totalCount;
      }
    });

    return result;
  });

  // ===== 时长统计与格式化 =====
  const getGroupDurationStats = (group: string) => {
    const cases = filteredTestCases.value[group] || [];
    let totalDuration = 0;

    cases.forEach((tc: TestCase) => {
      if (tc.totalDuration) totalDuration += tc.totalDuration;
    });

    return { totalDuration };
  };

  const formatGroupDuration = (seconds: number): string => {
    if (!seconds || seconds === 0) return '0s';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    if (minutes < 60) return `${minutes}m${remainingSeconds > 0 ? ` ${remainingSeconds.toFixed(0)}s` : ''}`;
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    return `${hours}h ${remainingMinutes}m`;
  };

  // ===== 分组排序与前端分页 =====
  const sortedGroups = computed(() => {
    const filteredValue = filteredTestCases.value;
    const groups = Object.keys(filteredValue);
    const currentSortBy = sortBy.value;
    const currentSortOrder = sortOrder.value;

    return groups.sort((a, b) => {
      let result = 0;

      switch (currentSortBy) {
        case 'count':
          // 按分组真实用例总数排序（来自后端 test_case_count），而非已加载数量，
          // 否则展开分组触发懒加载后已加载数量从 0 跳变，分组会被降序重排到顶部。
          result = getGroupTotalCount(b) - getGroupTotalCount(a);
          return currentSortOrder === 'asc' ? result * -1 : result;
        case 'name':
          result = a.localeCompare(b, 'zh-CN');
          return currentSortOrder === 'desc' ? result * -1 : result;
        case 'createTime':
          const aCases = filteredValue[a] || [];
          const bCases = filteredValue[b] || [];

          if (aCases.length === 0 && bCases.length === 0) {
            result = a.localeCompare(b, 'zh-CN');
            return currentSortOrder === 'desc' ? result * -1 : result;
          } else if (aCases.length === 0) {
            return currentSortOrder === 'asc' ? 1 : -1;
          } else if (bCases.length === 0) {
            return currentSortOrder === 'asc' ? -1 : 1;
          }

          const aTime = aCases[0]?.createdAt ? new Date(aCases[0].createdAt).getTime() : 0;
          const bTime = bCases[0]?.createdAt ? new Date(bCases[0].createdAt).getTime() : 0;
          result = bTime - aTime;
          return currentSortOrder === 'asc' ? result * -1 : result;
        default:
          result = getGroupTotalCount(b) - getGroupTotalCount(a);
          return currentSortOrder === 'asc' ? result * -1 : result;
      }
    });
  });

  // Paginated groups computed property
  const paginatedGroups = computed(() => {
    const allGroups = sortedGroups.value;
    const endIndex = currentPage.value * itemsPerPage.value;
    return allGroups.slice(0, endIndex);
  });

  // Pagination info computed property
  const paginationInfo = computed(() => {
    const totalItems = sortedGroups.value.length;
    const totalPages = Math.ceil(totalItems / itemsPerPage.value);
    hasMoreGroups.value = paginatedGroups.value.length < totalItems;

    return {
      totalItems,
      totalPages,
      currentPage: currentPage.value,
      itemsPerPage: itemsPerPage.value,
      hasPrev: currentPage.value > 1,
      hasNext: currentPage.value < totalPages
    };
  });

  return {
    availableGroups,
    filteredTestCases,
    formattedTestCases,
    groupSelectionStates,
    getGroupDurationStats,
    formatGroupDuration,
    sortedGroups,
    paginatedGroups,
    paginationInfo
  };
}

/** 分组视图计算属性模块类型（由工厂推断） */
export type GroupViewData = ReturnType<typeof createGroupViewData>;