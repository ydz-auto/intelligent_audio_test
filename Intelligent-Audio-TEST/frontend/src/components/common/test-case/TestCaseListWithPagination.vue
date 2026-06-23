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
      
      <div v-if="hasMore && !isLoadingMore && paginatedTestCases.length > 0" class="load-more-trigger">
        <span class="load-more-hint">已显示 {{ paginatedTestCases.length }} / {{ filteredTestCases.length }} 条用例</span>
        <button class="btn btn-secondary btn-sm" @click="loadMore">
          <i class="fas fa-chevron-down"></i> 加载更多
        </button>
      </div>
      
      <div v-if="!hasMore && paginatedTestCases.length > 0 && filteredTestCases.length > pageSize" class="all-loaded">
        <span>已加载全部 {{ filteredTestCases.length }} 条用例</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
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
  isLoading: { type: Boolean, default: false }
});

const emit = defineEmits(['toggle-selection', 'action', 'page-change', 'page-size-change']);

const currentPage = ref(1);
const pageSize = ref(10);
const listContainerRef = ref<HTMLElement | null>(null);
const isLoadingMore = ref(false);
const hasMore = ref(true);

watch(() => props.testCases, () => {
  currentPage.value = 1;
}, { deep: true });

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
  if (isLoadingMore.value || !hasMore.value) return;
  isLoadingMore.value = true;
  setTimeout(() => {
    currentPage.value++;
    isLoadingMore.value = false;
    emit('page-change', currentPage.value);
  }, 200);
};

const handleScroll = (event: Event) => {
  const target = event.target as HTMLElement;
  const scrollBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
  if (scrollBottom < 80 && hasMore.value && !isLoadingMore.value) {
    loadMore();
  }
};

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
  scroll-behavior: smooth;
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
