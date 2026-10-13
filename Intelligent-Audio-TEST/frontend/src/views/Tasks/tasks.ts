import { ref, computed, watch, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { Task } from '../../domain';
import { TaskStatus } from '@/domain/enums';
import { useTaskList } from '../../composables/task/useTaskList';
import { useTaskControl } from '../../composables/task/useTaskControl';
import { useTaskBatchOps } from '../../composables/task/useTaskBatchOps';
import { useTaskLogs } from '../../composables/task/useTaskLogs';
import { useTaskCharts } from '../../composables/task/useTaskCharts';
import { useTaskReport } from '../../composables/task/useTaskReport';
import { useFavorites } from '../../composables/favorite/useFavorites';
import { useModalControl, MODAL_TYPES } from '../../composables/modal/useModal';
import { useNotification } from '../../composables/modal/useNotification';

/**
 * useTasks - 轻量级协调层
 *
 * 组合以下子模块，暴露统一接口给 Tasks.vue 使用：
 * - useTaskList: 任务列表管理（获取、过滤、分页、排序、选择、标签）
 * - useTaskControl: 任务控制（pause/resume/stop/retry/reevaluate/delete/查看详情/报告）
 * - useTaskBatchOps: 批量操作（批量删除/导出/对比/恢复/合并）
 * - useTaskLogs: 日志查看（获取、过滤、刷新）
 * - useTaskCharts: 图表（任务类型/趋势/状态图表、时间粒度切换）
 * - useTaskReport: 报告编辑（结论编辑、报告保存/发布/关闭）
 */
export function useTasks() {
  const router = useRouter();

  // 创建共享的 tasks ref，供图表模块和列表模块共同引用
  const sharedTasks = ref<Task[]>([]);

  // 任务列表模块（注入共享的 tasks ref 和图表更新回调；
  // onTasksUpdated 由 fetchTasks 完成后异步触发，此时 chartsModule 已完成初始化）
  const listModule = useTaskList({
    tasks: sharedTasks,
    onTasksUpdated: () => chartsModule.updateCharts()
  });

  // 图表模块（INT-200：数据源为任务域全量聚合统计 taskStats，非当前页 tasks）
  const chartsModule = useTaskCharts(listModule.taskStats);

  // 任务控制模块
  const controlModule = useTaskControl(
    listModule.tasks,
    listModule.fetchTasks
  );

  // 批量操作模块
  const batchOpsModule = useTaskBatchOps(
    listModule.tasks,
    listModule.selectedTasks,
    listModule.fetchTasks
  );

  // 日志模块（依赖 filteredTasks）
  const logsModule = useTaskLogs(listModule.filteredTasks);

  // 报告模块
  const reportModule = useTaskReport(
    listModule.tasks,
    listModule.selectedTasks
  );

  // 收藏 / 回收站模块（INT-141）
  const favoritesModule = useFavorites('task');
  // INT-215：确认弹窗统一 BASIC_CONFIRM 模态 + 操作反馈（原先 favorite/purge 零反馈）
  const modalControl = useModalControl();
  const notification = useNotification();

  /** 回收站态（任务侧以状态筛选 deleted 承载，供工具栏/卡片动作可见性判定） */
  const taskTrashMode = computed(() => listModule.filters.value.status === 'deleted');

  /**
   * INT-215：回收站开关（对齐报告/用例的「工具栏回收站按钮」心智模型）。
   * 仍以 filters.status='deleted' 承载（批量恢复/彻底删除按钮可见性等既有逻辑不变），
   * 同时与收藏筛选互斥联动（回收站下 favorite 静默失效 → 进入时清空勾选态）。
   */
  const toggleTaskTrashMode = async () => {
    const next = !taskTrashMode.value;
    listModule.filters.value.status = next ? 'deleted' : '';
    if (next && listModule.favoriteOnly.value) {
      listModule.favoriteOnly.value = false;
    }
    // INT-215/S4 同口径：数据集切换清空选中集，防止普通态勾选的活跃任务
    // 流入回收站态批量彻底删除（误删活跃项）
    listModule.selectedTasks.value.clear();
    await listModule.applyFilters();
  };

  /** INT-215：收藏筛选切换（FavoriteTrashBar bar-toggle 口径，含刷新） */
  const handleTaskFavoriteFilterChange = async (value: boolean) => {
    listModule.favoriteOnly.value = value;
    await listModule.applyFilters();
  };

  /**
   * INT-298：action 归一化——TaskCard/TaskListWithPagination 事件载荷的 action 为
   * 操作对象（{id,...}），协调层直调（单测/合并面板源行）传 id 字符串，统一取 id 判定。
   * 修复 INT-215 起行内 favorite/restore/purge 因对象≠字符串恒假而落入无分支的回归。
   */
  const actionIdOf = (action: any): string =>
    typeof action === 'string' ? action : (action?.id ?? '');

  const handleTaskAction = async (payload: { action: any; task: any }) => {
    const actionId = actionIdOf(payload.action);
    if (actionId === 'favorite' || actionId === 'unfavorite') {
      try {
        await favoritesModule.toggleFavorite(payload.task.id);
        notification.success(favoritesModule.isFavorite(payload.task.id) ? '已收藏' : '已取消收藏');
      } catch (error) {
        notification.error('收藏操作失败: ' + (error instanceof Error ? error.message : '未知错误'));
      }
      return;
    }
    if (actionId === 'restore') {
      try {
        const result = await favoritesModule.restore([payload.task.id]);
        const restored = result?.restored_count ?? 0;
        if (restored > 0) {
          notification.success(`任务「${payload.task?.name ?? payload.task?.id}」已恢复`);
        } else {
          notification.info('无可恢复项（任务可能已被恢复）');
        }
        await listModule.fetchTasks();
      } catch (error) {
        notification.error('恢复任务失败: ' + (error instanceof Error ? error.message : '未知错误'));
      }
      return;
    }
    if (actionId === 'purge') {
      const name = payload.task?.name ?? payload.task?.id;
      let confirmed = false;
      try {
        confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
          title: '彻底删除任务',
          content: `彻底删除任务「${name}」？该操作不可恢复（仅管理员/所有者可执行）。`,
          confirmText: '彻底删除',
          cancelText: '取消',
          danger: true,
        });
      } catch {
        return; // 用户取消
      }
      if (!confirmed) return;
      try {
        const result = await favoritesModule.purge([payload.task.id]);
        const purged = result?.purged_count ?? 0;
        if (purged > 0) {
          notification.success(`任务「${name}」已彻底删除`);
        } else {
          notification.info('无可删除项（任务可能已被删除或不满足权限）');
        }
        await listModule.fetchTasks();
      } catch (error) {
        notification.error('彻底删除任务失败: ' + (error instanceof Error ? error.message : '未知错误'));
      }
      return;
    }
    await controlModule.handleTaskAction(payload);
  };

  const batchPurge = async () => {
    const ids = Array.from(listModule.selectedTasks.value);
    if (ids.length === 0) return;
    let confirmed = false;
    try {
      confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '批量彻底删除任务',
        content: `彻底删除选中的 ${ids.length} 个任务？该操作不可恢复（仅管理员/所有者可执行）。`,
        confirmText: '彻底删除',
        cancelText: '取消',
        danger: true,
      });
    } catch {
      return; // 用户取消
    }
    if (!confirmed) return;
    try {
      const result = await favoritesModule.purge(ids);
      const purged = result?.purged_count ?? 0;
      if (purged > 0) {
        notification.success(`已彻底删除 ${purged} 个任务`);
      } else {
        notification.info('无可删除项（任务可能已被删除或不满足权限）');
      }
      listModule.selectedTasks.value.clear();
      await listModule.fetchTasks();
    } catch (error) {
      notification.error('批量彻底删除失败: ' + (error instanceof Error ? error.message : '未知错误'));
    }
  };

  // ========== 协调逻辑 ==========

  const isTaskTypeModalVisible = ref(false);
  const currentTask = ref<Task | null>(null);

  // 任务数据导入导出弹窗（INT-25）
  const isDataExportDialogVisible = ref(false);
  const isDataImportDialogVisible = ref(false);

  const openDataExport = () => {
    isDataExportDialogVisible.value = true;
  };

  const openDataImport = () => {
    isDataImportDialogVisible.value = true;
  };

  const selectedTasksForExport = computed(() => {
    return listModule.tasks.value
      .filter(t => listModule.selectedTasks.value.has(t.id))
      .map(t => ({
        id: t.id,
        name: t.name,
        status: String(t.status ?? ''),
      }));
  });

  const handleDataImported = () => {
    listModule.fetchTasks();
  };

  const createNewTask = () => {
    isTaskTypeModalVisible.value = true;
  };

  const handleCreateTask = (data: { testType: string }) => {
    isTaskTypeModalVisible.value = false;
    if (data.testType === 'APITest') {
      router.push('/create-api-task');
    } else if (data.testType === 'E2ETest') {
      router.push('/create-e2e-task');
    }
  };

  const initTasks = async () => {
    await Promise.all([
      listModule.fetchTasks(),
      logsModule.fetchTaskLogs(),
      listModule.loadAlgorithmOptions()
    ]);
  };

  const resetAllStates = () => {
    listModule.resetAllStates();
  };

  // ========== 图表与生命周期协调（从 .vue 迁入） ==========

  /** INT-200：粒度切换 → 全量统计按新粒度重取趋势分桶后再重建图表 */
  const changeTimeGranularity = async (granularity: string) => {
    chartsModule.timeGranularity.value = granularity;
    listModule.statsGranularity.value = granularity;
    await listModule.fetchTaskStats();
    chartsModule.updateCharts();
  };

  const handleNameUpdated = ({ taskId, newName }: { taskId: string | number; newName: string }) => {
    console.log('[DEBUG] handleUpdateTaskName called:', { taskId, newName });
    controlModule.updateTaskName(taskId, newName);
  };

  const canMerge = computed(() => {
    if (listModule.selectedTasks.value.size < 2) return false;
    const selectedTasksArray = listModule.tasks.value.filter(t => listModule.selectedTasks.value.has(t.id));
    // 对齐 V9.7.10：已完成(completed)与已合并(merged)任务均可再次合并
    return selectedTasksArray.every(t => t.status === TaskStatus.COMPLETED || t.status === TaskStatus.MERGED);
  });

  const mergeButtonTitle = computed(() => {
    if (listModule.selectedTasks.value.size < 2) {
      return '请至少选择两个任务进行合并';
    }
    const selectedTasksArray = listModule.tasks.value.filter(t => listModule.selectedTasks.value.has(t.id));
    const incompleteTasks = selectedTasksArray.filter(t => t.status !== TaskStatus.COMPLETED && t.status !== TaskStatus.MERGED);
    if (incompleteTasks.length > 0) {
      const names = incompleteTasks.map(t => t.name).join(', ');
      return `以下任务未完成，无法合并: ${names}`;
    }
    return '点击将选中的已完成任务合并为一个新任务';
  });

  // 监听图表容器ref变化，初始化图表
  watch([chartsModule.taskTypeChartRef, chartsModule.taskTrendChartRef, chartsModule.taskStatusChartRef], () => {
    if (chartsModule.taskTypeChartRef.value && chartsModule.taskTrendChartRef.value && chartsModule.taskStatusChartRef.value) {
      chartsModule.updateCharts();
    }
  }, { deep: true });

  onMounted(async () => {
    await listModule.fetchTasks();
    listModule.applyFilters();
    // INT-141：加载当前用户收藏集合
    await favoritesModule.loadFavorites();
    // 初始化时获取日志
    await logsModule.refreshTaskLogs();

    // 初始化图表
    setTimeout(() => {
      if (chartsModule.taskTypeChartRef.value) {
        chartsModule.createTaskTypeChart(chartsModule.taskTypeChartRef.value);
      }
      if (chartsModule.taskTrendChartRef.value) {
        chartsModule.createTaskTrendChart(chartsModule.taskTrendChartRef.value);
      }
      if (chartsModule.taskStatusChartRef.value) {
        chartsModule.createTaskStatusChart(chartsModule.taskStatusChartRef.value);
      }
    }, 100);
  });

  // ========== 暴露统一接口（与原 useTasks 完全兼容） ==========

  return {
    // 列表相关
    tasks: listModule.tasks,
    filteredTasks: listModule.filteredTasks,
    selectedTasks: listModule.selectedTasks,
    currentPage: listModule.currentPage,
    pageSize: listModule.pageSize,
    sortConfig: listModule.sortConfig,
    selectedTags: listModule.selectedTags,
    searchTerm: listModule.searchTerm,
    filters: listModule.filters,
    customDateRange: listModule.customDateRange,
    favoriteOnly: listModule.favoriteOnly,
    tagCurrentPage: listModule.tagCurrentPage,
    tagPageSize: listModule.tagPageSize,
    allTags: listModule.allTags,
    totalTagPages: listModule.totalTagPages,
    currentTags: listModule.currentTags,
    totalTasks: listModule.totalTasks,
    domainTotal: listModule.domainTotal,
    taskStats: listModule.taskStats,
    pendingTasks: listModule.pendingTasks,
    queuedTasks: listModule.queuedTasks,
    inProgressTasks: listModule.inProgressTasks,
    completedTasks: listModule.completedTasks,
    failedTasks: listModule.failedTasks,
    deletedTasks: listModule.deletedTasks,
    totalPages: listModule.totalPages,
    paginatedTasks: listModule.paginatedTasks,
    isAllSelected: listModule.isAllSelected,
    algorithmOptions: listModule.algorithmOptions,
    loadAlgorithmOptions: listModule.loadAlgorithmOptions,
    fetchTasks: listModule.fetchTasks,
    applyFilters: listModule.applyFilters,
    handleSearch: listModule.handleSearch,
    sortTasks: listModule.sortTasks,
    toggleSort: listModule.toggleSort,
    clearCustomDateRange: listModule.clearCustomDateRange,
    toggleTag: listModule.toggleTag,
    toggleTaskSelection: listModule.toggleTaskSelection,
    toggleSelectAll: listModule.toggleSelectAll,
    cancelSelect: listModule.cancelSelect,
    handlePageChange: listModule.handlePageChange,
    handlePageSizeChange: listModule.handlePageSizeChange,

    // 控制相关
    isControlling: controlModule.isControlling,
    isGeneratingReport: controlModule.isGeneratingReport,
    pauseTask: controlModule.pauseTask,
    resumeTask: controlModule.resumeTask,
    stopTask: controlModule.stopTask,
    viewTaskDetails: controlModule.viewTaskDetails,
    viewTaskReport: controlModule.viewTaskReport,
    regenerateReport: controlModule.regenerateReport,
    editTask: controlModule.editTask,
    updateTaskName: controlModule.updateTaskName,
    retryTask: controlModule.retryTask,
    reevaluateTask: controlModule.reevaluateTask,
    deleteTask: controlModule.deleteTask,
    handleTaskAction,
    // 收藏 / 回收站（INT-141）
    isFavorite: favoritesModule.isFavorite,
    toggleFavorite: favoritesModule.toggleFavorite,
    favoriteIds: favoritesModule.favoriteIds,
    batchPurge,
    // INT-215：回收站工具栏（对齐报告/用例交互口径）
    taskTrashMode,
    toggleTaskTrashMode,
    handleTaskFavoriteFilterChange,
    getStatusText: controlModule.getStatusText,
    getStatusIcon: controlModule.getStatusIcon,
    getStepStatusText: controlModule.getStepStatusText,
    formatDate: controlModule.formatDate,

    // 批量操作
    batchDelete: batchOpsModule.batchDelete,
    batchCompare: batchOpsModule.batchCompare,
    batchMerge: batchOpsModule.batchMerge,
    batchRestore: batchOpsModule.batchRestore,
    batchExport: batchOpsModule.batchExport,

    // 日志相关
    taskLogs: logsModule.taskLogs,
    filteredTaskLogs: logsModule.filteredTaskLogs,
    taskLogSearchTerm: logsModule.taskLogSearchTerm,
    taskLogLevelFilter: logsModule.taskLogLevelFilter,
    taskLogFilter: logsModule.taskLogFilter,
    fetchTaskLogs: logsModule.fetchTaskLogs,
    refreshTaskLogs: logsModule.refreshTaskLogs,
    filterTaskLogs: logsModule.filterTaskLogs,

    // 图表相关
    taskTypeChartRef: chartsModule.taskTypeChartRef,
    taskTrendChartRef: chartsModule.taskTrendChartRef,
    taskStatusChartRef: chartsModule.taskStatusChartRef,
    createTaskTypeChart: chartsModule.createTaskTypeChart,
    createTaskTrendChart: chartsModule.createTaskTrendChart,
    createTaskStatusChart: chartsModule.createTaskStatusChart,
    updateCharts: chartsModule.updateCharts,
    changeTimeGranularity,
    isActive: chartsModule.isActive,

    // 报告相关
    showComparisonReport: reportModule.showComparisonReport,
    comparisonTasks: reportModule.comparisonTasks,
    comparisonReport: reportModule.comparisonReport,
    isEditingConclusion: reportModule.isEditingConclusion,
    isEditingReport: reportModule.isEditingReport,
    reportConclusion: reportModule.reportConclusion,
    reportServiceData: reportModule.reportServiceData,
    reportName: reportModule.reportName,
    reportDevices: reportModule.reportDevices,
    deviceApiColumns: reportModule.deviceApiColumns,
    caseExecutionColumns: reportModule.caseExecutionColumns,
    extractDevicesFromTasks: reportModule.extractDevicesFromTasks,
    updateComparisonData: reportModule.updateComparisonData,
    toggleDeviceSelection: reportModule.toggleDeviceSelection,
    deviceApiComparisonData: reportModule.deviceApiComparisonData,
    caseExecutionData: reportModule.caseExecutionData,
    updateComparisonReportConclusion: reportModule.updateComparisonReportConclusion,
    closeComparisonReport: reportModule.closeComparisonReport,
    saveComparisonReport: reportModule.saveComparisonReport,
    publishComparisonReport: reportModule.publishComparisonReport,
    startEditingConclusion: reportModule.startEditingConclusion,
    saveConclusion: reportModule.saveConclusion,
    toggleEditConclusion: reportModule.toggleEditConclusion,
    cancelEditConclusion: reportModule.cancelEditConclusion,
    toggleEditReport: reportModule.toggleEditReport,
    cancelEditReport: reportModule.cancelEditReport,

    // 创建任务相关
    isTaskTypeModalVisible,
    currentTask,
    createNewTask,
    handleCreateTask,

    // 任务数据导入导出（INT-25）
    isDataExportDialogVisible,
    isDataImportDialogVisible,
    openDataExport,
    openDataImport,
    selectedTasksForExport,
    handleDataImported,

    // 生命周期
    initTasks,
    resetAllStates,

    // 协调逻辑
    handleNameUpdated,
    canMerge,
    mergeButtonTitle,
  };
}
