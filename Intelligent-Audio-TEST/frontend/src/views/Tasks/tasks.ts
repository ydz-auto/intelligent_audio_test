import { ref, computed, watch, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { reportService } from '../../services/reportService';
import type { Task } from '../../shared/types';
import { useTaskList } from '../../composables/task/useTaskList';
import { useTaskControl } from '../../composables/task/useTaskControl';
import { useTaskBatchOps } from '../../composables/task/useTaskBatchOps';
import { useTaskLogs } from '../../composables/task/useTaskLogs';
import { useTaskCharts } from '../../composables/task/useTaskCharts';
import { useTaskReport } from '../../composables/task/useTaskReport';

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

  // 图表模块（引用 sharedTasks）
  const chartsModule = useTaskCharts(sharedTasks);

  // 任务列表模块（注入共享的 tasks ref 和图表更新回调）
  const listModule = useTaskList({
    tasks: sharedTasks,
    onTasksUpdated: () => chartsModule.updateCharts()
  });

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

  // ========== 协调逻辑 ==========

  const isTaskTypeModalVisible = ref(false);
  const currentTask = ref<Task | null>(null);

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

  const handleNameUpdated = ({ taskId, newName }: { taskId: string | number; newName: string }) => {
    console.log('[DEBUG] handleUpdateTaskName called:', { taskId, newName });
    controlModule.updateTaskName(taskId, newName);
  };

  const canMerge = computed(() => {
    if (listModule.selectedTasks.value.size < 2) return false;
    const selectedTasksArray = listModule.tasks.value.filter(t => listModule.selectedTasks.value.has(t.id));
    return selectedTasksArray.every(t => t.status === 'completed');
  });

  const mergeButtonTitle = computed(() => {
    if (listModule.selectedTasks.value.size < 2) {
      return '请至少选择两个任务进行合并';
    }
    const selectedTasksArray = listModule.tasks.value.filter(t => listModule.selectedTasks.value.has(t.id));
    const incompleteTasks = selectedTasksArray.filter(t => t.status !== 'completed');
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
    tagCurrentPage: listModule.tagCurrentPage,
    tagPageSize: listModule.tagPageSize,
    allTags: listModule.allTags,
    totalTagPages: listModule.totalTagPages,
    currentTags: listModule.currentTags,
    totalTasks: listModule.totalTasks,
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
    editTask: controlModule.editTask,
    updateTaskName: controlModule.updateTaskName,
    retryTask: controlModule.retryTask,
    reevaluateTask: controlModule.reevaluateTask,
    deleteTask: controlModule.deleteTask,
    handleTaskAction: controlModule.handleTaskAction,
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
    changeTimeGranularity: chartsModule.changeTimeGranularity,
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

    // 服务引用
    reportService,

    // 生命周期
    initTasks,
    resetAllStates,

    // 协调逻辑
    handleNameUpdated,
    canMerge,
    mergeButtonTitle,
  };
}
