import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useRouter } from 'vue-router';
import { reportsPort } from '@/composables/report/reportsPort';
import { useModalControl } from '@/composables/modal/useModal';
import { MODAL_TYPES } from '@/composables/modal/constants';
import { useAlgorithmLabels } from '../../composables/algorithm/useAlgorithmLabels';
import { getReportTypeLabel } from '../../domain/constants/reportLabels';
import type { Report, ReportListQuery as ReportListParams } from '../../domain';
import type { ToastMessage } from '../../domain/model/ui';
import { reportChannelPort } from '@/composables/report/reportChannelPort';
import { readCamel } from '../../utils/keyTransform';
import { usePagination } from '../../composables/usePagination';
import { ReportStatus } from '@/domain/enums';
import { formatDate } from '@/utils/utils';
import { useFavorites } from '../../composables/favorite/useFavorites';

/**
 * 历史报告页视图 Tab 常量（全部/草稿/已发布/对比）。
 * 值与后端列表接口的 type / status 过滤参数对应；对比视图为多类型服务端过滤。
 */
export const REPORT_TABS = {
  ALL: 'all',
  DRAFT: 'draft',
  PUBLISHED: 'published',
  COMPARISON: 'comparison',
} as const;

export type ReportTabValue = (typeof REPORT_TABS)[keyof typeof REPORT_TABS];

export interface ReportTabOption {
  value: ReportTabValue;
  label: string;
  icon: string;
}

export const REPORT_TAB_OPTIONS: ReadonlyArray<ReportTabOption> = [
  { value: REPORT_TABS.ALL, label: '全部报告', icon: 'fas fa-layer-group' },
  { value: REPORT_TABS.DRAFT, label: '草稿报告', icon: 'fas fa-edit' },
  { value: REPORT_TABS.PUBLISHED, label: '发布报告', icon: 'fas fa-check-circle' },
  { value: REPORT_TABS.COMPARISON, label: '对比报告', icon: 'fas fa-exchange-alt' },
];

/** 归类为「对比报告」视图的报告类型集合（domain ReportType 后端原值：task/comparison/secondary_comparison/standard） */
const COMPARISON_REPORT_TYPES: readonly string[] = ['comparison', 'secondary_comparison'];

/**
 * INT-1390：报告是否可参与二次对比（对齐后端 report_compare_helpers._validate_reports_and_get_tasks
 * 的任务派生口径）。Benchmark 快照报告（发布时点定格，无 task 关联）后端必然
 * 「未找到关联的任务数据」；对比家族报告经 summary_info.task_ids 派生任务视为可参与；
 * 其余类型须列表项带 taskId 才有任务数据。
 */
function isReportComparableForSecondaryCompare(report: Report): boolean {
  if (report.type === 'benchmark') return false;
  if (COMPARISON_REPORT_TYPES.includes(report.type)) return true;
  return report.taskId !== undefined && report.taskId !== null;
}

/**
 * Tab → 列表接口过滤参数映射（配置化，避免魔法字符串；恢复 V9.7.10 基线口径）。
 * - 草稿/已发布 Tab 下发 status 服务端过滤；
 * - 对比 Tab 下发逗号分隔多类型（report_service split_report_types IN 过滤）；
 * - 「全部」Tab 无附加过滤。
 * 注意：Tab 过滤与筛选栏 filters.reportType/reportStatus 相互独立（Tab 切换不回写筛选栏），
 * 两者在 loadReports 合并下发。
 */
const TAB_TO_FILTER: Record<ReportTabValue, { status?: ReportStatusFilter; type?: ReportTypeFilter; types?: string[] }> = {
  [REPORT_TABS.ALL]: {},
  [REPORT_TABS.DRAFT]: { status: 'draft' },
  [REPORT_TABS.PUBLISHED]: { status: 'published' },
  [REPORT_TABS.COMPARISON]: { types: [...COMPARISON_REPORT_TYPES] },
};

type ReportTypeFilter = 'all' | 'comparison' | 'secondary_comparison' | 'task' | 'benchmark';
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

const toast = ref<ToastMessage | null>(null);

function showToast(type: ToastMessage['type'], message: string): void {
  toast.value = { type, message };
  setTimeout(() => {
    toast.value = null;
  }, 3000);
}

export function useHistoryReports() {
  const router = useRouter();
  const modalManager = useModalControl();
  const allReports = ref<Report[]>([]);
  const totalItems = ref(0);
  const currentPage = ref(1);
  const pageSize = ref(10);
  const loading = ref(false);
  /** INT-969：列表加载错误态（区别于空态；失败时置错误文案，成功/重试后清空） */
  const error = ref('');
  const selectedReports = ref<Set<string | number>>(new Set());
  const activeTab = ref<ReportTabValue>(REPORT_TABS.ALL);

  /**
   * INT-1390 返工：选中报告元数据快照（id → Report）。
   * 选择时同步记录，跨页/已过滤（选中项不在当前 allReports 列表）时，
   * 批量对比可对比性判定仍基于此快照，修复「跨页残留选中绕过禁用态」。
   * 取消选择 / 清空选择时同步删除。
   */
  const selectedReportMeta = ref<Map<string, Report>>(new Map());

  /** 清空全部选中（selectedReports + 元数据快照） */
  const clearSelection = () => {
    selectedReports.value.clear();
    selectedReportMeta.value.clear();
  };

  /** INT-1390：选中报告项（当前列表优先取最新元数据；跨页/已过滤的 id 回退选择时快照） */
  const selectedReportItems = computed<Report[]>(() => {
    const byId = new Map(allReports.value.map(r => [String(r.id), r]));
    return Array.from(selectedReports.value)
      .map(id => byId.get(String(id)) ?? selectedReportMeta.value.get(String(id)))
      .filter((r): r is Report => r !== undefined);
  });

  /** INT-1390：选中集中不可参与二次对比的报告（Benchmark 快照 / 无 task 关联） */
  const unsupportedCompareReports = computed<Report[]>(() =>
    selectedReportItems.value.filter(r => !isReportComparableForSecondaryCompare(r)),
  );

  /** INT-1390：批量对比禁用态（选中集含不可对比报告时禁用，避免必然失败的后端请求） */
  const batchCompareDisabled = computed(() => unsupportedCompareReports.value.length > 0);

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

  // ===== 收藏 / 回收站（INT-141）=====
  const favoritesModule = useFavorites('report');
  /** 仅看收藏 */
  const favoriteOnly = favoritesModule.favoriteOnly;
  /** 回收站模式（deleted=true 拉取 + 卡片操作切换为恢复/彻底删除） */
  const trashMode = ref(false);
  /** INT-423/467：可见性筛选（'' | 'shared' | 'private'；服务端行级过滤） */
  const visibilityFilter = ref('');

  // ===== Tab 计数（INT-280：服务端聚合，多页数据下不失真）=====
  /** 四个 Tab 的全量计数（键 = ReportTabValue）；接口失败时回退空对象，计数隐藏为 0 */
  const tabCounts = ref<Record<ReportTabValue, number>>({
    [REPORT_TABS.ALL]: 0,
    [REPORT_TABS.DRAFT]: 0,
    [REPORT_TABS.PUBLISHED]: 0,
    [REPORT_TABS.COMPARISON]: 0,
  });

  /** 拉取 Tab 全量计数（mounted / 列表数据变更动作后刷新；失败静默，不影响主列表） */
  const loadTabCounts = async () => {
    try {
      const counts = await reportsPort.getTabCounts();
      tabCounts.value = {
        [REPORT_TABS.ALL]: counts[REPORT_TABS.ALL] ?? 0,
        [REPORT_TABS.DRAFT]: counts[REPORT_TABS.DRAFT] ?? 0,
        [REPORT_TABS.PUBLISHED]: counts[REPORT_TABS.PUBLISHED] ?? 0,
        [REPORT_TABS.COMPARISON]: counts[REPORT_TABS.COMPARISON] ?? 0,
      };
    } catch (error) {
      console.error('加载报告 Tab 计数失败:', error);
    }
  };

  /** 数据变更动作后的统一刷新：列表重取 + Tab 计数重取（INT-280 计数不陈旧） */
  const refreshAfterMutation = async () => {
    await Promise.all([loadReports(), loadTabCounts()]);
  };

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
      // INT-280：视图 Tab 附加过滤随请求下发（草稿/已发布按状态、对比按多类型），
      // 与筛选栏条件并存（Tab 切换不回写筛选栏），分页/计数以服务端过滤为准
      const tabMapping = TAB_TO_FILTER[activeTab.value];
      if (tabMapping.status && tabMapping.status !== 'all') {
        params.status = filters.value.reportStatus !== 'all' ? filters.value.reportStatus : tabMapping.status;
      }
      if (tabMapping.type && tabMapping.type !== 'all' && filters.value.reportType === 'all') {
        params.type = tabMapping.type;
      }
      if (tabMapping.types) {
        params.type = [...tabMapping.types].join(',');
      }
      // INT-141：收藏 / 回收站过滤
      if (favoriteOnly.value && !trashMode.value) params.favorite = true;
      if (trashMode.value) params.deleted = true;
      // INT-423/467：可见性过滤（服务端行级过滤；回收站态互斥）
      if (visibilityFilter.value && !trashMode.value) params.visibility = visibilityFilter.value;

      const data = await reportsPort.getAll(params);
      allReports.value = data?.items || [];
      totalItems.value = data?.total || 0;
      error.value = '';
    } catch (err) {
      console.error('加载报告失败:', err);
      // INT-969：列表加载失败进独立错误态（区别于空态），用户可点重试
      error.value = '加载报告失败，请稍后重试';
      showToast('error', '加载报告失败，请稍后重试');
      allReports.value = [];
      totalItems.value = 0;
    } finally {
      loading.value = false;
    }
  };

  /** 收藏 / 取消收藏（星标切换） */
  const handleToggleFavorite = async (report: Report) => {
    try {
      await favoritesModule.toggleFavorite(report.id);
      showToast('success', favoritesModule.isFavorite(report.id) ? '已收藏' : '已取消收藏');
    } catch (error) {
      showToast('error', '收藏操作失败');
    }
  };

  const handleRestoreReport = async (report: Report) => {
    try {
      const result = await favoritesModule.restore([report.id]);
      // INT-215：按后端 restored_count 判定真实结果，count=0 提示无可操作项而非假成功
      const restored = result?.restored_count ?? 0;
      if (restored > 0) {
        showToast('success', `报告「${report.name}」已恢复`);
      } else {
        showToast('info', '无可恢复项（报告可能已被恢复）');
      }
      await refreshAfterMutation();
    } catch (error) {
      showToast('error', '恢复报告失败');
    }
  };

  const handlePurgeReport = async (report: Report) => {
    // INT-215：确认弹窗统一收敛到 BASIC_CONFIRM 模态（对齐全站危险操作范式）
    let confirmed = false;
    try {
      confirmed = await modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
        title: '彻底删除报告',
        content: `彻底删除报告「${report.name}」？该操作不可恢复（仅管理员/所有者可执行）。`,
        confirmText: '彻底删除',
        cancelText: '取消',
        danger: true,
      });
    } catch {
      return; // 用户取消
    }
    if (!confirmed) return;
    try {
      const result = await favoritesModule.purge([report.id]);
      const purged = result?.purged_count ?? 0;
      if (purged > 0) {
        showToast('success', `报告「${report.name}」已彻底删除`);
      } else {
        showToast('info', '无可删除项（报告可能已被删除或不满足权限）');
      }
      await refreshAfterMutation();
    } catch (error) {
      showToast('error', '彻底删除报告失败');
    }
  };

  const toggleTrashMode = async () => {
    trashMode.value = !trashMode.value;
    // INT-215：回收站模式下收藏筛选不可用——联动清空勾选态，避免静默失效
    if (trashMode.value && favoriteOnly.value) {
      favoriteOnly.value = false;
    }
    // INT-215/S4：数据集切换（活跃↔已删）清空选中集，防止普通态勾选的活跃报告
    // 流入回收站态批量彻底删除（误删活跃项）；对照 handleTabChange 同口径
    clearSelection();
    currentPage.value = 1;
    await loadReports();
  };

  /** INT-215：收藏筛选切换（FavoriteTrashBar bar-toggle 口径，含刷新与分页重置） */
  const handleReportFavoriteFilterChange = async (value: boolean) => {
    favoriteOnly.value = value;
    currentPage.value = 1;
    await loadReports();
  };

  /** INT-423/467：可见性筛选切换（全部/共享/私有；含刷新与分页重置） */
  const handleVisibilityFilterChange = async (value: string | number) => {
    visibilityFilter.value = String(value) === 'all' ? '' : String(value);
    currentPage.value = 1;
    await loadReports();
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
    const totalCases = summary.totalCases || 0;
    // readCamel 先读 camelCase completedCases，兜底兼容未经 adapter 化的原始 summary
    const completedCases = readCamel<number>(summary, 'completedCases') || 0;
    const failedCases = summary.failedCases || 0;
    const successRate = summary.overallSuccessRate || summary.passRate || 0;
    
    if (report.type === 'task') {
      return `共 ${totalCases} 个测试用例，通过 ${completedCases} 个，失败 ${failedCases} 个，通过率 ${successRate}%`;
    } else if (report.type === 'comparison') {
      return `共对比 ${summary.taskCount || 0} 个任务，包含 ${totalCases} 个测试用例`;
    } else if (report.type === 'benchmark') {
      // INT-483：Benchmark 报告无用例统计（计数入 benchmark_reports 快照），列表无快照字段，展示占位文案
      return `Benchmark 排行快照报告（发布时点定格，点击查看详情）`;
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

  // 使用通用分页 composable 计算总页数
  // 说明：报告分页为服务端分页，totalItems 由 API 返回
  // 此处用 totalItems 长度的占位数组驱动 totalPages 计算
  const placeholderForTotal = computed(() => Array(totalItems.value).fill(0));
  const { totalPages } = usePagination(placeholderForTotal, pageSize, { currentPage });

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
    return allReports.value.filter(report => report.status === ReportStatus.PUBLISHED);
  });

  const draftReports = computed(() => {
    return allReports.value.filter(report => report.status === ReportStatus.DRAFT);
  });

  /** 归类为对比报告的报告（domain ReportType：comparison / secondary_comparison） */
  const comparisonReports = computed(() => {
    return allReports.value.filter(report => COMPARISON_REPORT_TYPES.includes(report.type));
  });

  /** 当前视图 Tab 下的可见报告列表（「全部」Tab 由视图层按状态分组展示） */
  const visibleReports = computed(() => {
    switch (activeTab.value) {
      case REPORT_TABS.DRAFT:
        return draftReports.value;
      case REPORT_TABS.PUBLISHED:
        return publishedReports.value;
      case REPORT_TABS.COMPARISON:
        return comparisonReports.value;
      default:
        return allReports.value;
    }
  });

  /** 各 Tab 的全量计数（INT-280：服务端聚合，不再按当前页统计） */
  const getTabCount = (tab: ReportTabValue): number => {
    return tabCounts.value[tab] ?? 0;
  };

  /**
   * 切换视图 Tab：更新 activeTab、清空已选、重置分页并按 Tab 过滤重新加载
   * （INT-280：恢复 V9.7.10 基线——Tab → 服务端 status/type 参数，非客户端过滤）
   */
  const handleTabChange = (tab: ReportTabValue) => {
    activeTab.value = tab;
    clearSelection();
    currentPage.value = 1;
    loadReports();
  };

  const toggleSelectAll = () => {
    if (isAllSelected.value) {
      clearSelection();
    } else {
      allReports.value.forEach(report => {
        selectedReports.value.add(report.id);
        selectedReportMeta.value.set(String(report.id), report);
      });
    }
  };

  const toggleReportSelection = (report: Report, event?: Event) => {
    if (event?.target instanceof HTMLElement && event.target.closest('.card-actions')) return;
    const reportId = report.id;
    if (selectedReports.value.has(reportId)) {
      selectedReports.value.delete(reportId);
      selectedReportMeta.value.delete(String(reportId));
    } else {
      selectedReports.value.add(reportId);
      selectedReportMeta.value.set(String(reportId), report);
    }
  };

  const handleBatchDelete = () => {
    if (selectedReports.value.size === 0) return;
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '批量删除报告',
      content: `确定要删除选中的 ${selectedReports.value.size} 个报告吗？删除后将移入回收站，可在回收站恢复。`,
      confirmText: '删除',
      cancelText: '取消',
      onConfirm: async () => {
        try {
          const ids = Array.from(selectedReports.value);
          await reportsPort.batchDelete(ids);
          clearSelection();
          showToast('success', `成功删除 ${ids.length} 个报告`);
          refreshAfterMutation();
        } catch (error: any) {
          showToast('error', '批量删除失败: ' + (error.message || '未知错误'));
        }
      }
    }).catch(() => {});
  };

  const handleBatchCancel = () => {
    clearSelection();
  };

  // ===== INT-215/S4：回收站态批量栏适配（对齐任务侧批量恢复/彻底删除能力）=====

  /** 批量恢复（恢复为可逆操作，与任务侧一致不设确认；按 restored_count 反馈真实结果） */
  const handleBatchRestore = async () => {
    if (selectedReports.value.size === 0) return;
    try {
      const ids = Array.from(selectedReports.value);
      const result = await favoritesModule.restore(ids);
      const restored = result?.restored_count ?? 0;
      if (restored > 0) {
        showToast('success', `已恢复 ${restored} 个报告`);
      } else {
        showToast('info', '无可恢复项（报告可能已被恢复）');
      }
      clearSelection();
      await refreshAfterMutation();
    } catch (error: any) {
      showToast('error', '批量恢复失败: ' + (error?.message || '未知错误'));
    }
  };

  /** 批量彻底删除（BASIC_CONFIRM 模态 + 不可恢复警示；按 purged_count 反馈真实结果） */
  const handleBatchPurge = () => {
    if (selectedReports.value.size === 0) return;
    modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '批量彻底删除报告',
      content: `彻底删除选中的 ${selectedReports.value.size} 个报告？该操作不可恢复（仅管理员/所有者可执行）。`,
      confirmText: '彻底删除',
      cancelText: '取消',
      danger: true,
      onConfirm: async () => {
        try {
          const ids = Array.from(selectedReports.value);
          const result = await favoritesModule.purge(ids);
          const purged = result?.purged_count ?? 0;
          if (purged > 0) {
            showToast('success', `已彻底删除 ${purged} 个报告`);
          } else {
            showToast('info', '无可删除项（报告可能已被删除或不满足权限）');
          }
          clearSelection();
          await refreshAfterMutation();
        } catch (error: any) {
          showToast('error', '批量彻底删除失败: ' + (error?.message || '未知错误'));
        }
      }
    }).catch(() => {});
  };

  const pendingSecondaryCompareReports = ref<Map<string, { reportIds: (string | number)[]; resolve: (id: string | number) => void; reject: (err: Error) => void }>>(new Map());

  const handleBatchCompare = async () => {
    if (selectedReports.value.size < 2) {
      showToast('warning', '请至少选择2个报告进行对比');
      return;
    }
    // INT-1390：Benchmark 快照 / 无 task 关联报告不可参与二次对比——前置提示而非必然失败的后端请求
    if (unsupportedCompareReports.value.length > 0) {
      const names = unsupportedCompareReports.value.map(r => r.name).join('、');
      showToast('warning', `所选报告不支持对比：${names}（Benchmark 快照或无任务关联，不可参与二次对比）`);
      return;
    }
    try {
      const ids = Array.from(selectedReports.value);
      const result = await reportsPort.secondaryCompare(ids);

      if (result.status === 'generating') {
        showToast('info', '对比报告生成中，请稍后...');
        reportChannelPort.connect();

        const reportKey = (result.reportKey ?? []).join(',');
        const reportId = await new Promise<string | number>((resolve, reject) => {
          const timeout = setTimeout(() => {
            pendingSecondaryCompareReports.value.delete(reportKey);
            reportChannelPort.offSecondaryCompareGenerated(handleSecondaryCompareGenerated);
            reject(new Error('对比报告生成超时'));
          }, 180000);

          const handleSecondaryCompareGenerated = (data: any) => {
            const dataKey = (data.reportIds || []).sort().join(',');
            if (dataKey === reportKey) {
              clearTimeout(timeout);
              reportChannelPort.offSecondaryCompareGenerated(handleSecondaryCompareGenerated);
              pendingSecondaryCompareReports.value.delete(reportKey);

              if (!data.success) {
                reject(new Error(data.error || '对比报告生成失败'));
                return;
              }
              resolve(data.reportId);
            }
          };

          pendingSecondaryCompareReports.value.set(reportKey, { reportIds: ids, resolve, reject });
          reportChannelPort.onSecondaryCompareGenerated(handleSecondaryCompareGenerated);
        });

        showToast('success', '对比报告生成成功');
        router.push({ name: 'reportView', params: { id: reportId } });
      } else {
        showToast('success', '对比报告生成成功');
      }
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

  const deleteReport = (reportId: string | number) => {
    modalManager.open(MODAL_TYPES.DELETE_CONFIRM, {
      title: '删除报告',
      content: '确定要删除这个报告吗？删除后将移入回收站，可在回收站恢复。',
      confirmText: '删除',
      cancelText: '取消',
      onConfirm: async () => {
        try {
          await reportsPort.delete(reportId);
          selectedReports.value.delete(reportId);
          selectedReportMeta.value.delete(String(reportId));
          showToast('success', '报告删除成功');
          refreshAfterMutation();
        } catch (error: any) {
          showToast('error', '删除失败: ' + (error.message || '未知错误'));
        }
      }
    }).catch(() => {});
  };

  const publishReport = (reportId: string | number) => {
    modalManager.open(MODAL_TYPES.BASIC_CONFIRM, {
      title: '发布报告',
      content: '确定要发布这个报告吗？',
      confirmText: '发布',
      cancelText: '取消',
      onConfirm: async () => {
        try {
          await reportsPort.publish(reportId);
          showToast('success', '报告发布成功');
          refreshAfterMutation();
        } catch (error: any) {
          showToast('error', '发布失败: ' + (error.message || '未知错误'));
        }
      }
    }).catch(() => {});
  };

  onMounted(() => {
    loadReports();
    // INT-280：Tab 全量计数服务端拉取
    loadTabCounts();
    loadAlgorithmOptions();
    // INT-141：加载当前用户收藏集合
    favoritesModule.loadFavorites();
  });

  onBeforeUnmount(() => {
    clearSelection();
    pendingSecondaryCompareReports.value.clear();
  });

  return {
    allReports,
    totalItems,
    currentPage,
    pageSize,
    loading,
    error,
    selectedReports,
    filters,
    sort,
    algorithmOptions,
    toast,
    showToast,
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
    activeTab,
    reportTabOptions: REPORT_TAB_OPTIONS,
    publishedReports,
    draftReports,
    visibleReports,
    tabCounts,
    getTabCount,
    loadTabCounts,
    handleTabChange,
    toggleSelectAll,
    toggleReportSelection,
    handleBatchDelete,
    handleBatchCancel,
    handleBatchCompare,
    batchCompareDisabled,
    // INT-215/S4：回收站态批量恢复/彻底删除
    handleBatchRestore,
    handleBatchPurge,
    viewReport,
    editReport,
    deleteReport,
    publishReport,
    // 收藏 / 回收站（INT-141）
    favoriteOnly,
    trashMode,
    // INT-423/467：可见性筛选
    visibilityFilter,
    handleVisibilityFilterChange,
    toggleTrashMode,
    // INT-215：收藏筛选切换（FavoriteTrashBar）
    handleReportFavoriteFilterChange,
    loadReports,
    isFavorite: favoritesModule.isFavorite,
    handleToggleFavorite,
    handleRestoreReport,
    handlePurgeReport
  };
}
