<template>
  <div class="filter-panel tag-filter-panel">
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
        @contextmenu.prevent="handleContextMenu($event, item)"
      >
        {{ getItemLabel(item) }}
        <span v-if="showMode && getItemMode(item)" class="mode-badge">
          {{ getItemMode(item) === 'or' ? 'OR' : 'AND' }}
        </span>
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

    <div
      v-if="showModeMenu && modeMenuPosition.visible"
      class="mode-menu"
      :style="{ top: modeMenuPosition.y + 'px', left: modeMenuPosition.x + 'px' }"
    >
      <div class="mode-menu-item" @click="setItemMode('or')">
        <span class="mode-icon or">OR</span>
        满足任一
      </div>
      <div class="mode-menu-item" @click="setItemMode('and')">
        <span class="mode-icon and">AND</span>
        满足所有
      </div>
      <div class="mode-menu-divider"></div>
      <div class="mode-menu-item remove" @click="removeSelectedItem">
        <i class="fas fa-times"></i> 移除
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';

type ItemMode = 'or' | 'and';

interface FilterItem {
  id?: string | number;
  name: string;
  label?: string;
  [key: string]: any;
}

interface Props {
  items: (string | FilterItem)[];
  selectedItems: string[];
  itemModes?: Record<string, ItemMode>;
  title?: string;
  iconClass?: string;
  showSearch?: boolean;
  showMode?: boolean;
  multiSelect?: boolean;
  pageSize?: number;
  searchPlaceholder?: string;
  emptyHint?: string;
  noDataHint?: string;
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  iconClass: 'fas fa-tag',
  showSearch: true,
  showMode: false,
  multiSelect: true,
  pageSize: 50,
  searchPlaceholder: '搜索...',
  emptyHint: '显示全部',
  noDataHint: '暂无数据'
});

const emit = defineEmits<{
  (e: 'update:selectedItems', items: string[]): void;
  (e: 'update:itemModes', modes: Record<string, ItemMode>): void;
  (e: 'change', items: string[], modes: Record<string, ItemMode>): void;
  (e: 'itemClick', item: string, mode?: ItemMode): void;
}>();

const searchQuery = ref('');
const currentPage = ref(1);
const localSelectedItems = ref<string[]>([]);
const localItemModes = ref<Map<string, ItemMode>>(new Map());

const showModeMenu = ref(false);
const modeMenuPosition = ref({ visible: false, x: 0, y: 0 });
const currentMenuItem = ref('');

const selectedItems = computed({
  get: () => props.selectedItems?.length > 0 ? props.selectedItems : localSelectedItems.value,
  set: (val) => {
    localSelectedItems.value = val;
    emit('update:selectedItems', val);
  }
});

const itemModes = computed({
  get: () => {
    if (props.itemModes && Object.keys(props.itemModes).length > 0) {
      return new Map(Object.entries(props.itemModes));
    }
    return localItemModes.value;
  },
  set: (val: Map<string, ItemMode>) => {
    localItemModes.value = val;
    emit('update:itemModes', Object.fromEntries(val));
  }
});

const normalizedItems = computed<FilterItem[]>(() => {
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
    (item.label && item.label.toLowerCase().includes(query))
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

const getItemKey = (item: FilterItem) => item.id ?? item.name;
const getItemLabel = (item: FilterItem) => item.label ?? item.name;

const isItemSelected = (item: FilterItem) => {
  return selectedItems.value.includes(item.name);
};

const getItemMode = (item: FilterItem): ItemMode | null => {
  return itemModes.value.get(item.name) || null;
};

const getItemClasses = (item: FilterItem) => {
  const mode = getItemMode(item);
  return {
    'filter-item': true,
    active: isItemSelected(item),
    'mode-or': mode === 'or',
    'mode-and': mode === 'and'
  };
};

const handleItemClick = (item: FilterItem) => {
  const itemName = item.name;
  const currentMode = itemModes.value.get(itemName);
  let newSelectedItems = [...selectedItems.value];
  let newItemModes = new Map(itemModes.value);

  if (!props.showMode) {
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
  } else {
    if (!currentMode) {
      newSelectedItems.push(itemName);
      newItemModes.set(itemName, 'and');
    } else if (currentMode === 'and') {
      newItemModes.set(itemName, 'or');
    } else if (currentMode === 'or') {
      const index = newSelectedItems.indexOf(itemName);
      if (index > -1) {
        newSelectedItems.splice(index, 1);
        newItemModes.delete(itemName);
      }
    }
  }

  selectedItems.value = newSelectedItems;
  itemModes.value = newItemModes;
  emit('change', newSelectedItems, Object.fromEntries(newItemModes));
  emit('itemClick', itemName, itemModes.value.get(itemName) || undefined);
};

const handleContextMenu = (event: MouseEvent, item: FilterItem) => {
  if (!props.showMode || !isItemSelected(item)) return;
  
  currentMenuItem.value = item.name;
  modeMenuPosition.value = { visible: true, x: event.pageX, y: event.pageY };
  showModeMenu.value = true;

  const closeMenu = (e: MouseEvent) => {
    if (!(e.target as HTMLElement).closest('.mode-menu')) {
      showModeMenu.value = false;
      modeMenuPosition.value.visible = false;
      document.removeEventListener('click', closeMenu);
    }
  };
  setTimeout(() => document.addEventListener('click', closeMenu), 0);
};

const setItemMode = (mode: ItemMode) => {
  if (!currentMenuItem.value) return;
  
  const newItemModes = new Map(itemModes.value);
  newItemModes.set(currentMenuItem.value, mode);
  itemModes.value = newItemModes;
  emit('change', [...selectedItems.value], Object.fromEntries(newItemModes));
  showModeMenu.value = false;
  modeMenuPosition.value.visible = false;
};

const removeSelectedItem = () => {
  if (!currentMenuItem.value) return;
  
  const newSelectedItems = selectedItems.value.filter(item => item !== currentMenuItem.value);
  const newItemModes = new Map(itemModes.value);
  newItemModes.delete(currentMenuItem.value);
  
  selectedItems.value = newSelectedItems;
  itemModes.value = newItemModes;
  emit('change', newSelectedItems, Object.fromEntries(newItemModes));
  showModeMenu.value = false;
  modeMenuPosition.value.visible = false;
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
    itemModes.value = new Map();
    searchQuery.value = '';
    currentPage.value = 1;
  },
  selectAll: () => {
    selectedItems.value = normalizedItems.value.map(item => item.name);
  },
  getSelectedItems: () => selectedItems.value,
  getItemModes: () => Object.fromEntries(itemModes.value)
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

.search-clear:hover {
  color: var(--text-primary, #333);
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
  padding: 4px 10px;
  border-radius: 4px;
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

.filter-item.mode-and {
  background: var(--success-color-light, #f6ffed);
  color: var(--success-color, #52c41a);
  border-color: var(--success-color, #52c41a);
}

.filter-item.mode-or {
  background: var(--warning-color-light, #fffbe6);
  color: var(--warning-color, #faad14);
  border-color: var(--warning-color, #faad14);
}

.mode-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.3);
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

.mode-menu {
  position: fixed;
  z-index: 10000;
  background: var(--bg-white, #fff);
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  padding: 4px 0;
  min-width: 120px;
}

.mode-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
  color: var(--text-primary, #333);
}

.mode-menu-item:hover {
  background: var(--hover-bg, #f5f5f5);
}

.mode-menu-item.remove {
  color: var(--danger-color, #ff4d4f);
}

.mode-icon {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 3px;
}

.mode-icon.or {
  background: var(--warning-color-light, #fffbe6);
  color: var(--warning-color, #faad14);
}

.mode-icon.and {
  background: var(--success-color-light, #f6ffed);
  color: var(--success-color, #52c41a);
}

.mode-menu-divider {
  height: 1px;
  background: var(--border-color, #eee);
  margin: 4px 0;
}
</style>
