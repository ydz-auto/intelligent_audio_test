<template>
  <div>
    <div class="test-case-list-with-pagination" ref="listContainerRef" @scroll="handleScroll">
      <TestCaseCard 
        v-for="testCase in paginatedTestCases" 
        :key="testCase?.id"
        :test-case="testCase" 
        :is-selected="testCase?.selected"
        :actions="actions"
        :show-checkbox="showCheckbox"
        :show-config="showConfig"
        @toggle-selection="handleToggleSelection"
        @action="handleAction"
      ></TestCaseCard>
      
      <div class="empty-state" v-if="paginatedTestCases.filter(Boolean).length === 0 && !isLoading">
        <i class="fas fa-inbox"></i>
        <p>没有找到测试用例</p>
        <p class="empty-state-hint">请尝试调整筛选条件或添加新的测试用例</p>
      </div>
      
      <div class="loading-state" v-if="isLoading">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>
      
      <div v-if="isLoadingMore" class="loading-more">
        <i class="fas fa-spinner fa-spin"></i>
        <span>加载更多用例...</span>
      </div>
      
      <div v-if="(hasMore || props.backendHasMore) && !isLoadingMore && paginatedTestCases.length > 0" class="load-more-trigger">
        <span class="load-more-hint">已显示 {{ paginatedTestCases.length }} / {{ filteredTestCases.length }} 条用例</span>
        <button class="btn btn-secondary btn-sm" @click="loadMore">
          <i class="fas fa-chevron-down"></i> 加载更多
        </button>
      </div>
      
      <div v-if="!hasMore && !props.backendHasMore && paginatedTestCases.length > 0 && filteredTestCases.length > pageSize" class="all-loaded">
        <span>已加载全部 {{ filteredTestCases.length }} 条用例</span>
      </div>

      <!-- 底部哨兵：常驻挂载，进入视口即触发加载。
        列表内容不足一屏时无法产生滚动事件，靠它保证“展开后也能继续加载”，
        内容超出后用户滚动内层列表也会让哨兵进入视口触发加载。 -->
      <div class="list-more-sentinel" ref="moreSentinelRef"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue';
import TestCaseCard from './TestCaseCard.vue';

interface TestCaseItem {
  id?: string | number;
  name?: string;
  description?: string;
  tags?: string[];
  status?: string;
  selected?: boolean;
  [key: string]: any;
}

const props = defineProps({
  testCases: { type: Array, default: () => [] },
  showCheckbox: { type: Boolean, default: true },
  showConfig: { type: Boolean, default: true },
  actions: { type: Array, default: () => [] },
  filter: { type: Object, default: () => ({}) },
  searchQuery: { type: String, default: '' },
  isLoading: { type: Boolean, default: false },
  // 分组视图下后端还有更多用例（store 分页未取完）时传入，供滚动/按钮触达后端加载
  backendHasMore: { type: Boolean, default: false },
  backendLoading: { type: Boolean, default: false }
});

const emit = defineEmits(['toggle-selection', 'action', 'page-change', 'page-size-change', 'load-more-backend']);

const currentPage = ref(1);
const pageSize = ref(10);
const listContainerRef = ref<HTMLElement | null>(null);
const isLoadingMore = ref(false);
const hasMore = ref(true);

// 数据集身份由父层 `:key="group/tagName"` 保证：分组/标签切换会重建实例，无需监听重置页码。
// 追加（后端加载更多）与选中状态变化都会重算 props.testCases，若一律重置，
// 已展开列表会缩回第一页造成跳动，因此这里不重置，仅搜索词变化时回到第一页。
watch(() => props.searchQuery, () => {
  currentPage.value = 1;
});

const filteredTestCases = computed(() => {
  let cases = [...props.testCases] as TestCaseItem[];
  
  cases = cases.filter(Boolean);
  
  if (props.searchQuery) {
    const query = props.searchQuery.toLowerCase();
    cases = cases.filter((testCase: TestCaseItem) => {
      const idStr = String(testCase.id || '').toLowerCase();
      return idStr.includes(query) ||
             (testCase.name || '').toLowerCase().includes(query) ||
             (testCase.description || '').toLowerCase().includes(query) ||
             (testCase.tags && testCase.tags.some((tag: string) => String(tag).toLowerCase().includes(query)));
    });
  }
  
  if (props.filter) {
    if (props.filter.tag && props.filter.tag !== 'all') {
      cases = cases.filter((testCase: TestCaseItem) => testCase.tags && testCase.tags.includes(props.filter.tag));
    }
    
    if (props.filter.status) {
      cases = cases.filter((testCase: TestCaseItem) => testCase.status === props.filter.status);
    }
    
    if (props.filter.customFilter && typeof props.filter.customFilter === 'function') {
      cases = cases.filter(props.filter.customFilter);
    }
  }
  
  return cases;
});

const paginatedTestCases = computed(() => {
  const endIndex = currentPage.value * pageSize.value;
  const cases = Array.isArray(filteredTestCases.value) ? filteredTestCases.value : [];
  hasMore.value = endIndex < cases.length;
  return cases.slice(0, endIndex);
});

const handleToggleSelection = (caseId: string | number) => {
  emit('toggle-selection', caseId);
};

const handleAction = (event: any) => {
  emit('action', event);
};

const loadMore = () => {
  if (isLoadingMore.value) return;
  if (hasMore.value) {
    // 前端缓冲内还有未展示的用例：本地翻页
    isLoadingMore.value = true;
    setTimeout(() => {
      currentPage.value++;
      isLoadingMore.value = false;
      emit('page-change', currentPage.value);
    }, 200);
  } else if (props.backendHasMore && !props.backendLoading) {
    // 前端缓冲已展示完、后端还有更多：请求下一批
    emit('load-more-backend');
  }
};

const handleScroll = (event: Event) => {
  const target = event.target as HTMLElement;
  const scrollBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
  if (scrollBottom < 80 && !isLoadingMore.value) {
    loadMore();
  }
};

// 底部哨兵 + 视口观察：不依赖内层列表自身是否可滚动。
// 内容不足一屏（无滚动事件）时哨兵仍在视口内，自动继续加载直到填满/取完；
// 内容超出后滚动内层列表，哨兵进入视口同样触发。
const moreSentinelRef = ref<HTMLElement | null>(null);
let moreObserver: IntersectionObserver | null = null;
const setupMoreObserver = () => {
  if (typeof IntersectionObserver === 'undefined') return;
  if (moreObserver) moreObserver.disconnect();
  moreObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting && !isLoadingMore.value && !props.backendLoading) {
        loadMore();
      }
    });
  }, { rootMargin: '100px' });
  if (moreSentinelRef.value) moreObserver.observe(moreSentinelRef.value);
};

// 每页加载后补一次检查：哨兵仍在视口内（尚未填满一屏）就继续加载下一页。
function checkAndContinueLoad() {
  if (isLoadingMore.value || props.backendLoading) return;
  const sentinel = moreSentinelRef.value;
  // 折叠卡片 display:none 时 offsetParent 为 null，跳过，避免对不可见列表自动加载
  if (!sentinel || !sentinel.offsetParent) return;
  const rect = sentinel.getBoundingClientRect();
  if (rect.top <= window.innerHeight + 100 && (hasMore.value || props.backendHasMore)) {
    loadMore();
  }
}

watch(paginatedTestCases, () => {
  nextTick(checkAndContinueLoad);
});

onMounted(() => {
  setupMoreObserver();
  nextTick(checkAndContinueLoad);
});

onBeforeUnmount(() => {
  if (moreObserver) {
    moreObserver.disconnect();
    moreObserver = null;
  }
});

defineExpose({
  resetPage: () => {
    currentPage.value = 1;
  },
  getCurrentPage: () => currentPage.value,
  getPageSize: () => pageSize.value
});
</script>

<style scoped>
.test-case-list-with-pagination {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 400px;
  overflow-y: auto;
  padding-right: 8px;
}

.test-case-list-with-pagination::-webkit-scrollbar {
  width: 6px;
}

.test-case-list-with-pagination::-webkit-scrollbar-track {
  background: var(--background-tertiary);
  border-radius: 3px;
}

.test-case-list-with-pagination::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
}

.test-case-list-with-pagination::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* 空状态样式 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 24px;
  text-align: center;
  background-color: var(--background-secondary);
  border-radius: var(--border-radius-lg);
  border: 1px dashed var(--border-color);
  margin-top: 16px;
  margin-bottom: 16px;
}

.empty-state i {
  font-size: 48px;
  color: var(--text-tertiary);
  margin-bottom: 16px;
}

.empty-state p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 16px;
}

.empty-state-hint {
  margin-top: 8px !important;
  font-size: 14px !important;
  color: var(--text-tertiary);
}

/* 加载状态样式 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 24px;
  background-color: var(--background-secondary);
  border-radius: var(--border-radius-lg);
  margin-top: 16px;
  margin-bottom: 16px;
}

.spinner {
  border: 4px solid var(--background-tertiary);
  border-top: 4px solid var(--primary-color);
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-state p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 16px;
}

/* 加载更多提示 */
.loading-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  color: var(--text-secondary);
  font-size: 14px;
}

.load-more-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 12px;
  border-top: 1px dashed var(--border-color);
  margin-top: 8px;
}

.load-more-hint {
  color: var(--text-tertiary);
  font-size: 12px;
}

/* 底部加载哨兵：保持可见性以便 IntersectionObserver 可靠触发 */
.list-more-sentinel {
  min-height: 2px;
}

.all-loaded {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  color: var(--text-tertiary);
  font-size: 12px;
  border-top: 1px dashed var(--border-color);
  margin-top: 8px;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
}
</style>
