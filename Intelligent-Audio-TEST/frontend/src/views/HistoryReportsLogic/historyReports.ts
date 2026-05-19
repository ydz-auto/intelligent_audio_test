import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useRouter } from 'vue-router';
import { reportsApi } from '../../utils/api';
import { useAlgorithmLabels } from '../../composables/useAlgorithmLabels';
import { getReportTypeLabel } from '../../shared/constants/reportConstants';
import type { Report, ReportListParams } from '../../shared/types/index';

interface AlgorithmOption {
  value: string;
  name: string;
  group_id?: number;
  group_name?: string;
}

type ReportTypeFilter = 'all' | 'comparison' | 'secondaryComparison' | 'task';
type ReportStatusFilter = 'all' | 'draft' | 'published';
type TimeRangeFilter = 'all' | 'today' | 'yesterday' | 'week' | 'month' | 'custom';

interface HistoryReportsFilters {
  search: string;
  reportType: ReportTypeFilter;
  reportStatus: ReportStatusFilter;
  timeRange: TimeRangeFilter;
  startDate: string;
  endDate: string;
  algorithmType: string;
}

interface HistoryReportsSort {
  sortBy: 'createdAt' | 'name' | 'type' | 'status' | 'updatedAt';
  order: 'asc' | 'desc';
}

interface ToastMessage {
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
}

const toast = ref<ToastMessage | null>(null);

function showToast(type: ToastMessage['type'], message: string): void {
  toast.value = { type, message };
  setTimeout(() => {
    toast.value = null;
  }, 3000);
}

export function useHistoryReports() {
  const router = useRouter();
  const allReports = ref<Report[]>([]);
  const totalItems = ref(0);
  const currentPage = ref(1);
  const pageSize = ref(10);
  const loading = ref(false);
  const selectedReports = ref<Set<string | number>>(new Set());

  const { algorithmOptions, loadAlgorithms, getAlgorithmLabel } = useAlgorithmLabels();

  const filters = ref<HistoryReportsFilters>({
    search: '',
    reportType: 'all',
    reportStatus: 'all',
    timeRange: 'all',
    startDate: '',
    endDate: '',
    algorithmType: 'all'
  });

  const sort = ref<HistoryReportsSort>({
    sortBy: 'createdAt',
    order: 'desc'
  });

  const loadReports = async () => {
    loading.value = true;
    try {
      const params : ReportListParams = {
        page: currentPage.value, 
        perPage: pageSize.value, 
        sortBy: sort.value.sortBy as string, 
        order: sort.value.order
      };
      
      if (filters.value.search) params.keyword = filters.value.search;
      if (filters.value.reportType && filters.value.reportType !== 'all') params.type = filters.value.reportType;
      if (filters.value.reportStatus && filters.value.reportStatus !== 'all') params.status = filters.value.reportStatus;
      if (filters.value.startDate) params.startTime = filters.value.startDate;
      if (filters.value.endDate) params.endTime = filters.value.endDate;
      if (filters.value.algorithmType && filters.value.algorithmType !== 'all') params.algorithmType = filters.value.algorithmType;
      
      const data = await reportsApi.getAll(params);
      allReports.value = data.items || [];
      totalItems.value = data.total || 0;
    } catch (error) {
      console.error('加载报告失败:', error);
      showToast('error', '加载报告失败，请稍后重试');
    } finally {
      loading.value = false;
    }
  };

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString();
  };

  const calculateDateRange = () => {
    const now = new Date();
    let startDate = '';
    let endDate = '';

    switch (filters.value.timeRange) {
      case 'today':
        startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString().split('T')[0];
        endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).toISOString().split('T')[0];
        break;
      case 'yesterday':
        startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1).toISOString().split('T')[0];
        endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString().split('T')[0];
        break;
      case 'week':
        startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 7).toISOString().split('T')[0];
        endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).toISOString().split('T')[0];
        break;
      case 'month':
        startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 30).toISOString().split('T')[0];
        endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).toISOString().split('T')[0];
        break;
      case 'custom':
        return;
      default:
        filters.value.startDate = '';
        filters.value.endDate = '';
        return;
    }

    filters.value.startDate = startDate;
    filters.value.endDate = endDate;
  };

  const getReportTypeLabelLocal = (type: string) => {
    return getReportTypeLabel(type);
  };

  const getAlgorithmTypeLabel = (algorithmType: string | undefined) => {
    if (!algorithmType) return null;
    return getAlgorithmLabel(algorithmType);
  };

  const loadAlgorithmOptions = async () => {
    await loadAlgorithms();
  };

  const getReportSummary = (report: Report) => {
    if (!report.summary) return '暂无摘要';
    
    const summary = report.summary;
    const totalCases = summary.totalCases || summary.total_cases || 0;
    const completedCases = summary.completedCases || summary.completed_cases || 0;
    const failedCases = summary.failedCases || summary.failed_cases || 0;
    const successRate = summary.overallSuccessRate || summary.passRate || summary.overall_success_rate || 0;
    
    if (report.type === 'task') {
      return `共 ${totalCases} 个测试用例，通过 ${completedCases} 个，失败 ${failedCases} 个，通过率 ${successRate}%`;
    } else if (report.type === 'comparison') {
      return `共对比 ${summary.taskCount || 0} 个任务，包含 ${totalCases} 个测试用例`;
    } else {
      return `共 ${totalCases} 个测试用例，通过 ${completedCases} 个，失败 ${failedCases} 个，通过率 ${successRate}%`;
    }
  };

  const handleFilterChange = () => {
    calculateDateRange();
    currentPage.value = 1;
    loadReports();
  };

  const handleSortChange = (sortBy: string) => {
    if (sort.value.sortBy === sortBy) {
      sort.value.order = sort.value.order === 'asc' ? 'desc' : 'asc';
    } else {
      sort.value.sortBy = sortBy as HistoryReportsSort['sortBy'];
      sort.value.order = 'desc';
    }
    currentPage.value = 1;
    loadReports();
  };

  const clearDateRange = () => {
    filters.value.startDate = '';
    filters.value.endDate = '';
    handleFilterChange();
  };

  const totalPages = computed(() => Math.ceil(totalItems.value / pageSize.value));

  const handlePrevPage = () => {
    if (currentPage.value > 1) {
      currentPage.value--;
      loadReports();
    }
  };

  const handleNextPage = () => {
    if (currentPage.value < totalPages.value) {
      currentPage.value++;
      loadReports();
    }
  };

  const handleGoToPage = (page: number) => {
    currentPage.value = page;
    loadReports();
  };

  const handlePageSizeChange = (newSize: number) => {
    pageSize.value = newSize;
    currentPage.value = 1;
    loadReports();
  };

  const isAllSelected = computed(() => {
    return allReports.value.length > 0 && selectedReports.value.size === allReports.value.length;
  });

  const publishedReports = computed(() => {
    return allReports.value.filter(report => report.status === 'published');
  });

  const draftReports = computed(() => {
    return allReports.value.filter(report => report.status === 'draft');
  });

  const toggleSelectAll = () => {
    if (isAllSelected.value) {
      selectedReports.value.clear();
    } else {
      allReports.value.forEach(report => selectedReports.value.add(report.id));
    }
  };

  const toggleReportSelection = (reportId: string | number, event?: MouseEvent) => {
    if (event?.target instanceof HTMLElement && event.target.closest('.card-actions')) return;
    if (selectedReports.value.has(reportId)) {
      selectedReports.value.delete(reportId);
    } else {
      selectedReports.value.add(reportId);
    }
  };

  const handleBatchDelete = async () => {
    if (selectedReports.value.size === 0) return;
    if (confirm(`确定要删除选中的 ${selectedReports.value.size} 个报告吗？`)) {
      try {
        const ids = Array.from(selectedReports.value);
        await reportsApi.batchDelete(ids);
        selectedReports.value.clear();
        showToast('success', `成功删除 ${ids.length} 个报告`);
        loadReports();
      } catch (error: any) {
        showToast('error', '批量删除失败: ' + (error.message || '未知错误'));
      }
    }
  };

  const handleBatchCancel = () => {
    selectedReports.value.clear();
  };

  const handleBatchCompare = async () => {
    if (selectedReports.value.size < 2) {
      showToast('warning', '请至少选择2个报告进行对比');
      return;
    }
    try {
      const ids = Array.from(selectedReports.value);
      const result = await reportsApi.secondaryCompare(ids);
      showToast('success', '对比报告生成成功');
      router.push({ name: 'reportView', params: { id: result.id } });
    } catch (error: any) {
      showToast('error', '生成对比报告失败: ' + (error.message || '未知错误'));
    }
  };

  const viewReport = (reportId: string | number, type?: string) => {
    router.push({ name: 'reportView', params: { id: reportId } });
  };

  const editReport = (reportId: string | number) => {
    router.push({ name: 'reportView', params: { id: reportId } });
  };

  const deleteReport = async (reportId: string | number) => {
    if (confirm('确定要删除这个报告吗？')) {
      try {
        await reportsApi.delete(reportId);
        selectedReports.value.delete(reportId);
        showToast('success', '报告删除成功');
        loadReports();
      } catch (error: any) {
        showToast('error', '删除失败: ' + (error.message || '未知错误'));
      }
    }
  };

  const publishReport = async (reportId: string | number) => {
    if (confirm('确定要发布这个报告吗？')) {
      try {
        await reportsApi.publish(reportId);
        showToast('success', '报告发布成功');
        loadReports();
      } catch (error: any) {
        showToast('error', '发布失败: ' + (error.message || '未知错误'));
      }
    }
  };

  onMounted(() => {
    loadReports();
    loadAlgorithmOptions();
  });

  onBeforeUnmount(() => {
    selectedReports.value.clear();
  });

  return {
    allReports,
    totalItems,
    currentPage,
    pageSize,
    loading,
    selectedReports,
    filters,
    sort,
    algorithmOptions,
    toast,
    formatDate,
    getReportTypeLabel: getReportTypeLabelLocal,
    getAlgorithmTypeLabel,
    getReportSummary,
    handleFilterChange,
    handleSortChange,
    clearDateRange,
    handlePrevPage,
    handleNextPage,
    handleGoToPage,
    handlePageSizeChange,
    totalPages,
    isAllSelected,
    publishedReports,
    draftReports,
    toggleSelectAll,
    toggleReportSelection,
    handleBatchDelete,
    handleBatchCancel,
    handleBatchCompare,
    viewReport,
    editReport,
    deleteReport,
    publishReport
  };
}
