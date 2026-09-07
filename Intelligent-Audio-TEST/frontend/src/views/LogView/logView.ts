import { ref, computed, watch, onMounted, onBeforeUnmount, onUnmounted, nextTick, type Ref } from 'vue';
import { useRoute } from 'vue-router';
import { logsPort } from '../../composables/task/logsPort';
import { algorithmPort } from '../../composables/algorithm/algorithmPort';
import { useModalControl } from '../../composables/modal/useModal';
import type {
  Log,
  LogFilters,
  AdvancedLogFilters,
  LogStats,
  LogQuery as LogQueryParams,
  LogLevelOption,
  LogRow
} from '../../domain';
import { MODAL_TYPES } from '../../composables/modal/constants';
import { usePagination } from '../../composables/usePagination';
import { formatLogTime } from '../../utils/timeFormat';
// 引入视图模式枚举，消除魔法字符串
import { LogLevel, ViewMode, TestType } from '@/domain/enums';

// 日志级别选项/默认全选值由 domain 枚举 LogLevel 派生（value 小写用于筛选，label 首字母大写）
const LOG_LEVEL_OPTIONS: LogLevelOption[] = Object.values(LogLevel).map(level => ({
  value: level.toLowerCase(),
  label: level.charAt(0) + level.slice(1).toLowerCase()
}));
// 默认选中的日志级别（小写 value）
const DEFAULT_SELECTED_LEVELS: string[] = Object.values(LogLevel).map(level => level.toLowerCase());
// 日志级别（小写）→ 后端查询参数（大写原值）映射，由领域枚举派生，消除悬空引用
const LOG_LEVEL_MAP: Record<string, string> = Object.fromEntries(
  Object.values(LogLevel).map(level => [level.toLowerCase(), level]),
);
// 实时日志轮询间隔（毫秒）
const REALTIME_POLL_INTERVAL_MS = 5000;
// 实时监控连接状态文案
const CONNECTION_STATUS = { CONNECTED: '已连接', ERROR: '连接异常' } as const;

// 日志行视图模型统一收敛至 domain/model/ui.ts 的 LogRow（与 useTaskLogs 共用）
type UILog = LogRow;

interface LogViewRefs {
  startDateTimeRef?: Ref<HTMLInputElement | null>;
  endDateTimeRef?: Ref<HTMLInputElement | null>;
  startContainerRef?: Ref<HTMLElement | null>;
  endContainerRef?: Ref<HTMLElement | null>;
}

export function useLogView(refs?: LogViewRefs) {
  const realTimeLogEnabled = ref(false);
  const showMonitorIndicator = ref(false);
  const logRate = ref(0);
  const logDelay = ref(0);
  const connectionStatus = ref<typeof CONNECTION_STATUS[keyof typeof CONNECTION_STATUS]>(CONNECTION_STATUS.CONNECTED);
  const autoScrollEnabled = ref(true);
  const realTimeLogInterval = ref<number | null>(null);

  const filters = ref<LogFilters>({
    startDateTime: '',
    endDateTime: '',
    logCategory: ViewMode.ALL,
    logModule: ViewMode.ALL,
    markFilter: ViewMode.ALL,
    algorithmType: ViewMode.ALL
  });

  const advancedFilters = ref<AdvancedLogFilters>({
    deviceId: '',
    taskId: '',
    userId: '',
    threadId: '',
    contentInclude: '',
    contentExclude: ''
  });

  const searchTerm = ref('');

  const logLevels = ref<LogLevelOption[]>(LOG_LEVEL_OPTIONS as unknown as LogLevelOption[]);
  const selectedLevels = ref<string[]>(['debug', 'info', 'warning', 'error']);

  const showAdvancedFilter = ref(false);
  const showLevelDropdown = ref(false);
  const markColor = ref('yellow');
  const isLoading = ref(false);

  const modalManager = useModalControl();

  const logs = ref<UILog[]>([]);
  const totalLogs = ref(0);
  const logStats = ref<LogStats>({
    total: 0,
    error: 0,
    warning: 0,
    info: 0
  });

  const currentPage = ref(1);
  const pageSize = ref(10);

  // 日志为服务端分页：totalLogs 由后端返回，直接驱动 totalPages 计算
  const { totalPages } = usePagination(undefined, pageSize, { currentPage, totalCount: totalLogs });
  const algorithmOptions = ref<{ value: string; label: string }[]>([]);

  // 日志配置默认值
  const LOGCategoryOptions = [{ value: 'all', label: '所有分类' }, { value: 'system', label: '系统日志' }, { value: 'test', label: '测试日志' }, { value: 'error', label: '错误日志' }];
  const LOGModuleOptions = [{ value: 'all', label: '所有模块' }, { value: TestType.API, label: 'API模块' }, { value: TestType.E2E, label: 'E2E测试' }, { value: 'device', label: '设备管理' }];
  const LOGMarkOptions = [{ value: 'all', label: '所有标记' }, { value: 'yellow', label: '黄色标记' }, { value: 'red', label: '红色标记' }, { value: 'green', label: '绿色标记' }, { value: 'blue', label: '蓝色标记' }];

  const getAlgorithmLabel = (algorithmType: string): string => {
    const option = algorithmOptions.value.find(opt => opt.value === algorithmType);
    return option ? option.label : algorithmType;
  };

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
        { value: 'asr', label: 'ASR' },
        { value: 'speaker_recognition', label: '说话人识别' },
        { value: 'tts', label: 'TTS' }
      ];
    }
  }

  const buildQueryParams = (): LogQueryParams => {
    const params : LogQueryParams = {keyword: searchTerm.value, startTime: filters.value.startDateTime, endTime: filters.value.endDateTime, ...advancedFilters.value};
    
    if (filters.value.logCategory !== ViewMode.ALL) params.category = filters.value.logCategory;
    if (filters.value.logModule !== ViewMode.ALL) params.module = filters.value.logModule;
    if (filters.value.markFilter !== ViewMode.ALL) params.mark = filters.value.markFilter;
    if (filters.value.algorithmType !== ViewMode.ALL) params.algorithmType = filters.value.algorithmType;
    
    if (selectedLevels.value.length < logLevels.value.length && selectedLevels.value.length > 0) {
      const backendLevels = selectedLevels.value.map(level => LOG_LEVEL_MAP[level] || level);
      params.level = backendLevels.join(',');
    }

    return params;
  };

  const fetchStats = async () => {
    try {
      const params = buildQueryParams();
      const response = await logsPort.getStats(params);
      
      const result : LogStats = {total: response.total || 0, error: 0, warning: 0, info: 0};
      
      Object.entries(response).forEach(([key, value]) => {
        const lowerKey = key.toLowerCase();
        if (lowerKey === 'total') return;
        
        const count = Number(value);
        if (lowerKey === 'error' || lowerKey === 'critical') {
          result.error += count;
        } else if (lowerKey === 'warn' || lowerKey === 'warning') {
          result.warning += count;
        } else if (lowerKey === 'info') {
          result.info += count;
        }
      });
      
      logStats.value = result;
    } catch (error) {
      console.error('Failed to fetch log stats:', error);
    }
  };

  const fetchLogs = async () => {
    isLoading.value = true;
    try {
      const params = buildQueryParams();
      params.page = currentPage.value;
      params.perPage = pageSize.value;

      const response = await logsPort.getAll(params);
      
      logs.value = (response.items || []).map((log: Log) => {
        let formattedTime = log.time?.toString() || log.timestamp?.toString() || '';
        try {
          const date = new Date(formattedTime);
          if (!isNaN(date.getTime())) {
            formattedTime = date.toLocaleTimeString();
          }
        } catch (e) {
          console.error('Failed to format log time:', e);
        }
        
        return {...log, time: formattedTime, selected: false, isExpanded: false} as UILog;
      });
      
      totalLogs.value = response?.total || 0;
      fetchStats();
    } catch (error) {
      console.error('Failed to fetch logs:', error);
    } finally {
      isLoading.value = false;
    }
  };

  async function initLogView() {
    await Promise.all([
      fetchLogs(),
      loadAlgorithmOptions()
    ]);
  }

  function cleanupLogView() {
    stopRealTimeLog();
  }

  onUnmounted(() => {
    cleanupLogView();
  });

  watch([currentPage, pageSize], () => {
    fetchLogs();
  });

  const realTimeLogStatus = computed(() => realTimeLogEnabled.value ? '停止实时日志' : '开启实时日志');
  const paginatedLogs = computed(() => logs.value);
  const advancedFilterText = computed(() => showAdvancedFilter.value ? '收起高级过滤' : '高级过滤');
  const autoScrollText = computed(() => autoScrollEnabled.value ? '暂停自动滚动' : '自动滚动');
  const selectedLevelObjects = computed(() => logLevels.value.filter(level => selectedLevels.value.includes(level.value)));

  const handlePrevPage = () => {
    if (currentPage.value > 1) currentPage.value--;
  };

  const handleNextPage = () => {
    if (currentPage.value < totalPages.value) currentPage.value++;
  };

  const handleGoToPage = (page: number) => {
    if (page >= 1 && page <= totalPages.value) currentPage.value = page;
  };

  const handlePageSizeChange = (newPageSize: number) => {
    pageSize.value = newPageSize;
    currentPage.value = 1;
  };

  const removeLevel = (level: string) => {
    const index = selectedLevels.value.indexOf(level);
    if (index > -1) {
      selectedLevels.value.splice(index, 1);
      filterLogs();
    }
  };

  const toggleLevel = (level: string) => {
    const index = selectedLevels.value.indexOf(level);
    if (index > -1) {
      selectedLevels.value.splice(index, 1);
    } else {
      selectedLevels.value.push(level);
    }
    filterLogs();
  };

  const filterLogs = () => {
    currentPage.value = 1;
    fetchLogs();
  };

  const searchLogs = () => {
    currentPage.value = 1;
    fetchLogs();
  };

  const clearSearch = () => {
    searchTerm.value = '';
    filterLogs();
  };

  const toggleAdvancedFilter = () => {
    showAdvancedFilter.value = !showAdvancedFilter.value;
  };

  const clearAllFilters = () => {
    Object.assign(filters.value, {
      startDateTime: '',
      endDateTime: '',
      logCategory: ViewMode.ALL,
      logModule: ViewMode.ALL,
      markFilter: ViewMode.ALL,
      algorithmType: ViewMode.ALL
    });
    
    Object.assign(advancedFilters.value, {
      deviceId: '',
      taskId: '',
      userId: '',
      threadId: '',
      contentInclude: '',
      contentExclude: ''
    });
    
    selectedLevels.value = [...DEFAULT_SELECTED_LEVELS];
    searchTerm.value = '';
    filterLogs();
  };

  const toggleLevelDropdown = () => {
    showLevelDropdown.value = !showLevelDropdown.value;
  };

  const selectAllLevels = () => {
    selectedLevels.value = logLevels.value.map(level => level.value);
    filterLogs();
  };

  const clearAllLevels = () => {
    selectedLevels.value = [];
    filterLogs();
  };

  const refreshLogs = async () => {
    isLoading.value = true;
    try {
      const lastId = logs.value.length > 0 ? logs.value[0].id : 0;
      await logsPort.refresh(lastId);
      await fetchLogs();
    } catch (error) {
      console.error('Failed to refresh logs:', error);
    } finally {
      isLoading.value = false;
    }
  };

  const clearLogs = () => {
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '确认清除',
      message: '确定要清除所有日志吗？此操作不可撤销。',
      confirmText: '确定清除',
      cancelText: '取消',
      onConfirm: async () => {
        try {
          isLoading.value = true;
          await logsPort.clear();
          currentPage.value = 1;
          await fetchLogs();
        } catch (error) {
          console.error('Failed to clear logs:', error);
        } finally {
          isLoading.value = false;
        }
      }
    });
  };

  const exportLogs = () => {
    modalManager.open(MODAL_TYPES.IMPORT_EXPORT, {
      mode: 'export',
      title: '导出日志',
      formatOptions: [
        { value: 'json', label: 'JSON文件 (.json)' },
        { value: 'excel', label: 'Excel文件 (.xlsx)' }
      ],
      rangeOptions: [
        { value: 'current', label: '当前页面' },
        { value: 'all', label: '所有日志' },
        { value: 'selected', label: '选中的日志' }
      ],
      fields: [
        { key: 'time', label: '时间', default: true },
        { key: 'level', label: '级别', default: true },
        { key: 'module', label: '模块', default: true },
        { key: 'source', label: '来源', default: true },
        { key: 'content', label: '内容', default: true },
        { key: 'context', label: '上下文', default: false }
      ],
      onConfirm: async (options: {range: string; format: string}) => {
        try {
          isLoading.value = true;
          const params = buildQueryParams();
          let exportParams = {...params};
          
          if (options.range === 'current') {
            exportParams.page = currentPage.value;
            exportParams.perPage = pageSize.value;
          } else if (options.range === 'selected') {
            (exportParams as any).logIds = logs.value.filter(l => l.selected).map(l => l.id).join(',');
          }
          
          await logsPort.export({ ...exportParams, format: options.format } as any);
        } catch (error) {
          console.error('Failed to export logs:', error);
        } finally {
          isLoading.value = false;
        }
      }
    });
  };

  const toggleRealTimeLog = () => {
    realTimeLogEnabled.value = !realTimeLogEnabled.value;
    showMonitorIndicator.value = realTimeLogEnabled.value;
    
    if (realTimeLogEnabled.value) {
      startRealTimeLog();
    } else {
      stopRealTimeLog();
    }
  };

  const startRealTimeLog = () => {
    if (realTimeLogInterval.value) return;

    realTimeLogInterval.value = window.setInterval(async () => {
      if (autoScrollEnabled.value && currentPage.value === 1) {
        const lastId = logs.value.length > 0 ? Math.max(...logs.value.map(l => l.id)) : 0;
        const pollStartTime = performance.now();
        try {
          const response = await logsPort.refresh(lastId);
          const newCount = response.newCount;
          // 基于真实增量计算日志速率（条/秒）与响应延迟（毫秒）
          logRate.value = Math.round((newCount * 1000 / REALTIME_POLL_INTERVAL_MS) * 10) / 10;
          logDelay.value = Math.round(performance.now() - pollStartTime);
          connectionStatus.value = CONNECTION_STATUS.CONNECTED;
          if (newCount > 0) {
            fetchLogs();
          }
        } catch (e) {
          connectionStatus.value = CONNECTION_STATUS.ERROR;
          console.error('Real-time refresh failed:', e);
        }
      }
    }, REALTIME_POLL_INTERVAL_MS);
  };

  const stopRealTimeLog = () => {
    if (realTimeLogInterval.value) {
      clearInterval(realTimeLogInterval.value);
      realTimeLogInterval.value = null;
    }
  };

  const toggleAutoScroll = () => {
    autoScrollEnabled.value = !autoScrollEnabled.value;
  };

  const toggleLogDetails = (logId: number | string) => {
    const log = logs.value.find(l => l.id === logId);
    if (log) log.isExpanded = !log.isExpanded;
  };

  const selectAllLogs = (event: Event) => {
    const target = event.target as HTMLInputElement;
    const isChecked = target.checked;
    logs.value.forEach(log => { log.selected = isChecked; });
  };



  const markLog = async (logId: number | string) => {
    const log = logs.value.find(l => l.id === logId);
    if (log) {
      const newMark = log.mark === markColor.value ? '' : markColor.value;
      try {
        await logsPort.mark([logId], newMark);
        log.mark = newMark;
      } catch (error) {
        console.error('Failed to mark log:', error);
      }
    }
  };

  const batchMarkLogs = () => {
    const selectedLogIds = logs.value.filter(log => log.selected).map(log => log.id);
    if (selectedLogIds.length === 0) return;
    
    modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '确认标记',
      message: `确定要标记选中的 ${selectedLogIds.length} 条日志吗？`,
      confirmText: '确定标记',
      cancelText: '取消',
      onConfirm: async () => {
        try {
          await logsPort.mark(selectedLogIds, markColor.value);
          logs.value.forEach(log => {
            if (log.selected) log.mark = markColor.value;
          });
        } catch (error) {
          console.error('Failed to batch mark logs:', error);
        }
      }
    });
  };

  const copyLog = async (logId: number | string) => {
    const log = logs.value.find(l => l.id === logId);
    if (log) {
      try {
        const text = `[${log.time}] [${log.level.toUpperCase()}] [${log.module}] ${log.content}`;
        await navigator.clipboard.writeText(text);
      } catch (err) {
        console.error('Failed to copy log:', err);
      }
    }
  };

  const openMonitorConfig = () => {
    console.log('Open monitor config');
  };

  const sortLogs = (field: string) => {
    logs.value.sort((a, b) => {
      const valA = (a as any)[field];
      const valB = (b as any)[field];
      if (valA < valB) return 1;
      if (valA > valB) return -1;
      return 0;
    });
  };

  // 日期时间选择器逻辑
  const openDateTimePicker = (inputRef: Ref<HTMLInputElement | null>) => {
    if (inputRef && inputRef.value) {
      // 直接调用输入框的showPicker方法（现代浏览器支持）
      if (typeof (inputRef.value as any).showPicker === 'function') {
        try {
          (inputRef.value as any).showPicker();
        } catch (error) {
          // 如果showPicker不可用，回退到模拟点击
          inputRef.value.focus();
          const event = new MouseEvent('click', {
            bubbles: true,
            cancelable: true,
            view: window
          });
          inputRef.value.dispatchEvent(event);
        }
      } else {
        // 回退方案：模拟点击
        inputRef.value.focus();
        const event = new MouseEvent('click', {
          bubbles: true,
          cancelable: true,
          view: window
        });
        inputRef.value.dispatchEvent(event);
      }
    }
  };

  const handleStartDateClick = () => {
    if (refs?.startDateTimeRef) openDateTimePicker(refs.startDateTimeRef);
  };

  const handleEndDateClick = () => {
    if (refs?.endDateTimeRef) openDateTimePicker(refs.endDateTimeRef);
  };

  // 调整筛选卡片高度的函数
  function adjustFilterCardHeight() {
    const filterBar = document.querySelector('.log-view > .filter-section > .filter-bar') as HTMLElement;
    if (filterBar) {
      // 重置高度以触发重新计算
      filterBar.style.height = 'auto';
      // 强制重排
      filterBar.offsetHeight;
      // 再次设置为auto确保内容能正确撑开
      filterBar.style.height = 'auto';
    }
  }

  // 添加事件监听器
  onMounted(() => {
    // 为开始时间容器添加点击事件
    if (refs?.startContainerRef?.value) {
      refs.startContainerRef.value.addEventListener('click', handleStartDateClick);
    }
    
    // 为结束时间容器添加点击事件
    if (refs?.endContainerRef?.value) {
      refs.endContainerRef.value.addEventListener('click', handleEndDateClick);
    }
  });

  // 组件挂载时初始化日志视图
  onMounted(async () => {
    await initLogView();
    // 组件挂载后强制重新计算高度
    nextTick(() => {
      adjustFilterCardHeight();
    });
  });

  // 清理事件监听器
  onBeforeUnmount(() => {
    if (refs?.startContainerRef?.value) {
      refs.startContainerRef.value.removeEventListener('click', handleStartDateClick);
    }
    
    // 为结束时间容器添加点击事件
    if (refs?.endContainerRef?.value) {
      refs.endContainerRef.value.removeEventListener('click', handleEndDateClick);
    }
    cleanupLogView();
  });

  // 监听路由变化，确保组件可见时重新计算高度
  const route = useRoute();
  watch(
    () => route.path,
    () => {
      if (route.path === '/LogView') {
        nextTick(() => {
          adjustFilterCardHeight();
        });
      }
    }
  );

  return {
    realTimeLogEnabled,
    showMonitorIndicator,
    logRate,
    logDelay,
    connectionStatus,
    autoScrollEnabled,
    filters,
    advancedFilters,
    searchTerm,
    logLevels,
    selectedLevels,
    showAdvancedFilter,
    showLevelDropdown,
    markColor,
    logs,
    totalLogs,
    isLoading,
    logStats,
    currentPage,
    pageSize,
    realTimeLogStatus,
    paginatedLogs,
    advancedFilterText,
    autoScrollText,
    selectedLevelObjects,
    LOGCategoryOptions,
    LOGModuleOptions,
    LOGMarkOptions,
    getAlgorithmLabel,
    initLogView,
    cleanupLogView,
    fetchLogs,
    fetchStats,
    handlePrevPage,
    handleNextPage,
    handleGoToPage,
    handlePageSizeChange,
    removeLevel,
    toggleLevel,
    filterLogs,
    searchLogs,
    clearSearch,
    toggleAdvancedFilter,
    clearAllFilters,
    toggleLevelDropdown,
    selectAllLevels,
    clearAllLevels,
    refreshLogs,
    clearLogs,
    exportLogs,
    toggleRealTimeLog,
    toggleAutoScroll,
    toggleLogDetails,
    selectAllLogs,
    markLog,
    batchMarkLogs,
    copyLog,
    openMonitorConfig,
    sortLogs,
    algorithmOptions,
    loadAlgorithmOptions
  };
}
