<template>
  <div class="task-list-with-pagination">
    <div class="task-list">

      <TaskCard
        v-for="taskItem in paginatedTasks"
        :key="taskItem.id"
        :task="taskItem"
        :isSelected="isSelected(taskItem)"
        :actions="actions"
        :showCheckbox="showCheckbox"
        :showConfig="showConfig"
        @toggle-selection="handleToggleSelection"
        @action="handleAction"
        @name-updated="handleNameUpdated"
      />

      <!-- 合并任务：源任务列表（默认收起） -->
      <template v-for="taskItem in paginatedTasks" :key="`merged-${taskItem.id}`">
        <div
          v-if="(taskItem.sourceTasks?.length ?? 0) > 0"
          class="merged-source-list"
        >
          <div class="merged-source-list-title" @click="toggleMergedSources(taskItem.id)">
            <i class="fas fa-object-ungroup"></i> 源任务列表（{{ taskItem.sourceTasks.length }} 个）
            <i class="fas merged-source-toggle" :class="expandedMergedSources.has(taskItem.id) ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
          </div>
          <template v-if="expandedMergedSources.has(taskItem.id)">
            <div v-for="src in taskItem.sourceTasks" :key="src.id" class="merged-source-row">
              <div class="merged-source-row-info">
                <span class="merged-source-row-name" :title="src.name">{{ src.name }}</span>
                <span class="merged-source-status" :class="src.status">{{ src.status }}</span>
                <span class="merged-source-row-cases"><i class="fas fa-list-alt"></i>用例 {{ src.completedCases ?? 0 }}/{{ src.totalCases ?? 0 }}</span>
                <span v-if="src.createdAt" class="merged-source-row-time"><i class="fas fa-calendar-alt"></i>{{ src.createdAt }}</span>
              </div>
            </div>
          </template>
        </div>
      </template>

      <div class="empty-state" v-if="paginatedTasks.length === 0">
        <i class="fas fa-tasks"></i>
        <p>没有找到任务</p>
        <p class="empty-state-hint">请尝试调整筛选条件或添加新的任务</p>
      </div>

      <div class="loading-state" v-if="isLoading">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>
    </div>

    <PaginationComponent
      :currentPage="props.currentPage"
      :pageSize="props.pageSize"
      :totalItems="props.totalItems"
      :totalPages="props.totalPages"
      @prev-page="handlePrevPage"
      @next-page="handleNextPage"
      @go-to-page="handleGoToPage"
      @page-size-change="handlePageSizeChange"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import TaskCard from './TaskCard.vue';
import PaginationComponent from '../common/data/PaginationComponent.vue';

const props = defineProps({
  tasks: {type: Array, default: () => []},
  showCheckbox: {type: Boolean, default: true},
  showConfig: {type: Boolean, default: true},
  actions: {type: Array, default: () => []},
  searchQuery: {type: String, default: ''},
  isLoading: {type: Boolean, default: false},
  isSelected: {type: Function, default: (task) => task.selected || false},
  totalItems: {type: Number, default: 0},
  totalPages: {type: Number, default: 1},
  currentPage: {type: Number, default: 1},
  pageSize: {type: Number, default: 10}
});

const emit = defineEmits(['toggle-selection', 'action', 'page-change', 'page-size-change', 'name-updated']);

/** 合并任务源任务列表展开状态（taskId -> expanded） */
const expandedMergedSources = ref(new Set());

const toggleMergedSources = (taskId) => {
  const next = new Set(expandedMergedSources.value);
  if (next.has(taskId)) {
    next.delete(taskId);
  } else {
    next.add(taskId);
  }
  expandedMergedSources.value = next;
};

watch(() => props.tasks, () => {
}, { deep: true });

watch(() => props.searchQuery, () => {
  emit('page-change', 1);
});

const handleNameUpdated = (data) => {
  emit('name-updated', data);
};

const filteredTasks = computed(() => {
  if (!props.searchQuery) {
    return [...props.tasks];
  }
  const query = props.searchQuery.toLowerCase();
  return props.tasks.filter(task => {
    return (
      (task.name && task.name.toLowerCase().includes(query)) ||
      (task.id && task.id.toString().includes(query)) ||
      (task.description && task.description.toLowerCase().includes(query))
    );
  });
});

const paginatedTasks = computed(() => {
  return props.tasks;
});

const handleToggleSelection = (taskId) => {
  emit('toggle-selection', taskId);
};

const handleAction = (event) => {
  emit('action', event);
};

const handlePrevPage = () => {
  if (props.currentPage > 1) {
    emit('page-change', props.currentPage - 1);
  }
};

const handleNextPage = () => {
  if (props.currentPage < props.totalPages) {
    emit('page-change', props.currentPage + 1);
  }
};

const handleGoToPage = (newPage) => {
  emit('page-change', newPage);
};

const handlePageSizeChange = (newPageSize) => {
  emit('page-size-change', newPageSize);
};

defineExpose({
  resetPage: () => {
    emit('page-change', 1);
  },
  getCurrentPage: () => props.currentPage,
  getPageSize: () => props.pageSize
});
</script>

<style scoped>
.debug-info {
  background: var(--color-amber-100);
  padding: 10px;
  margin-bottom: 10px;
  border: 1px solid var(--color-amber-200);
}

.debug-info p {
  margin: 5px 0;
  font-size: 14px;
  color: var(--color-yellow-800);
}

/* ===== 合并任务源任务列表 ===== */
.merged-source-list {
  border: 1px dashed var(--color-gray-300, #d1d5db);
  border-radius: 8px;
  margin: 0 0 12px;
  padding: 0;
  background: var(--color-gray-50, #f9fafb);
}

.merged-source-list-title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-gray-700, #374151);
  cursor: pointer;
  user-select: none;
}

.merged-source-list-title:hover {
  background: var(--color-gray-100, #f3f4f6);
}

.merged-source-toggle {
  margin-left: auto;
  color: var(--color-gray-400, #9ca3af);
}

.merged-source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  border-top: 1px solid var(--color-gray-200, #e5e7eb);
}

.merged-source-row-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.merged-source-row-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-gray-800, #1f2937);
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.merged-source-status {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 10px;
  background: var(--color-gray-200, #e5e7eb);
  color: var(--color-gray-700, #374151);
}

.merged-source-status.completed {
  background: var(--color-green-100, #d1fae5);
  color: var(--color-green-700, #047857);
}

.merged-source-status.merged {
  background: var(--color-blue-100, #dbeafe);
  color: var(--color-blue-700, #1d4ed8);
}

.merged-source-row-cases {
  font-size: 12px;
  color: var(--color-gray-500, #6b7280);
}

.merged-source-row-time {
  font-size: 12px;
  color: var(--color-gray-400, #9ca3af);
}

.merged-source-list.empty-source-hint {
  padding: 0;
}

.merged-source-list.empty-source-hint .merged-source-row {
  border-top: none;
  justify-content: flex-start;
}
</style>
