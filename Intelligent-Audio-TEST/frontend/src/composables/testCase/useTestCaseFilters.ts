import { ref, watch, type Ref } from 'vue';

/**
 * useDebounce: 为给定的响应式值生成防抖副本。
 *
 * 从原 TestCaseListContainer.vue 内联实现抽取，保持行为一致。
 */
export function useDebounce<T>(value: Ref<T>, delay: number = 300): Ref<T> {
  const debouncedValue = ref(value.value) as Ref<T>;
  let timeout: ReturnType<typeof setTimeout> | null = null;

  watch(value, (newValue) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => {
      debouncedValue.value = newValue;
    }, delay);
  });

  return debouncedValue;
}

/**
 * 测试用例列表筛选/搜索 composable。
 *
 * 职责：
 * - 管理搜索框、测试类型 / 算法类型 / 分组 / 标签 / 排序等筛选状态
 * - 提供防抖后的搜索查询
 * - 重置所有筛选条件
 * - 筛选条件变化时重置分页（与外部 currentPage 联动）
 * - 标签视图模式下，筛选条件变化时通知父组件重新请求后端
 *
 * 注意：筛选状态 ref 由调用方在组件级声明并传入，便于其它 composable
 * （如 useTestCaseGroupExpand 的 toggleCategory 需要 algorithmTypeFilter）
 * 共享同一份响应式状态，避免初始化顺序导致的循环依赖。
 */
export function useTestCaseFilters(
  props: {
    algorithmTypeFilter?: string;
    testTypeFilter?: string;
  },
  refs: {
    searchQuery: Ref<string>;
    testTypeFilter: Ref<string>;
    algorithmTypeFilter: Ref<string>;
    groupFilter: Ref<string>;
    tagFilter: Ref<string>;
    sortBy: Ref<string>;
    sortOrder: Ref<string>;
    dimensionFilter: Ref<number | 'all'>;
  },
  options: {
    currentPage: Ref<number>;
    innerViewMode: Ref<'group' | 'tag'>;
    emitTagFilterChange: (filters: { keyword?: string; testType?: string; algorithmType?: string; dimensionId?: number }) => void;
    emitGroupFilterChange: (filters: { keyword?: string; testType?: string; algorithmType?: string; dimensionId?: number }) => void;
  }
) {
  const {
    searchQuery,
    testTypeFilter,
    algorithmTypeFilter,
    groupFilter,
    tagFilter,
    sortBy,
    sortOrder,
    dimensionFilter
  } = refs;

  const debouncedSearchQuery = useDebounce(searchQuery, 300);

  // 同步外部 props -> 本地筛选状态
  watch(() => props.algorithmTypeFilter, (newValue) => {
    if (newValue !== undefined) {
      algorithmTypeFilter.value = newValue;
    }
  }, { immediate: true });

  watch(() => props.testTypeFilter, (newValue) => {
    if (newValue !== undefined) {
      testTypeFilter.value = newValue;
    }
  }, { immediate: true });

  // 任意筛选条件变化时重置到第一页
  watch([searchQuery, testTypeFilter, algorithmTypeFilter, groupFilter, tagFilter, sortBy, sortOrder], () => {
    options.currentPage.value = 1;
  });

  // 筛选条件变化时通知父组件重新请求后端:
  // - 标签视图:刷新标签聚合数据
  // - 分组视图:刷新分组列表(test_case_count 按筛选统计),否则徽标计数不随筛选更新
  // 使用 suppressFilterEmit 标志抑制 resetFilters 后防抖 watch 的重复触发
  let suppressFilterEmit = false;
  watch([debouncedSearchQuery, testTypeFilter, algorithmTypeFilter, dimensionFilter, options.innerViewMode], () => {
    if (suppressFilterEmit) return;
    const filters = {
      keyword: debouncedSearchQuery.value || undefined,
      testType: testTypeFilter.value !== 'all' ? testTypeFilter.value : undefined,
      algorithmType: algorithmTypeFilter.value !== 'all' ? algorithmTypeFilter.value : undefined,
      dimensionId: dimensionFilter.value !== 'all' ? dimensionFilter.value : undefined,
    };
    if (options.innerViewMode.value === 'tag') {
      options.emitTagFilterChange(filters);
    } else {
      options.emitGroupFilterChange(filters);
    }
  });

  const resetFilters = () => {
    // 抑制防抖 watch 的重复触发（searchQuery 清空后 300ms 防抖会再次触发）
    suppressFilterEmit = true;
    searchQuery.value = '';
    // testTypeFilter 和 algorithmTypeFilter 由 props 控制（E2E/APITest 固定 e2e/api），
    // resetFilters 不重置它们，避免被 props watch 立即覆盖导致抖动。
    groupFilter.value = 'all';
    tagFilter.value = 'all';
    dimensionFilter.value = 'all';
    sortBy.value = 'count';
    sortOrder.value = 'desc';
    options.currentPage.value = 1;

    // 立即触发后端刷新（不等防抖），用当前实际有效的筛选条件
    const filters = {
      keyword: undefined,
      testType: testTypeFilter.value !== 'all' ? testTypeFilter.value : undefined,
      algorithmType: algorithmTypeFilter.value !== 'all' ? algorithmTypeFilter.value : undefined,
      dimensionId: undefined,
    };
    if (options.innerViewMode.value === 'tag') {
      options.emitTagFilterChange(filters);
    } else {
      options.emitGroupFilterChange(filters);
    }

    // 防抖延迟过后恢复 watch 响应
    setTimeout(() => { suppressFilterEmit = false; }, 350);
  };

  return {
    searchQuery,
    debouncedSearchQuery,
    testTypeFilter,
    algorithmTypeFilter,
    groupFilter,
    tagFilter,
    sortBy,
    sortOrder,
    dimensionFilter,
    resetFilters
  };
}
