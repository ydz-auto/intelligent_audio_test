import { ref, computed, type Ref } from 'vue';
import { tasksApi, algorithmApi } from '../utils/api';
import type { Task } from '../shared/types';

/**
 * 任务列表管理组合式函数
 *
 * 职责：
 * - 任务列表的获取、搜索、过滤、分页、排序
 * - 标签管理（分页展示）
 * - 选择管理（单选、全选、取消选择）
 * - 算法选项加载
 * - 任务统计计算
 */

export interface TaskFilters {
  status: string;
  type: string;
  algorithmType: string;
  timeRange: string;
  dateRange: [Date | null, Date | null];
}

export interface UseTaskListOptions {
  onTasksUpdated?: () => void;
  tasks?: Ref<Task[]>;
}

export function useTaskList(options?: UseTaskListOptions) {
  const onTasksUpdated = options?.onTasksUpdated;

  // 支持外部注入 tasks ref，便于与其他模块共享同一引用
  const tasks = options?.tasks ?? ref<Task[]>([]);
  const filteredTasks = ref<Task[]>([]);
  const selectedTasks = ref<Set<string | number>>(new Set());
  const currentPage = ref(1);
  const pageSize = ref(10);
  const totalItems = ref(0);
  const sortConfig = ref({ field: 'createdAt', order: 'desc' });
  const selectedTags = ref<string[]>([]);
  const searchTerm = ref('');
  const filters = ref<TaskFilters>({
    status: '',
    type: '',
    algorithmType: '',
    timeRange: 'all',
    dateRange: [null, null] as [Date | null, Date | null]
  });
  const customDateRange = ref({ start: '', end: '' });
  const algorithmOptions = ref<{ value: string; label: string }[]>([]);

  const tagCurrentPage = ref(1);
  const tagPageSize = ref(15);

  const allTags = computed(() => {
    const tags = new Set<string>();
    tasks.value.forEach(task => {
      if (task.tags) {
        task.tags.forEach(tag => tags.add(tag));
      }
    });
    return Array.from(tags);
  });

  const totalTagPages = computed(() => Math.ceil(allTags.value.length / tagPageSize.value) || 1);
  const currentTags = computed(() => {
    const start = (tagCurrentPage.value - 1) * tagPageSize.value;
    return allTags.value.slice(start, start + tagPageSize.value);
  });

  const totalTasks = computed(() => totalItems.value);
  const pendingTasks = computed(() => tasks.value.filter(t => t.status === 'pending' || t.status === 'queued').length);
  const inProgressTasks = computed(() => tasks.value.filter(t => t.status === 'running').length);
  const completedTasks = computed(() => tasks.value.filter(t => t.status === 'completed').length);
  const failedTasks = computed(() => tasks.value.filter(t => t.status === 'failed').length);
  const deletedTasks = computed(() => tasks.value.filter(t => t.deleted).length);
  const queuedTasks = computed(() => tasks.value.filter(t => t.status === 'queued').length);

  const totalPages = computed(() => {
    const pages = Math.ceil(totalItems.value / pageSize.value) || 1;
    return pages;
  });
  const paginatedTasks = computed(() => filteredTasks.value);

  const isAllSelected = computed(() => {
    return paginatedTasks.value.length > 0 && paginatedTasks.value.every(t => selectedTasks.value.has(t.id));
  });

  async function loadAlgorithmOptions() {
    try {
      const data = await algorithmApi.getOptions();
      algorithmOptions.value = [
        { value: 'all', label: '全部算法' },
        ...(data?.algorithms || []).map((algo: any) => ({
          value: algo.value,
          label: algo.name || algo.value
        }))
      ];
    } catch (error) {
      console.error('加载算法选项失败:', error);
      algorithmOptions.value = [
        { value: 'all', label: '全部算法' },
        { value: 'translation', label: '翻译' },
        { value: 'asr', label: 'ASR识别' },
        { value: 'speaker_recognition', label: '说话人识别' },
        { value: 'tts', label: '语音合成' }
      ];
    }
  }

  const fetchTasks = async () => {
    try {
      const params: Record<string, any> = {
        page: currentPage.value,
        per_page: pageSize.value
      };

      if (searchTerm.value) {
        params.search = searchTerm.value;
      }

      if (filters.value.status && filters.value.status !== 'all') {
        params.status = filters.value.status;
      }
      if (filters.value.type && filters.value.type !== 'all') {
        params.type = filters.value.type;
      }
      if (filters.value.algorithmType && filters.value.algorithmType !== 'all') {
        params.algorithm_type = filters.value.algorithmType;
      }
      if (filters.value.timeRange && filters.value.timeRange !== 'all') {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

        switch (filters.value.timeRange) {
          case 'today':
            params.start_date = today.toISOString();
            break;
          case 'yesterday':
            const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
            params.start_date = yesterday.toISOString();
            params.end_date = today.toISOString();
            break;
          case 'week':
            const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
            params.start_date = weekAgo.toISOString();
            break;
          case 'month':
            const monthAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
            params.start_date = monthAgo.toISOString();
            break;
          case 'custom':
            if (customDateRange.value.start) {
              params.start_date = new Date(customDateRange.value.start).toISOString();
            }
            if (customDateRange.value.end) {
              const endDate = new Date(customDateRange.value.end);
              endDate.setHours(23, 59, 59, 999);
              params.end_date = endDate.toISOString();
            }
            break;
        }
      }

      const response = await tasksApi.getAll(params) as any;

      let taskList: any[] = [];
      let total = 0;

      if (response?.items) {
        taskList = response.items;
        total = response.total || taskList.length;
      } else if (response?.data?.items) {
        taskList = response.data.items;
        total = response.data.total || taskList.length;
      } else if (Array.isArray(response)) {
        taskList = response;
        total = response.length;
      } else {
        taskList = response || [];
      }

      tasks.value = taskList;
      totalItems.value = total;
      filteredTasks.value = taskList;

      if (onTasksUpdated) {
        setTimeout(() => {
          onTasksUpdated();
        }, 0);
      }
    } catch (error) {
      console.error('Failed to fetch tasks:', error);
    }
  };

  const applyFilters = () => {
    currentPage.value = 1;
    fetchTasks();
  };

  const handleSearch = () => {
    currentPage.value = 1;
    fetchTasks();
  };

  const handlePageChange = (page: number) => {
    currentPage.value = page;
    fetchTasks();
  };

  const handlePageSizeChange = (size: number) => {
    pageSize.value = size;
    currentPage.value = 1;
    fetchTasks();
  };

  const sortTasks = () => {
    const { field, order } = sortConfig.value;
    filteredTasks.value.sort((a, b) => {
      const valA = (a as any)[field];
      const valB = (b as any)[field];
      if (valA < valB) return order === 'asc' ? -1 : 1;
      if (valA > valB) return order === 'asc' ? 1 : -1;
      return 0;
    });
  };

  const toggleSort = (field: string) => {
    if (sortConfig.value.field === field) {
      sortConfig.value.order = sortConfig.value.order === 'asc' ? 'desc' : 'asc';
    } else {
      sortConfig.value.field = field;
      sortConfig.value.order = 'desc';
    }
    sortTasks();
  };

  const clearCustomDateRange = () => {
    customDateRange.value = { start: '', end: '' };
    filters.value.timeRange = 'all';
    applyFilters();
  };

  const toggleTag = (tag: string) => {
    const index = selectedTags.value.indexOf(tag);
    if (index > -1) {
      selectedTags.value.splice(index, 1);
    } else {
      selectedTags.value.push(tag);
    }
    applyFilters();
  };

  const toggleTaskSelection = (task: any) => {
    const id = task.id || task;
    if (selectedTasks.value.has(id)) {
      selectedTasks.value.delete(id);
    } else {
      selectedTasks.value.add(id);
    }
  };

  const toggleSelectAll = () => {
    if (isAllSelected.value) {
      paginatedTasks.value.forEach(t => selectedTasks.value.delete(t.id));
    } else {
      paginatedTasks.value.forEach(t => selectedTasks.value.add(t.id));
    }
  };

  const cancelSelect = () => {
    selectedTasks.value.clear();
  };

  const resetAllStates = () => {
    searchTerm.value = '';
    selectedTags.value = [];
    filters.value = { status: '', type: '', algorithmType: '', timeRange: 'all', dateRange: [null, null] };
    customDateRange.value = { start: '', end: '' };
    currentPage.value = 1;
    applyFilters();
  };

  return {
    tasks,
    filteredTasks,
    selectedTasks,
    currentPage,
    pageSize,
    totalItems,
    sortConfig,
    selectedTags,
    searchTerm,
    filters,
    customDateRange,
    algorithmOptions,
    tagCurrentPage,
    tagPageSize,
    allTags,
    totalTagPages,
    currentTags,
    totalTasks,
    pendingTasks,
    inProgressTasks,
    completedTasks,
    failedTasks,
    deletedTasks,
    queuedTasks,
    totalPages,
    paginatedTasks,
    isAllSelected,
    loadAlgorithmOptions,
    fetchTasks,
    applyFilters,
    handleSearch,
    handlePageChange,
    handlePageSizeChange,
    sortTasks,
    toggleSort,
    clearCustomDateRange,
    toggleTag,
    toggleTaskSelection,
    toggleSelectAll,
    cancelSelect,
    resetAllStates,
  };
}
