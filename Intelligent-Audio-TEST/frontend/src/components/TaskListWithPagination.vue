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
import PaginationComponent from './common/PaginationComponent.vue';

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

<style>
.debug-info {
  background: #fff3cd !important;
  padding: 10px !important;
  margin-bottom: 10px !important;
  border: 1px solid #ffeeba !important;
}

.debug-info p {
  margin: 5px 0 !important;
  font-size: 14px !important;
  color: #856404 !important;
}
</style>
