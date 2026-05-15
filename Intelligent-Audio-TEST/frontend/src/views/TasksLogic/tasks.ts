import { ref, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import { tasksApi, logsApi, algorithmApi } from '../../utils/api';
import { reportService } from '../../services/reportService';
import type { Task, Log } from '../../shared/types';
import { createTaskTypeChart, createTaskTrendChart, createTaskStatusChart } from '../../utils/chartUtils';
import { Chart } from 'chart.js/auto';
import { useModalControl, MODAL_TYPES } from '../../composables/useModal';
import { useNotification } from '../../composables/useNotification';

interface UILog extends Log {
  time: string;
}

export function useTasks() {
  const router = useRouter();
  const modalControl = useModalControl();
  const notification = useNotification();

  const tasks = ref<Task[]>([]);
  const filteredTasks = ref<Task[]>([]);
  const selectedTasks = ref<Set<string | number>>(new Set());
  const currentPage = ref(1);
  const pageSize = ref(10);
  const sortConfig = ref({ field: 'createdAt', order: 'desc' });
  const selectedTags = ref<string[]>([]);
  const searchTerm = ref('');
  const filters = ref({
    status: '',
    type: '',
    algorithmType: '',
    timeRange: 'all',
    dateRange: [null, null] as [Date | null, Date | null]
  });
  const customDateRange = ref({ start: '', end: '' });
  const algorithmOptions = ref<{ value: string; label: string }[]>([]);

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
  const tagCurrentPage = ref(1);
  const tagPageSize = ref(15);
  const isEditingReport = ref(false);
  const isEditingConclusion = ref(false);
  
  const isTaskTypeModalVisible = ref(false);
  const currentTask = ref<Task | null>(null);
  const isViewingReport = ref(false);
  const isControlling = ref<Set<string | number>>(new Set());

  const taskLogs = ref<UILog[]>([]);
  const taskLogSearchTerm = ref('');
  const taskLogLevelFilter = ref('all');
  const taskLogFilter = ref('all');
  const filteredTaskLogs = ref<UILog[]>([]);

  let typeChartInstance: Chart | null = null;
  let trendChartInstance: Chart | null = null;
  let statusChartInstance: Chart | null = null;

  // 图表容器ref，用于绑定到DOM元素
  const taskTypeChartRef = ref<HTMLCanvasElement | null>(null);
  const taskTrendChartRef = ref<HTMLCanvasElement | null>(null);
  const taskStatusChartRef = ref<HTMLCanvasElement | null>(null);

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

  const totalTasks = computed(() => tasks.value.length);
  const pendingTasks = computed(() => tasks.value.filter(t => t.status === 'pending' || t.status === 'queued').length);
  const inProgressTasks = computed(() => tasks.value.filter(t => t.status === 'running').length);
  const completedTasks = computed(() => tasks.value.filter(t => t.status === 'completed').length);
  const failedTasks = computed(() => tasks.value.filter(t => t.status === 'failed').length);
  const deletedTasks = computed(() => tasks.value.filter(t => t.deleted).length);
  const queuedTasks = computed(() => tasks.value.filter(t => t.status === 'queued').length);

  const totalPages = computed(() => {
    const pages = Math.ceil(filteredTasks.value.length / pageSize.value) || 1;
    console.log('[DEBUG] totalPages computed:', pages, 'filteredTasks.length:', filteredTasks.value.length, 'pageSize:', pageSize.value);
    return pages;
  });
  const paginatedTasks = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value;
    return filteredTasks.value.slice(start, start + pageSize.value);
  });

  const isAllSelected = computed(() => {
    return paginatedTasks.value.length > 0 && paginatedTasks.value.every(t => selectedTasks.value.has(t.id));
  });

  const reportConclusion = computed({
    get: () => reportService.comparisonReport.value?.conclusion || '',
    set: (val) => {
      if (reportService.comparisonReport.value) {
        reportService.comparisonReport.value.conclusion = val;
      }
    }
  });
  const reportName = computed({
    get: () => reportService.comparisonReport.value?.title || '',
    set: (val) => {
      if (reportService.comparisonReport.value) {
        reportService.comparisonReport.value.title = val;
      }
    }
  });
  const reportDevices = computed(() => reportService.devices.value);
  const reportServiceData = computed(() => reportService.comparisonReport.value);

  const fetchTasks = async () => {
    try {
      const response = await tasksApi.getAll({ per_page: 10000 }) as any;
      console.log('[DEBUG] fetchTasks response:', response);
      console.log('[DEBUG] response type:', typeof response);
      console.log('[DEBUG] Is array?', Array.isArray(response));
      console.log('[DEBUG] response.data:', response?.data);
      console.log('[DEBUG] response.items:', response?.items);
      
      let taskList: any[] = [];
      if (Array.isArray(response)) {
        taskList = response;
      } else if (response?.items) {
        taskList = response.items;
      } else if (response?.data?.items) {
        taskList = response.data.items;
      } else if (response?.data && Array.isArray(response.data)) {
        taskList = response.data;
      } else {
        taskList = response || [];
      }
      
      console.log('[DEBUG] taskList length:', taskList.length);
      tasks.value = taskList;
      applyFilters();
      setTimeout(() => {
        updateCharts();
      }, 0);
    } catch (error) {
      console.error('Failed to fetch tasks:', error);
    }
  };

  const applyFilters = () => {
    console.log('[DEBUG] applyFilters called, tasks.value length:', tasks.value.length);
    let result = [...tasks.value];

    result = result.filter(t => !t.deleted);

    if (searchTerm.value) {
      const term = searchTerm.value.toLowerCase();
      result = result.filter(t => 
        (t.name && t.name.toLowerCase().includes(term)) || 
        (t.id && t.id.toString().includes(term))
      );
    }

    if (filters.value.status && filters.value.status !== 'all') {
      result = result.filter(t => t.status === filters.value.status);
    }

    if (filters.value.type && filters.value.type !== 'all') {
      result = result.filter(t => t.type === filters.value.type);
    }

    if (filters.value.algorithmType && filters.value.algorithmType !== 'all') {
      result = result.filter(t => t.algorithmType === filters.value.algorithmType);
    }

    if (filters.value.timeRange && filters.value.timeRange !== 'all') {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
      
      switch (filters.value.timeRange) {
        case 'today':
          result = result.filter(t => new Date(t.createdAt || '').getTime() >= today);
          break;
        case 'yesterday':
          const yesterday = today - 24 * 60 * 60 * 1000;
          result = result.filter(t => {
            const time = new Date(t.createdAt || '').getTime();
            return time >= yesterday && time < today;
          });
          break;
        case 'week':
          const weekAgo = today - 7 * 24 * 60 * 60 * 1000;
          result = result.filter(t => new Date(t.createdAt || '').getTime() >= weekAgo);
          break;
        case 'month':
          const monthAgo = today - 30 * 24 * 60 * 60 * 1000;
          result = result.filter(t => new Date(t.createdAt || '').getTime() >= monthAgo);
          break;
        case 'custom':
          if (customDateRange.value.start) {
            const start = new Date(customDateRange.value.start).getTime();
            result = result.filter(t => new Date(t.createdAt || '').getTime() >= start);
          }
          if (customDateRange.value.end) {
            const endDate = new Date(customDateRange.value.end);
            endDate.setHours(23, 59, 59, 999);
            result = result.filter(t => new Date(t.createdAt || '').getTime() <= endDate.getTime());
          }
          break;
      }
    }

    if (selectedTags.value.length > 0) {
      result = result.filter(t => {
        if (!t.tags) return false;
        const taskTags = Array.isArray(t.tags) ? t.tags : [];
        return selectedTags.value.every(tag => {
          return taskTags.some(tTag => {
            if (typeof tTag === 'string') return tTag === tag;
            if (typeof tTag === 'object' && tTag !== null) {
              return (tTag as any).name === tag;
            }
            return false;
          });
        });
      });
    }

    filteredTasks.value = result;
    console.log('[DEBUG] filteredTasks.value length:', filteredTasks.value.length);
    sortTasks();
    currentPage.value = 1;
  };

  const handleSearch = () => {
    applyFilters();
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

  const handleTaskAction = (event: any) => {
    const { action, task } = event;
    switch (action.id) {
      case 'view-details':
        viewTaskDetails(task.id);
        break;
      case 'view-report':
        viewTaskReport(task);
        break;
      case 'retry':
        retryTask(task.id);
        break;
      case 'reevaluate':
        reevaluateTask(task.id);
        break;
      case 'delete':
        deleteTask(task.id);
        break;
      case 'pause':
        pauseTask(task.id);
        break;
      case 'resume':
        resumeTask(task.id);
        break;
      case 'stop':
        stopTask(task.id);
        break;
    }
  };

  const pauseTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;
    
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '暂停任务',
      content: '确定要暂停该测试任务吗？',
      confirmText: '暂停',
      cancelText: '取消'
    });

    if (confirmed) {
      isControlling.value.add(taskId);
      try {
        await tasksApi.control(taskId, 'pause');
        await fetchTasks();
      } catch (error: any) {
        console.error('Failed to pause task:', error);
      } finally {
        isControlling.value.delete(taskId);
      }
    }
  };

  const resumeTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;

    isControlling.value.add(taskId);
    try {
      const task = tasks.value.find(t => t.id === taskId);
      if (task?.status === 'stopped') {
        await tasksApi.start(taskId);
      } else {
        await tasksApi.control(taskId, 'resume');
      }
      await fetchTasks();
    } catch (error: any) {
      console.error('Failed to resume task:', error);
    } finally {
      isControlling.value.delete(taskId);
    }
  };

  const stopTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;

    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '停止任务',
      content: '确定要停止该测试任务吗？停止后将无法恢复。',
      confirmText: '停止',
      cancelText: '取消',
      danger: true
    });

    if (confirmed) {
      isControlling.value.add(taskId);
      try {
        await tasksApi.control(taskId, 'stop');
        await fetchTasks();
      } catch (error: any) {
        console.error('Failed to stop task:', error);
      } finally {
        isControlling.value.delete(taskId);
      }
    }
  };

  const viewTaskDetails = async (taskId: string | number) => {
    try {
      modalControl.open(MODAL_TYPES.TASK_DETAIL, { taskId });
    } catch (error) {
      console.error('Failed to view task details:', error);
    }
  };

  const viewTaskReport = async (task: Task) => {
    try {
      await reportService.viewTaskReport(task);
      isViewingReport.value = true;
      // 滚动到报告区域
      setTimeout(() => {
        const reportElement = document.getElementById('task-comparison-report-container');
        if (reportElement) {
          reportElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }, 100);
    } catch (error) {
      console.error('Failed to view task report:', error);
    }
  };

  const editTask = async (taskId: string | number) => {
    try {
      modalControl.open(MODAL_TYPES.TASK_DETAIL, { taskId });
    } catch (error) {
      console.error('Failed to edit task:', error);
    }
  };

  const updateTaskName = async (taskId: string | number, newName: string) => {
    console.log('[DEBUG] updateTaskName called:', { taskId, newName });
    try {
      await tasksApi.update(taskId, { name: newName });
      const taskIndex = tasks.value.findIndex(t => t.id === taskId);
      if (taskIndex !== -1) {
        tasks.value[taskIndex].name = newName;
      }
      const filteredIndex = filteredTasks.value.findIndex(t => t.id === taskId);
      if (filteredIndex !== -1) {
        filteredTasks.value[filteredIndex].name = newName;
      }
      notification.success('任务名称已更新');
    } catch (error) {
      console.error('Failed to update task name:', error);
      notification.error('更新任务名称失败');
    }
  };

  const retryTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;
    
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '重试任务',
      content: '确定要重试该测试任务吗？',
      confirmText: '重试',
      cancelText: '取消'
    });

    if (confirmed) {
      isControlling.value.add(taskId);
      try {
        await tasksApi.retry(taskId);
        await fetchTasks();
      } catch (error) {
        console.error('Failed to retry task:', error);
      } finally {
        isControlling.value.delete(taskId);
      }
    }
  };

  const reevaluateTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;
    
    const result = await modalControl.open(MODAL_TYPES.REEVALUATE, {
      content: '请选择重新评估类型'
    });

    if (result?.reevaluateType) {
      const reevaluateType = result.reevaluateType;
      const reextractDeviceOutput = result.reextractDeviceOutput || false;
      isControlling.value.add(taskId);
      let pollInterval: any = null;
      
      try {
        const apiResult = await tasksApi.reevaluate(taskId, reevaluateType, reextractDeviceOutput) as any;
        console.log('reevaluate result:', apiResult);
        await fetchTasks();
        console.log('tasks after reevaluate:', tasks.value.find((t: any) => t.id === taskId));
        
        if (apiResult?.data?.message) {
          notification.info(apiResult.data.message);
        } else {
          notification.success('重新评估任务已提交');
        }
        
        pollInterval = setInterval(async () => {
          await fetchTasks();
          const task = tasks.value.find((t: any) => t.id === taskId);
          console.log('poll task status:', task?.status);
          if (task && task.status === 'completed') {
            clearInterval(pollInterval);
            pollInterval = null;
            isControlling.value.delete(taskId);
            notification.success('评估完成');
          } else if (task && task.status !== 'evaluating') {
            clearInterval(pollInterval);
            pollInterval = null;
            isControlling.value.delete(taskId);
          }
        }, 3000);
        
        setTimeout(() => {
          if (pollInterval) {
            clearInterval(pollInterval);
            isControlling.value.delete(taskId);
          }
        }, 120000);
        
      } catch (error: any) {
        console.error('Failed to reevaluate task:', error);
        notification.error(error?.response?.data?.message || error?.message || '重新评估失败，请稍后重试');
        if (pollInterval) {
          clearInterval(pollInterval);
          isControlling.value.delete(taskId);
        }
      }
    }
  };

  const deleteTask = async (taskId: string | number) => {
    if (isControlling.value.has(taskId)) return;
    
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '删除任务',
      content: '确定要删除该任务吗？',
      confirmText: '删除',
      cancelText: '取消',
      danger: true
    });

    if (confirmed) {
      isControlling.value.add(taskId);
      try {
        await tasksApi.delete(taskId);
        await fetchTasks();
      } catch (error) {
        console.error('Failed to delete task:', error);
      } finally {
        isControlling.value.delete(taskId);
      }
    }
  };

  const batchDelete = async () => {
    if (selectedTasks.value.size === 0) return;
    if (confirm(`确定要删除选中的 ${selectedTasks.value.size} 个任务吗？`)) {
      try {
        const ids = Array.from(selectedTasks.value);
        await tasksApi.batchAction('delete', ids as any);
        selectedTasks.value.clear();
        await fetchTasks();
      } catch (error) {
        console.error('Failed to batch delete tasks:', error);
      }
    }
  };

  const batchExport = async () => {
    if (selectedTasks.value.size === 0) return;
    try {
      const ids = Array.from(selectedTasks.value);
      const result = await modalControl.open(MODAL_TYPES.IMPORT_EXPORT, {
        mode: 'export',
        title: '批量导出任务',
        supportedFormats: ['excel', 'json'],
        exportFields: [
          { key: 'id', label: '任务ID', defaultChecked: true },
          { key: 'name', label: '任务名称', defaultChecked: true },
          { key: 'description', label: '任务描述', defaultChecked: false },
          { key: 'type', label: '任务类型', defaultChecked: true },
          { key: 'status', label: '任务状态', defaultChecked: true },
          { key: 'createdAt', label: '创建时间', defaultChecked: true },
          { key: 'tags', label: '任务标签', defaultChecked: false },
          { key: 'deviceCount', label: '设备数量', defaultChecked: true },
          { key: 'caseCount', label: '用例数量', defaultChecked: true }
        ],
        advancedOptions: [
          {
            key: 'includeDetails',
            label: '包含详细信息',
            type: 'boolean',
            defaultValue: false
          },
          {
            key: 'format',
            label: '导出格式',
            type: 'select',
            defaultValue: 'excel',
            options: [
              { value: 'excel', label: 'Excel' },
              { value: 'json', label: 'JSON' }
            ]
          }
        ]
      });
      
      if (result) {
        const format = result.config.format || 'excel';
        const blob = await reportService.exportReport(ids[0], format);
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `tasks_export_${new Date().getTime()}.${format === 'excel' ? 'xlsx' : format}`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } catch (error) {
      console.error('Failed to batch export tasks:', error);
    }
  };

  const batchCompare = async () => {
    if (selectedTasks.value.size < 2) {
      alert('请至少选择两个任务进行对比');
      return;
    }
    try {
      const selectedTasksArray = tasks.value.filter(t => selectedTasks.value.has(t.id));
      const taskIds = selectedTasksArray.map(t => t.id);
      await reportService.batchCompare(taskIds, selectedTasksArray);
      // 滚动到报告区域
      setTimeout(() => {
        const reportElement = document.getElementById('task-comparison-report-container');
        if (reportElement) {
          reportElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }, 100);
    } catch (error) {
      console.error('Failed to batch compare tasks:', error);
      alert('生成对比报告失败，请稍后重试');
    }
  };

  const batchRestore = async () => {
    if (selectedTasks.value.size === 0) return;
    try {
      const ids = Array.from(selectedTasks.value);
      await tasksApi.batchAction('restore', ids as any);
      selectedTasks.value.clear();
      await fetchTasks();
    } catch (error) {
      console.error('Failed to batch restore tasks:', error);
    }
  };

  const batchMerge = async () => {
    if (selectedTasks.value.size < 2) {
      alert('请至少选择两个任务进行合并');
      return;
    }
    
    const selectedTasksArray = tasks.value.filter(t => selectedTasks.value.has(t.id));
    const incompleteTasks = selectedTasksArray.filter(t => t.status !== 'completed');
    if (incompleteTasks.length > 0) {
      const names = incompleteTasks.map(t => t.name).join(', ');
      alert(`以下任务未完成，无法合并: ${names}`);
      return;
    }
    
    const confirmed = await modalControl.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '合并任务',
      content: `确定要合并选中的 ${selectedTasks.value.size} 个任务吗？合并后将会创建一个新的任务，原任务将被标记为已合并。`,
      confirmText: '合并',
      cancelText: '取消'
    });

    if (!confirmed) return;

    try {
      const ids = Array.from(selectedTasks.value);
      const result = await tasksApi.mergeTasks(ids as any) as any;
      selectedTasks.value.clear();
      await fetchTasks();
      alert(`合并成功！新任务: ${result.merged_task_name || result.name || '合并任务'}`);
    } catch (error: any) {
      console.error('Failed to merge tasks:', error);
      alert(error.message || '合并失败，请稍后重试');
    }
  };

  const closeComparisonReport = () => {
    reportService.comparisonTasks.value = [];
    reportService.comparisonReport.value = {
      id: '',
      name: '任务对比报告',
      type: 'comparison',
      status: 'draft',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      description: '',
      summary: {
        totalCases: 0,
        passedCases: 0,
        failedCases: 0,
        passRate: 0,
        avgScore: 0,
        completedCases: 0,
        allMetrics: [],
        detailedResults: [],
        deviceStats: [],
        apiStats: []
      }
    } as any;
  };

  const saveComparisonReport = async () => {
    try {
      if (reportService.comparisonReport.value) {
        await reportService.saveReport(reportService.comparisonReport.value);
        alert('报告已保存');
      }
    } catch (error) {
      console.error('Failed to save report:', error);
    }
  };

  const publishComparisonReport = async () => {
    try {
      if (reportService.comparisonReport.value?.id) {
        await reportService.publishReport(reportService.comparisonReport.value.id);
        alert('报告已发布');
      }
    } catch (error) {
      console.error('Failed to publish report:', error);
    }
  };

  const startEditingConclusion = () => {
    isEditingConclusion.value = true;
  };

  const saveConclusion = async () => {
    try {
      const selectedTasksArray = tasks.value.filter(t => selectedTasks.value.has(t.id));
      await reportService.updateComparisonReportConclusion(selectedTasksArray);
      if (reportService.comparisonReport.value) {
        await reportService.saveReport(reportService.comparisonReport.value);
      }
      isEditingConclusion.value = false;
    } catch (error: any) {
      console.error('Failed to save conclusion:', error);
      alert('结论保存失败: ' + (error.message || '未知错误'));
    }
  };

  const toggleEditConclusion = () => {
    isEditingConclusion.value = !isEditingConclusion.value;
  };

  const cancelEditConclusion = () => {
    isEditingConclusion.value = false;
  };

  const toggleEditReport = () => {
    isEditingReport.value = !isEditingReport.value;
  };

  const cancelEditReport = () => {
    isEditingReport.value = false;
  };

  const createTaskTypeChartFn = (ctx: HTMLCanvasElement | null) => {
    if (!ctx) return;
    if (typeChartInstance) typeChartInstance.destroy();
    typeChartInstance = createTaskTypeChart(ctx, tasks.value);
  };

  const createTaskTrendChartFn = (ctx: HTMLCanvasElement | null, granularity: string = 'day') => {
    if (!ctx) return;
    if (trendChartInstance) trendChartInstance.destroy();
    trendChartInstance = createTaskTrendChart(ctx, tasks.value, { granularity });
  };

  const createTaskStatusChartFn = (ctx: HTMLCanvasElement | null) => {
    if (!ctx) return;
    if (statusChartInstance) statusChartInstance.destroy();
    statusChartInstance = createTaskStatusChart(ctx, tasks.value);
  };

  const updateCharts = () => {
    // 当任务数据更新时，重新创建所有图表实例
    if (taskTypeChartRef.value) {
      createTaskTypeChartFn(taskTypeChartRef.value);
    }
    if (taskTrendChartRef.value) {
      createTaskTrendChartFn(taskTrendChartRef.value, timeGranularity.value);
    }
    if (taskStatusChartRef.value) {
      createTaskStatusChartFn(taskStatusChartRef.value);
    }
  };

  const timeGranularity = ref('day');

  const changeTimeGranularity = (granularity: string) => {
    timeGranularity.value = granularity;
    updateCharts();
  };

  const isActive = (granularity: string) => {
    return timeGranularity.value === granularity;
  };

  const initTasks = async () => {
    await Promise.all([
      fetchTasks(),
      fetchTaskLogs(),
      loadAlgorithmOptions()
    ]);
  };

  const resetAllStates = () => {
    searchTerm.value = '';
    selectedTags.value = [];
    filters.value = { status: '', type: '', algorithmType: '', timeRange: 'all', dateRange: [null, null] };
    customDateRange.value = { start: '', end: '' };
    currentPage.value = 1;
    applyFilters();
  };

  const fetchTaskLogs = async () => {
    try {
      const response = await logsApi.getAll({ 
        module: 'task',
        page: 1,
        per_page: 20
      });
      const logs = response.items || [];
      
      taskLogs.value = logs.map((log: Log) => {
        let formattedTime = log.time?.toString() || log.timestamp?.toString() || '';
        try {
          const date = new Date(formattedTime);
          if (!isNaN(date.getTime())) {
            formattedTime = date.toLocaleString();
          }
        } catch (e) {
          console.error('Failed to format log time:', e);
        }
        
        return { ...log, time: formattedTime } as UILog;
      });
      
      filterTaskLogs();
    } catch (error) {
      console.error('Failed to fetch task logs:', error);
    }
  };

  const refreshTaskLogs = async () => {
    await fetchTaskLogs();
  };

  const filterTaskLogs = () => {
    let result = [...taskLogs.value];
    
    if (taskLogSearchTerm.value) {
      const term = taskLogSearchTerm.value.toLowerCase();
      result = result.filter(log => 
        log.content.toLowerCase().includes(term) ||
        (log.module?.toLowerCase().includes(term) ?? false) ||
        (log.source?.toLowerCase().includes(term) ?? false)
      );
    }
    
    if (taskLogLevelFilter.value !== 'all') {
      result = result.filter(log => log.level === taskLogLevelFilter.value);
    }
    
    if (taskLogFilter.value === 'current' && filteredTasks.value.length > 0) {
      const taskIds = new Set(filteredTasks.value.map(task => task.id));
      result = result.filter(log => taskIds.has((log as any).taskId));
    }
    
    filteredTaskLogs.value = result;
  };

  watch([taskLogSearchTerm, taskLogLevelFilter, taskLogFilter, filteredTasks], () => {
    filterTaskLogs();
  });

  const getStatusText = (status: string) => reportService.getStatusText(status);
  const getStatusIcon = (status: string) => {
    const icons: Record<string, string> = { 
      'pending': 'clock', 
      'queued': 'hourglass', 
      'running': 'play-circle', 
      'completed': 'check-circle', 
      'failed': 'exclamation-circle', 
      'paused': 'pause-circle', 
      'stopped': 'stop-circle', 
      'skipped': 'minus-circle' 
    };
    return icons[status] || 'question-circle';
  };
  const getStepStatusText = (status: string) => {
    const texts: Record<string, string> = { 
      'pending': '等待中', 
      'queued': '排队中', 
      'running': '执行中', 
      'completed': '已完成', 
      'failed': '失败', 
      'paused': '已暂停', 
      'stopped': '已停止', 
      'skipped': '已跳过' 
    };
    return texts[status] || status;
  };
  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString();
  };

  const { 
    deviceApiColumns, 
    caseExecutionColumns, 
    extractDevicesFromTasks, 
    updateComparisonData, 
    toggleDeviceSelection,
    deviceApiComparisonData,
    caseExecutionData,
    updateComparisonReportConclusion
  } = reportService;

  const showComparisonReport = computed(() => reportService.comparisonTasks.value.length > 0);
  const comparisonTasks = computed(() => reportService.comparisonTasks.value);
  const comparisonReport = computed(() => reportService.comparisonReport.value);

  return {
    tasks,
    filteredTasks,
    selectedTasks,
    currentPage,
    pageSize,
    sortConfig,
    selectedTags,
    searchTerm,
    filters,
    customDateRange,
    tagCurrentPage,
    tagPageSize,
    showComparisonReport,
    comparisonTasks,
    comparisonReport,
    isEditingConclusion,
    allTags,
    totalTagPages,
    currentTags,
    totalTasks,
    pendingTasks,
    queuedTasks,
    inProgressTasks,
    completedTasks,
    failedTasks,
    deletedTasks,
    totalPages,
    paginatedTasks,
    isAllSelected,
    getStatusText,
    getStatusIcon,
    getStepStatusText,
    formatDate,
    applyFilters,
    handleSearch,
    sortTasks,
    toggleSort,
    clearCustomDateRange,
    toggleTag,
    toggleTaskSelection,
    toggleSelectAll,
    cancelSelect,
    createNewTask,
    handleCreateTask,
    handleTaskAction,
    viewTaskDetails,
    viewTaskReport,
    editTask,
    updateTaskName,
    retryTask,
    reevaluateTask,
    deleteTask,
    pauseTask,
    resumeTask,
    stopTask,
    isControlling,
    batchDelete,
    batchCompare,
    batchMerge,
    batchRestore,
    closeComparisonReport,
    saveComparisonReport,
    publishComparisonReport,
    startEditingConclusion,
    saveConclusion,
    toggleEditConclusion,
    cancelEditConclusion,
    toggleEditReport,
    cancelEditReport,
    createTaskTypeChart: createTaskTypeChartFn,
    createTaskTrendChart: createTaskTrendChartFn,
    createTaskStatusChart: createTaskStatusChartFn,
    updateCharts,
    updateComparisonReportConclusion,
    initTasks,
    resetAllStates,
    changeTimeGranularity,
    isActive,
    deviceApiColumns,
    caseExecutionColumns,
    extractDevicesFromTasks,
    updateComparisonData,
    toggleDeviceSelection,
    fetchTasks,
    reportService,
    isEditingReport,
    reportConclusion,
    reportServiceData,
    reportName,
    reportDevices,
    deviceApiComparisonData,
    caseExecutionData,
    isTaskTypeModalVisible,
    currentTask,
    taskLogs,
    filteredTaskLogs,
    taskLogSearchTerm,
    taskLogLevelFilter,
    taskLogFilter,
    fetchTaskLogs,
    refreshTaskLogs,
    filterTaskLogs,
    taskTypeChartRef,
    taskTrendChartRef,
    taskStatusChartRef,
    algorithmOptions,
    loadAlgorithmOptions
  };
}
