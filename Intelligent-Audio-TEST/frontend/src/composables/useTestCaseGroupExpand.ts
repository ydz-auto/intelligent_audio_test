import { ref, computed, watch, nextTick, type Ref } from 'vue';
import { useTestCaseStore } from '../store/testCaseStore';
import type { TestCase } from '../shared/types';

/**
 * 测试用例分组展开/折叠/加载 composable。
 *
 * 职责：
 * - 分组展开/折叠状态管理（toggleCategory）
 * - 分组内用例懒加载（首次展开时拉取）
 * - 分组内"加载更多"判断与触发
 * - 分组/标签分组的分页加载（loadMoreGroups / IntersectionObserver）
 * - 滚动加载兜底
 *
 * 依赖：
 * - algorithmTypeFilter: 拉取分组用例时透传算法过滤值
 * - innerViewMode: 当前视图模式，决定 hasMore 取分组还是标签
 * - paginatedGroups / paginatedTags: 用于哨兵重新观察
 * - hasMoreGroups / hasMoreTags: 决定是否还有更多可加载
 */
export function useTestCaseGroupExpand(
  algorithmTypeFilter: Ref<string>,
  innerViewMode: Ref<'group' | 'tag'>,
  paginatedGroups: Ref<string[]>,
  paginatedTags: Ref<string[]>,
  hasMoreGroups: Ref<boolean>,
  hasMoreTags: Ref<boolean>
) {
  const expandedCategories = ref<Record<string, boolean>>({});
  const expandedTagCategories = ref<Record<string, boolean>>({});
  const currentPage = ref(1);
  const itemsPerPage = ref(5);
  const isLoadingMore = ref(false);
  const listContainerRef = ref<HTMLElement | null>(null);
  const loadMoreTriggerRef = ref<HTMLElement | null>(null);

  // IntersectionObserver 实例（模块作用域内复用）
  let loadMoreObserver: IntersectionObserver | null = null;

  const hasMore = computed(() =>
    innerViewMode.value === 'tag' ? hasMoreTags.value : hasMoreGroups.value
  );

  const toggleCategory = async (group: string) => {
    const wasExpanded = expandedCategories.value[group];
    expandedCategories.value[group] = !wasExpanded;

    if (!wasExpanded) {
      const store = useTestCaseStore();
      const groupInfo = store.groupsList.find(g => g.name === group);
      if (groupInfo && (!store.loadedGroupCases[groupInfo.id] || store.loadedGroupCases[groupInfo.id].length === 0)) {
        // 传当前算法过滤值,使拉取的用例与徽标计数(按算法统计)及 filteredTestCases 过滤一致,
        // 否则拉取的是分组下所有算法用例,经算法过滤后可能为空(显示"已加载 0/N 条")。
        const algorithmType = algorithmTypeFilter.value === 'all' ? undefined : algorithmTypeFilter.value;
        await store.fetchCasesByGroup(groupInfo.id, { algorithmType });
      }
    }
  };

  const toggleTagCategory = (tagName: string) => {
    expandedTagCategories.value = {
      ...expandedTagCategories.value,
      [tagName]: !expandedTagCategories.value[tagName]
    };
  };

  const isGroupLoading = (groupName: string) => {
    const store = useTestCaseStore();
    const groupInfo = store.groupsList.find(g => g.name === groupName);
    if (!groupInfo) return false;
    return store.isGroupLoading(groupInfo.id);
  };

  const hasMoreGroupCases = (groupName: string) => {
    const store = useTestCaseStore();
    const groupInfo = store.groupsList.find(g => g.name === groupName);
    if (!groupInfo) return false;
    return store.hasMoreGroupCases(groupInfo.id);
  };

  const getGroupTotalCount = (groupName: string) => {
    const store = useTestCaseStore();
    const groupInfo = store.groupsList.find(g => g.name === groupName);
    return groupInfo?.testCaseCount || 0;
  };

  const loadMoreCases = async (groupName: string) => {
    const store = useTestCaseStore();
    const groupInfo = store.groupsList.find(g => g.name === groupName);
    if (groupInfo) {
      await store.loadMoreGroupCases(groupInfo.id);
    }
  };

  const loadMoreGroups = () => {
    if (isLoadingMore.value || !hasMore.value) return;
    isLoadingMore.value = true;
    setTimeout(() => {
      currentPage.value++;
      isLoadingMore.value = false;
    }, 300);
  };

  const handleScroll = (event: Event) => {
    const target = event.target as HTMLElement;
    const scrollBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
    if (scrollBottom < 100 && hasMore.value && !isLoadingMore.value) {
      loadMoreGroups();
    }
  };

  // 滚动加载兜底：页面真正滚动的是外层 MAIN.main-content（overflow:auto），
  // 既不是 window 也不是 .single-column-layout，所以 @scroll 和 window 监听都捕获不到。
  // 用 IntersectionObserver 监听"加载更多"哨兵，进入视口即自动加载，不受滚动容器归属影响。
  const setupLoadMoreObserver = () => {
    if (typeof IntersectionObserver === 'undefined') return;
    if (loadMoreObserver) loadMoreObserver.disconnect();
    loadMoreObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting && hasMore.value && !isLoadingMore.value) {
          loadMoreGroups();
        }
      });
    }, { rootMargin: '100px' });
    if (loadMoreTriggerRef.value) {
      loadMoreObserver.observe(loadMoreTriggerRef.value);
    }
  };

  // 哨兵是 v-if 元素，每次加载后会重新挂载，需重新观察；
  // 分组/标签视图切换时哨兵也会换元素，需一并重新观察。
  watch([hasMore, isLoadingMore, () => paginatedGroups.value.length, () => paginatedTags.value.length, innerViewMode], () => {
    nextTick(setupLoadMoreObserver);
  });

  // 清理 IntersectionObserver
  const cleanupObserver = () => {
    if (loadMoreObserver) {
      loadMoreObserver.disconnect();
      loadMoreObserver = null;
    }
  };

  return {
    expandedCategories,
    expandedTagCategories,
    currentPage,
    itemsPerPage,
    isLoadingMore,
    listContainerRef,
    loadMoreTriggerRef,
    hasMore,
    toggleCategory,
    toggleTagCategory,
    isGroupLoading,
    hasMoreGroupCases,
    getGroupTotalCount,
    loadMoreCases,
    loadMoreGroups,
    handleScroll,
    setupLoadMoreObserver,
    cleanupObserver
  };
}
