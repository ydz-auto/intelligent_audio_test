<template>
  <div class="filter-panel group-filter-panel">
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
        <i class="fas fa-folder item-icon"></i>
        <span class="item-name">{{ getItemLabel(item) }}</span>
        <span class="item-count" v-if="item.count !== undefined">({{ item.count }})</span>
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

interface GroupItem {
  id?: string | number;
  name: string;
  label?: string;
  count?: number;
  description?: string;
  [key: string]: any;
}

interface Props {
  items: (string | GroupItem)[];
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
  title: '用例分组',
  iconClass: 'fas fa-list-check',
  showSearch: true,
  multiSelect: true,
  pageSize: 50,
  searchPlaceholder: '搜索分组...',
  emptyHint: '显示全部',
  noDataHint: '暂无分组'
});

const emit = defineEmits<{
  (e: 'update:selectedItems', items: string[]): void;
  (e: 'change', items: string[]): void;
  (e: 'itemClick', item: GroupItem): void;
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

const normalizedItems = computed<GroupItem[]>(() => {
  return props.items.map(item => {
    if (typeof item === 'string') {
      return { id: item, name: item, label: item };
    }
    return { ...item, id: item.id ?? item.name, label: item.label ?? item.name };
  });
});

const filteredItems = computed(() => {
  if (!searchQuery.value.trim()) {
    return normalizedItems.value;
  }
  const query = searchQuery.value.toLowerCase();
  return normalizedItems.value.filter(item =>
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

const getItemKey = (item: GroupItem) => item.id ?? item.name;
const getItemLabel = (item: GroupItem) => item.label ?? item.name;

const isItemSelected = (item: GroupItem) => {
  return selectedItems.value.includes(item.name);
};

const getItemClasses = (item: GroupItem) => {
  return {
    'filter-item': true,
    active: isItemSelected(item)
  };
};

const handleItemClick = (item: GroupItem) => {
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
    selectedItems.value = normalizedItems.value.map(item => item.name);
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
  gap: 6px;
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

.filter-item.active .item-icon {
  color: var(--primary-color, #1890ff);
}

.item-icon {
  font-size: 11px;
  color: var(--text-secondary, #999);
}

.item-name {
  font-weight: 500;
}

.item-count {
  font-size: 11px;
  opacity: 0.7;
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
