import { ref, computed, watch, type Ref } from 'vue';
import { tasksPort } from './tasksPort';
import { algorithmPort } from '../algorithm/algorithmPort';
import { useGlobalAlgorithmStore } from '../../store/globalAlgorithmStore';
import type { AlgorithmOption, Task, TaskDomainStats } from '../../domain';
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
  /** INT-273：任务类型过滤（api/e2e/mixed，服务端按派生 device_type 口径过滤） */
  type: string;
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
    type: '',
    timeRange: 'all',
    dateRange: [null, null] as [Date | null, Date | null]
  });
  // INT-141：仅收藏筛选（后端 favorite=true）
  const favoriteOnly = ref(false);
  // INT-423/467：可见性筛选（'' | 'shared' | 'private'；服务端 ?visibility= 过滤）
  const visibilityFilter = ref('');
  const customDateRange = ref({ start: '', end: '' });
  const algorithmOptions = ref<{ value: string; label: string }[]>([]);
  // INT-288：列表拉取加载态 / 错误态（错误文案供视图渲染错误条；失败保留旧数据不清空）
  const isLoading = ref(false);
  const error = ref('');

  // ===== 全局算法联动（B03 全局切换器 / React INT-1033 对齐）=====
  // 日常/收藏列表算法过滤由全局切换器承载：切换一次全局生效，请求自动附 algorithm_type。
  // 陈旧持久化值（localStorage `iatp:algorithm:v1`）不在真实 /algorithm/options 内时视为无效——
  // 不继承、不发 algorithm_type（后端契约：无 algorithm_type 即返回全部；无效值会把列表筛空）。
  const globalStore = useGlobalAlgorithmStore();
  globalStore.init();
  globalStore.loadAlgorithms();

  /** 全局选中值是否在真实算法选项内（有效才继承；算法列表未加载/为空 → 视为无效回落「全部算法」） */
  const globalAlgorithmValid = computed(() => {
    const type = globalStore.selectedType;
    return Boolean(type && globalStore.algorithmList.some((o: AlgorithmOption) => o.value === type));
  });

  /** 有效算法过滤口径：页面内算法筛选优先（INT-1112 保留页面徽章，与全局联动）；未设则继承有效全局算法 */
  const effectiveAlgorithmType = computed(() => {
    const pageAlgo = filters.value.algorithmType;
    if (pageAlgo && pageAlgo !== 'all') return pageAlgo;
    if (globalAlgorithmValid.value) return globalStore.selectedType;
    return '';
  });

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
    isLoading.value = true;
    error.value = '';
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
        // INT-141：回收站模式（已删除）走专用 deleted 参数
        if (filters.value.status === 'deleted') {
          params.deleted = true;
        } else {
          // INT-301 F1（UX 审计打回）：执行筛选改走 execution_status 派生参数
          // （命中行执行徽章 == 筛选值）；不再按原始 Task.status 裸匹配。
          params.executionStatus = filters.value.status;
        }
      }
      // INT-141：仅收藏过滤（favorite=true，服务端按当前用户 JWT 过滤）。
      // INT-320：发送侧守卫对齐文档 §3.3 / 报告·用例侧口径——回收站态
      // （filters.status==='deleted'）下收藏过滤不得生效，互斥不依赖入口清空顺序
      if (favoriteOnly.value && filters.value.status !== 'deleted') {
        params.favorite = true;
      }
      // INT-423/467：可见性过滤（visibility=private|shared，服务端行级过滤；
      // 回收站态互斥——已删任务不参与可见性筛选）
      if (visibilityFilter.value && filters.value.status !== 'deleted') {
        params.visibility = visibilityFilter.value;
      }
      // INT-1112：全局算法联动（页面徽章优先；未设页面筛选则继承有效全局算法；
      // 陈旧/无效全局值静默回落「全部算法」——不发 algorithm_type，后端即返回全部）
      const algorithmType = effectiveAlgorithmType.value;
      if (algorithmType) {
        params.algorithmType = algorithmType;
      }
      // INT-273：任务类型筛选（api/e2e/mixed，服务端按派生 device_type 口径过滤）
      if (filters.value.type && filters.value.type !== 'all') {
        params.taskType = filters.value.type;
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
    } catch (err) {
      console.error('Failed to fetch tasks:', err);
      // INT-288：失败不清空旧数据，仅暴露错误文案供视图渲染错误条（区别于空态）
      error.value = '加载任务失败，请稍后重试';
    } finally {
      isLoading.value = false;
    }
  };

  const applyFilters = () => {
    currentPage.value = 1;
    fetchTasks();
  };

  // INT-1112：全局算法切换（右上角切换器或页面徽章联动）→ 有效过滤口径变化即重新查询。
  // 用 effectiveAlgorithmType（而非裸 selectedType）做触发源：算法列表异步加载后若确认
  // 持久化值为有效算法，也能自动补一次按算法查询；无效/未选中不触发，避免加载期双请求。
  watch(effectiveAlgorithmType, () => {
    fetchTasks();
  });

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
    filters.value = { status: '', evaluationStatus: '', algorithmType: '', type: '', timeRange: 'all', dateRange: [null, null] };
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
    visibilityFilter,
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
    // INT-288：加载态 / 错误态
    isLoading,
    error,
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
    // INT-1112：全局算法联动（页面徽章与全局切换器联动时的有效过滤口径）
    globalAlgorithmValid,
    effectiveAlgorithmType,
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
