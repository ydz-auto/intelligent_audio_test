import { ref, computed, type Ref } from 'vue';
import { tasksPort } from './tasksPort';
import { algorithmPort } from '../algorithm/algorithmPort';
import type { Task, TaskDomainStats } from '../../domain';
import { TaskStatus } from '../../domain/enums';
import { usePagination } from '../usePagination';

/**
 * 任务列表管理组合式函数
 *
 * 职责：
 * - 任务列表的获取、搜索、过滤、分页、排序
 * - 标签管理（分页展示）
 * - 选择管理（单选、全选、取消选择）
 * - 算法选项加载
 * - 任务统计（INT-200：走 /tasks/stats 全量聚合，与列表筛选/分页无关）
 */

export interface TaskFilters {
  status: string;
  /** INT-301：评估状态过滤（与执行状态并列） */
  evaluationStatus: string;
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
    evaluationStatus: '',
    algorithmType: '',
    timeRange: 'all',
    dateRange: [null, null] as [Date | null, Date | null]
  });
  // INT-141：仅收藏筛选（后端 favorite=true）
  const favoriteOnly = ref(false);
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

  // 标签分页：使用通用分页 composable
  const { totalPages: totalTagPages, paginatedItems: currentTags } = usePagination(allTags, tagPageSize, { currentPage: tagCurrentPage });

  // INT-200：统计卡/图表数据源改为任务域全量聚合（/tasks/stats），
  // 不再由当前页 tasks 过滤得出（分页下当前页统计与真实总量不符）
  const statsGranularity = ref('day');
  const taskStats = ref<TaskDomainStats | null>(null);

  const fetchTaskStats = async () => {
    try {
      taskStats.value = await tasksPort.getDomainStats(statsGranularity.value);
    } catch (error) {
      console.error('Failed to fetch task stats:', error);
    }
  };

  const totalTasks = computed(() => totalItems.value);
  // 统计卡（全量口径；total 为列表分页 total，与统计卡「总任务数」解耦）
  const domainTotal = computed(() => taskStats.value?.total ?? 0);
  const pendingTasks = computed(() =>
    (taskStats.value?.statusCounts[TaskStatus.PENDING] ?? 0) + (taskStats.value?.statusCounts[TaskStatus.QUEUED] ?? 0));
  const inProgressTasks = computed(() => taskStats.value?.statusCounts[TaskStatus.RUNNING] ?? 0);
  const completedTasks = computed(() => taskStats.value?.statusCounts[TaskStatus.COMPLETED] ?? 0);
  const failedTasks = computed(() => taskStats.value?.statusCounts[TaskStatus.FAILED] ?? 0);
  const deletedTasks = computed(() => taskStats.value?.deletedTotal ?? 0);
  const queuedTasks = computed(() => taskStats.value?.statusCounts[TaskStatus.QUEUED] ?? 0);

  // 任务分页为服务端分页，totalItems 由 API 返回
  // 此处用 totalItems 长度的占位数组驱动 totalPages 计算
  const placeholderForTotal = computed(() => Array(totalItems.value).fill(0));
  const { totalPages } = usePagination(placeholderForTotal, pageSize, { currentPage });
  const paginatedTasks = computed(() => filteredTasks.value);

  const isAllSelected = computed(() => {
    return paginatedTasks.value.length > 0 && paginatedTasks.value.every(t => selectedTasks.value.has(t.id));
  });

  async function loadAlgorithmOptions() {
    try {
      const data = await algorithmPort.getOptions();
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
      // 查询参数保持 camelCase（TaskListQuery），snake_case 化由 tasksApi 内部完成
      const params: Record<string, any> = {
        page: currentPage.value,
        perPage: pageSize.value
      };

      if (searchTerm.value) {
        params.search = searchTerm.value;
      }

      if (filters.value.status && filters.value.status !== 'all') {
        // INT-141：回收站模式（已删除）走专用 deleted 参数，其余按任务状态过滤
        if (filters.value.status === 'deleted') {
          params.deleted = true;
        } else {
          params.status = filters.value.status;
        }
      }
      // INT-141：仅收藏过滤（favorite=true，服务端按当前用户 JWT 过滤）
      if (favoriteOnly.value) {
        params.favorite = true;
      }
      if (filters.value.algorithmType && filters.value.algorithmType !== 'all') {
        params.algorithmType = filters.value.algorithmType;
      }
      // INT-301：评估状态过滤（与执行状态并列）
      if (filters.value.evaluationStatus && filters.value.evaluationStatus !== 'all') {
        params.evaluationStatus = filters.value.evaluationStatus;
      }
      if (filters.value.timeRange && filters.value.timeRange !== 'all') {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

        switch (filters.value.timeRange) {
          case 'today':
            params.startTime = today.toISOString();
            break;
          case 'yesterday':
            const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
            params.startTime = yesterday.toISOString();
            params.endTime = today.toISOString();
            break;
          case 'week':
            const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
            params.startTime = weekAgo.toISOString();
            break;
          case 'month':
            const monthAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
            params.startTime = monthAgo.toISOString();
            break;
          case 'custom':
            if (customDateRange.value.start) {
              params.startTime = new Date(customDateRange.value.start).toISOString();
            }
            if (customDateRange.value.end) {
              const endDate = new Date(customDateRange.value.end);
              endDate.setHours(23, 59, 59, 999);
              params.endTime = endDate.toISOString();
            }
            break;
        }
      }

      const response = await tasksPort.getAll(params) as any;

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

      // INT-200：列表数据变化（增删/状态流转）后同步刷新全量统计，
      // 先于 onTasksUpdated（图表据此重建），保证图表读到新统计
      await fetchTaskStats();

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

  // 注：此处分页导航函数需在页码变更后触发 fetchTasks() 拉取服务端数据，
  // 与 usePagination 的纯客户端导航语义不同，因此保留手写实现。
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
    filters.value = { status: '', evaluationStatus: '', algorithmType: '', timeRange: 'all', dateRange: [null, null] };
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
    favoriteOnly,
    algorithmOptions,
    tagCurrentPage,
    tagPageSize,
    allTags,
    totalTagPages,
    currentTags,
    totalTasks,
    domainTotal,
    taskStats,
    statsGranularity,
    fetchTaskStats,
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
