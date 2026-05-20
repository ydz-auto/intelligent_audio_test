<template>
  <div class="filter-panel dimension-filter-panel">
    <div class="filter-header" v-if="title">
      <label class="filter-label">
        <i :class="iconClass"></i> {{ title }}
        <span class="filter-hint" v-if="selectedItems.length === 0">({{ emptyHint }})</span>
        <span class="filter-count" v-else>已选 {{ selectedItems.length }} 个</span>
      </label>
    </div>
    
    <div class="filter-search" v-if="showSearch">
      <div class="search-box">
        <i class="fas fa-search search-icon"></i>
        <input
          type="text"
          v-model="searchQuery"
          :placeholder="searchPlaceholder"
          class="search-input"
        />
        <button
          class="search-clear"
          :class="{ visible: searchQuery }"
          @click="searchQuery = ''"
        >
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>

    <div class="filter-items" :class="{ 'has-pagination': totalPages > 1 }">
      <div
        v-for="item in paginatedItems"
        :key="getItemKey(item)"
        :class="getItemClasses(item)"
        @click="handleItemClick(item)"
      >
        <i class="fas fa-check-circle check-icon" v-if="isItemSelected(item)"></i>
        <span class="item-name">{{ getItemLabel(item) }}</span>
        <span class="item-unit" v-if="item.unit">（{{ item.unit }}）</span>
      </div>
      <div v-if="filteredItems.length === 0" class="no-data-tip">
        {{ noDataHint }}
      </div>
    </div>

    <div class="filter-pagination" v-if="totalPages > 1">
      <button
        class="page-btn"
        :disabled="currentPage === 1"
        @click="currentPage--"
      >
        <i class="fas fa-chevron-left"></i>
      </button>
      <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
      <button
        class="page-btn"
        :disabled="currentPage === totalPages"
        @click="currentPage++"
      >
        <i class="fas fa-chevron-right"></i>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';

interface DimensionItem {
  id?: string | number;
  name: string;
  label?: string;
  unit?: string;
  description?: string;
  [key: string]: any;
}

interface Props {
  items: DimensionItem[];
  selectedItems: string[];
  title?: string;
  iconClass?: string;
  showSearch?: boolean;
  multiSelect?: boolean;
  pageSize?: number;
  searchPlaceholder?: string;
  emptyHint?: string;
  noDataHint?: string;
}

const props = withDefaults(defineProps<Props>(), {
  title: '评测维度',
  iconClass: 'fas fa-chart-line',
  showSearch: true,
  multiSelect: true,
  pageSize: 30,
  searchPlaceholder: '搜索评测维度...',
  emptyHint: '显示全部',
  noDataHint: '暂无评测维度'
});

const emit = defineEmits<{
  (e: 'update:selectedItems', items: string[]): void;
  (e: 'change', items: string[]): void;
  (e: 'itemClick', item: DimensionItem): void;
}>();

const searchQuery = ref('');
const currentPage = ref(1);
const localSelectedItems = ref<string[]>([]);

const selectedItems = computed({
  get: () => props.selectedItems?.length > 0 ? props.selectedItems : localSelectedItems.value,
  set: (val) => {
    localSelectedItems.value = val;
    emit('update:selectedItems', val);
  }
});

const filteredItems = computed(() => {
  if (!searchQuery.value.trim()) {
    return props.items;
  }
  const query = searchQuery.value.toLowerCase();
  return props.items.filter(item =>
    item.name.toLowerCase().includes(query) ||
    (item.label && item.label.toLowerCase().includes(query)) ||
    (item.description && item.description.toLowerCase().includes(query))
  );
});

const totalPages = computed(() => {
  return Math.ceil(filteredItems.value.length / props.pageSize) || 1;
});

const paginatedItems = computed(() => {
  const start = (currentPage.value - 1) * props.pageSize;
  const end = start + props.pageSize;
  return filteredItems.value.slice(start, end);
});

const getItemKey = (item: DimensionItem) => item.id ?? item.name;
const getItemLabel = (item: DimensionItem) => item.label ?? item.name;

const isItemSelected = (item: DimensionItem) => {
  return selectedItems.value.includes(item.name);
};

const getItemClasses = (item: DimensionItem) => {
  return {
    'filter-item': true,
    active: isItemSelected(item)
  };
};

const handleItemClick = (item: DimensionItem) => {
  const itemName = item.name;
  let newSelectedItems = [...selectedItems.value];
  const index = newSelectedItems.indexOf(itemName);

  if (index > -1) {
    newSelectedItems.splice(index, 1);
  } else {
    if (props.multiSelect) {
      newSelectedItems.push(itemName);
    } else {
      newSelectedItems = [itemName];
    }
  }

  selectedItems.value = newSelectedItems;
  emit('change', newSelectedItems);
  emit('itemClick', item);
};

watch(searchQuery, () => {
  currentPage.value = 1;
});

watch(() => props.items, () => {
  currentPage.value = 1;
}, { deep: true });

defineExpose({
  reset: () => {
    selectedItems.value = [];
    searchQuery.value = '';
    currentPage.value = 1;
  },
  selectAll: () => {
    selectedItems.value = props.items.map(item => item.name);
  },
  getSelectedItems: () => selectedItems.value
});
</script>

<style scoped>
.filter-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filter-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #333);
}

.filter-label i {
  color: var(--primary-color, #1890ff);
}

.filter-hint {
  font-size: 12px;
  color: var(--text-secondary, #999);
  font-weight: normal;
}

.filter-count {
  font-size: 12px;
  color: var(--primary-color, #1890ff);
  font-weight: normal;
}

.filter-search {
  position: relative;
}

.search-box {
  display: flex;
  align-items: center;
  background: var(--input-bg, #f5f5f5);
  border-radius: 6px;
  padding: 6px 10px;
  gap: 8px;
}

.search-icon {
  color: var(--text-secondary, #999);
  font-size: 12px;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 13px;
  outline: none;
  color: var(--text-primary, #333);
}

.search-input::placeholder {
  color: var(--text-placeholder, #bbb);
}

.search-clear {
  display: none;
  background: none;
  border: none;
  color: var(--text-secondary, #999);
  cursor: pointer;
  padding: 2px;
}

.search-clear.visible {
  display: block;
}

.filter-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.filter-items.has-pagination {
  max-height: 250px;
}

.filter-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  background: var(--tag-bg, #f0f0f0);
  color: var(--tag-text, #666);
  border: 1px solid transparent;
  transition: all 0.2s ease;
  user-select: none;
}

.filter-item:hover {
  background: var(--tag-hover-bg, #e0e0e0);
}

.filter-item.active {
  background: var(--primary-color-light, #e6f7ff);
  color: var(--primary-color, #1890ff);
  border-color: var(--primary-color, #1890ff);
}

.check-icon {
  font-size: 12px;
}

.item-name {
  font-weight: 500;
}

.item-unit {
  font-size: 11px;
  opacity: 0.8;
}

.no-data-tip {
  font-size: 12px;
  color: var(--text-secondary, #999);
  padding: 8px 0;
}

.filter-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-color, #eee);
}

.page-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid var(--border-color, #d9d9d9);
  border-radius: 4px;
  background: var(--bg-white, #fff);
  color: var(--text-secondary, #666);
  cursor: pointer;
  font-size: 12px;
}

.page-btn:hover:not(:disabled) {
  border-color: var(--primary-color, #1890ff);
  color: var(--primary-color, #1890ff);
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 12px;
  color: var(--text-secondary, #666);
}
</style>
