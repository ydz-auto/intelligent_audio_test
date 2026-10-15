import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useRouter } from 'vue-router';
import { reportsPort } from '@/composables/report/reportsPort';
import { useModalControl } from '@/composables/modal/useModal';
import { MODAL_TYPES } from '@/composables/modal/constants';
import type { Report, ReportListQuery } from '../../domain';
import { getReportTypeLabel } from '../../domain/constants/reportLabels';
import { formatDate } from '@/utils/utils';
import { useFavorites } from '../../composables/favorite/useFavorites';

/**
 * TestReports（测试历史报告数据）composable —— INT-287 占位页补齐。
 *
 * 对齐 HistoryReports 口径的最小化实现：分页列表 + 三态（加载/空/错误）+
 * 行操作（查看/收藏/删除）。不引入 Tab/筛选/排序/回收站（页面定位为
 * 「测试产生的报告数据」视图，复杂管理入口由 /history-reports 承担）。
 */
export function useTestReports() {
  const router = useRouter();
  const modalManager = useModalControl();
  const favoritesModule = useFavorites('report');

  const reports = ref<Report[]>([]);
  const total = ref<number>(0);
  const currentPage = ref<number>(1);
  const pageSize = ref<number>(10);
  const loading = ref<boolean>(false);
  /** 拉取失败时的用户可见错误文案（三态之「错误态」） */
  const error = ref<string>('');
  /** 轻量行内反馈（收藏/删除结果），样式对齐 HistoryReports toast */
  const toast = ref<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  function showToast(type: 'success' | 'error' | 'info', message: string): void {
    if (toastTimer) clearTimeout(toastTimer);
    toast.value = { type, message };
    toastTimer = setTimeout(() => {
      toast.value = null;
    }, 3000);
  }

  const getReportTypeLabelLocal = (type: string) => getReportTypeLabel(type);

  const loadReports = async () => {
    loading.value = true;
    error.value = '';
    try {
      const params: ReportListQuery = {
        page: currentPage.value,
        perPage: pageSize.value,
        sortBy: 'createdAt',
        order: 'desc',
      };
      const response = await reportsPort.getAll(params);
      reports.value = response.items || [];
      total.value = response.total || 0;
      if (currentPage.value > 1 && reports.value.length === 0) {
        // 当前页越界（数据被删光后停留在旧页码）：回退首页重取
        currentPage.value = 1;
        loading.value = false;
        return loadReports();
      }
    } catch (err) {
      console.error('加载报告列表失败:', err);
      reports.value = [];
      total.value = 0;
      error.value = '加载报告失败，请稍后重试';
    } finally {
      loading.value = false;
    }
  };

  const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));

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

  // ===== 行操作 =====

  /** 查看报告 → /report/:id（对齐 HistoryReports viewReport） */
  const viewReport = (reportId: string | number) => {
    router.push({ name: 'reportView', params: { id: reportId } });
  };

  /** 收藏 / 取消收藏（星标切换，对齐 HistoryReports handleToggleFavorite） */
  const handleToggleFavorite = async (report: Report) => {
    try {
      await favoritesModule.toggleFavorite(report.id);
      showToast('success', favoritesModule.isFavorite(report.id) ? '已收藏' : '已取消收藏');
    } catch (err) {
      console.error('收藏操作失败:', err);
      showToast('error', '收藏操作失败');
    }
  };

  /** 删除报告（软删除，DELETE_CONFIRM 模态确认，对齐 HistoryReports deleteReport） */
  const deleteReport = (reportId: string | number) => {
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '删除报告',
      content: '确定要删除这个报告吗？删除后将移入回收站，可在回收站恢复。',
      confirmText: '删除',
      cancelText: '取消',
      onConfirm: async () => {
        try {
          await reportsPort.delete(reportId);
          showToast('success', '报告删除成功');
          await loadReports();
        } catch (err: any) {
          showToast('error', '删除失败: ' + (err?.message || '未知错误'));
        }
      },
    }).catch(() => {});
  };

  onMounted(() => {
    loadReports();
    favoritesModule.loadFavorites();
  });

  onBeforeUnmount(() => {
    if (toastTimer) clearTimeout(toastTimer);
  });

  return {
    reports,
    total,
    currentPage,
    pageSize,
    totalPages,
    loading,
    error,
    toast,
    loadReports,
    getReportTypeLabel: getReportTypeLabelLocal,
    formatDate,
    viewReport,
    isFavorite: favoritesModule.isFavorite,
    handleToggleFavorite,
    deleteReport,
    handlePrevPage,
    handleNextPage,
    handleGoToPage,
    handlePageSizeChange,
  };
}
