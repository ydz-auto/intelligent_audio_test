<template>
  <div>
    <div class="test-case-list-with-pagination" ref="listContainerRef">
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
      
      <div class="empty-state" v-if="paginatedTestCases.filter(Boolean).length === 0">
        <i class="fas fa-inbox"></i>
        <p>没有找到测试用例</p>
        <p class="empty-state-hint">请尝试调整筛选条件或添加新的测试用例</p>
      </div>
      
      <div class="loading-state" v-if="isLoading">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>
    </div>
    
    <PaginationComponent 
      :current-page="currentPage"
      :page-size="pageSize"
      :total-items="filteredTestCases.length"
      @prev-page="handlePageChange(currentPage - 1)"
      @next-page="handlePageChange(currentPage + 1)"
      @go-to-page="handlePageChange"
      @page-size-change="handlePageSizeChange"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import TestCaseCard from './TestCaseCard.vue';
import PaginationComponent from '../PaginationComponent.vue';

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
const listContainerRef = ref(null);

watch(() => props.testCases, () => {
  currentPage.value = 1;
}, { deep: true });

watch(() => props.searchQuery, () => {
  currentPage.value = 1;
});

const filteredTestCases = computed(() => {
  let cases = [...props.testCases];
  
  // 先过滤掉 null/undefined 值
  cases = cases.filter(Boolean);
  
  if (props.searchQuery) {
    const query = props.searchQuery.toLowerCase();
    cases = cases.filter(testCase => {
      const idStr = String(testCase.id || '').toLowerCase();
      return idStr.includes(query) ||
             (testCase.name || '').toLowerCase().includes(query) ||
             (testCase.description || '').toLowerCase().includes(query) ||
             (testCase.tags && testCase.tags.some(tag => String(tag).toLowerCase().includes(query)));
    });
  }
  
  if (props.filter) {
    if (props.filter.tag && props.filter.tag !== 'all') {
      cases = cases.filter(testCase => testCase.tags && testCase.tags.includes(props.filter.tag));
    }
    
    if (props.filter.status) {
      cases = cases.filter(testCase => testCase.status === props.filter.status);
    }
    
    if (props.filter.customFilter && typeof props.filter.customFilter === 'function') {
      cases = cases.filter(props.filter.customFilter);
    }
  }
  
  return cases;
});

const paginatedTestCases = computed(() => {
  const startIndex = (currentPage.value - 1) * pageSize.value;
  const endIndex = startIndex + pageSize.value;
  // 确保 filteredTestCases.value 是数组
  const cases = Array.isArray(filteredTestCases.value) ? filteredTestCases.value : [];
  return cases.slice(startIndex, endIndex);
});

const handleToggleSelection = (caseId) => {
  emit('toggle-selection', caseId);
};

const handleAction = (event) => {
  emit('action', event);
};

const handlePageChange = (newPage) => {
  currentPage.value = newPage;
  if (listContainerRef.value) {
    listContainerRef.value.scrollTo({ top: 0, behavior: 'smooth' });
  }
  emit('page-change', newPage);
};

const handlePageSizeChange = (newPageSize) => {
  pageSize.value = newPageSize;
  currentPage.value = 1;
  if (listContainerRef.value) {
    listContainerRef.value.scrollTo({ top: 0, behavior: 'smooth' });
  }
  emit('page-size-change', newPageSize);
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
  max-height: calc(100vh - 280px);
  overflow-y: auto;
  padding-right: 8px;
  scroll-behavior: smooth;
}

/* 自定义滚动条样式 */
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

/* 分页组件间距 */
.pagination-container {
  margin-top: 16px;
}
</style>