/**
 * TestCaseListContainer —— 标签视图计算属性模块
 *
 * 职责：标签视图的可用标签、用例过滤、格式化、时长统计、排序，以及后端分页"加载更多"标志。
 */
import { computed } from 'vue';
import type { TestCase } from '../../../domain';
import type { ContainerState } from './testCaseListContainer.state';

/** 创建标签视图计算属性模块 */
export function createTagViewData(props: any, state: ContainerState) {
  const {
    tagFilter,
    sortBy,
    sortOrder,
    selectedCases
  } = state;

  // ===== 计算属性：标签视图 =====
  const availableTags = computed(() => {
    return Object.keys(props.tagViewData || {});
  });

  const filteredTagCases = computed(() => {
    const result: Record<string, TestCase[]> = {};
    const tagData = props.tagViewData || {};

    const selectedTag = tagFilter.value;

    // 后端已对 keyword/testType/algorithmType 做筛选，前端只做标签选择器过滤
    Object.keys(tagData).forEach((tagName: string) => {
      if (selectedTag !== 'all' && tagName !== selectedTag) {
        return;
      }
      result[tagName] = tagData[tagName] || [];
    });

    return result;
  });

  const formattedTagCases = computed(() => {
    const result: Record<string, (TestCase & { lastEditTime?: string; selected: boolean })[]> = {};
    const filteredValue = filteredTagCases.value;

    Object.keys(filteredValue).forEach((tagName: string) => {
      result[tagName] = filteredValue[tagName]
        .filter((testCase: TestCase) => testCase && testCase.id)
        .map((testCase: TestCase) => ({
          ...testCase,
          lastEditTime: testCase.updatedAt || testCase.createdAt,
          selected: selectedCases.value.includes(testCase.id)
        }));
    });
    return result;
  });

  const sortedTags = computed(() => {
    const filteredValue = filteredTagCases.value;
    const tagsList = Object.keys(filteredValue);
    const currentSortBy = sortBy.value;
    const currentSortOrder = sortOrder.value;

    return tagsList.sort((a, b) => {
      let result = 0;
      switch (currentSortBy) {
        case 'count':
          result = (filteredValue[b]?.length || 0) - (filteredValue[a]?.length || 0);
          return currentSortOrder === 'asc' ? result * -1 : result;
        case 'name':
          result = a.localeCompare(b, 'zh-CN');
          return currentSortOrder === 'desc' ? result * -1 : result;
        case 'createTime':
          const aCases = filteredValue[a] || [];
          const bCases = filteredValue[b] || [];
          const aTime = aCases[0]?.createdAt ? new Date(aCases[0].createdAt).getTime() : 0;
          const bTime = bCases[0]?.createdAt ? new Date(bCases[0].createdAt).getTime() : 0;
          result = bTime - aTime;
          return currentSortOrder === 'asc' ? result * -1 : result;
        default:
          result = (filteredValue[b]?.length || 0) - (filteredValue[a]?.length || 0);
          return currentSortOrder === 'asc' ? result * -1 : result;
      }
    });
  });

  // 标签视图是否还有更多未从后端加载的标签（基于后端分页信息）
  const hasMoreTagsFromBackend = computed(() => {
    const pagination = props.tagViewPagination;
    if (!pagination) return false;
    return pagination.page < pagination.pages;
  });

  // 兼容旧引用：标签视图的前端分页标志，后端分页模式下始终为 false（由 hasMoreTagsFromBackend 接管）
  const hasMoreTags = computed(() => false);

  // ===== 时长统计 =====
  const getTagDurationStats = (tagName: string) => {
    const cases = filteredTagCases.value[tagName] || [];
    let totalDuration = 0;
    cases.forEach((tc: TestCase) => {
      if (tc.totalDuration) totalDuration += tc.totalDuration;
    });
    return { totalDuration };
  };

  return {
    availableTags,
    filteredTagCases,
    formattedTagCases,
    sortedTags,
    hasMoreTagsFromBackend,
    hasMoreTags,
    getTagDurationStats
  };
}

/** 标签视图计算属性模块类型（由工厂推断） */
export type TagViewData = ReturnType<typeof createTagViewData>;