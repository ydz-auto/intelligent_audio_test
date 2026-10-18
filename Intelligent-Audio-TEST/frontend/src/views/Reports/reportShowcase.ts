// -*- coding: utf-8 -*-
/**
 * 报告展示页 composable（G01，INT-741）
 *
 * 页面定位：顶部导航「报告」直达的对外展示页——弱管理，仅展示**已发布**报告，
 * 行操作只有「查看 / 复制链接」；管理操作集中到报告中心 `/report-center`。
 *
 * 算法切换口径（总表 §2.4 / INT-442）：本页**不渲染右上角全局算法切换器**，
 * 改页内**算法卡片网格**（每算法一张大卡，首卡「全部算法」），点击选中即过滤
 * 下方报告列表（请求自动附 `algorithm_type`）。
 *
 * 全局算法 store（基座卡 INT-735 `useGlobalAlgorithmStore`，localStorage
 * `iatp:algorithm:v1`）属基座线契约；基座线合入前本页以页内 ref 承载选中态并
 * **读写同一 localStorage 键**，基座落地后选中值自动衔接同一 store。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { reportsPort } from '@/composables/report/reportsPort'
import { algorithmPort } from '@/composables/algorithm/algorithmPort'
import type { AlgorithmDefinition } from '@/domain/model/algorithm'
import type { Report, ReportListQuery } from '@/domain'
import { getReportTypeLabel } from '@/domain/constants/reportLabels'
import { formatDate, copyToClipboard } from '@/utils/utils'
import type { ToastMessage } from '@/domain/model/ui'

/** 全局算法切换持久化键（对齐基座卡 `iatp:algorithm:v1`；'all' 即未选中，不落盘） */
const ALGORITHM_STORAGE_KEY = 'iatp:algorithm:v1'

/** 读取 localStorage 存量选中算法（基座 store 同键，切换衔接） */
function readStoredAlgorithm(): string {
  try {
    return localStorage.getItem(ALGORITHM_STORAGE_KEY) || 'all'
  } catch {
    return 'all'
  }
}

function persistAlgorithm(type: string): void {
  try {
    if (type && type !== 'all') {
      localStorage.setItem(ALGORITHM_STORAGE_KEY, type)
    } else {
      localStorage.removeItem(ALGORITHM_STORAGE_KEY)
    }
  } catch {
    // localStorage 不可用时忽略持久化
  }
}

export type ShowcaseTimeRange = 'all' | 'today' | 'yesterday' | 'week' | 'month' | 'custom'

export interface ShowcaseSort {
  sortBy: 'createdAt' | 'name' | 'status' | 'algorithmType'
  order: 'asc' | 'desc'
}

const toast = ref<ToastMessage | null>(null)

function showToast(type: ToastMessage['type'], message: string): void {
  toast.value = { type, message }
  setTimeout(() => {
    toast.value = null
  }, 3000)
}

export function useReportShowcase() {
  const router = useRouter()

  // ===== 算法卡片网格 =====
  const algorithms = ref<AlgorithmDefinition[]>([])
  const selectedAlgorithm = ref<string>(readStoredAlgorithm()) // 'all' 或算法 type
  const loadingAlgorithms = ref(false)
  const algorithmError = ref('')

  // ===== 报告列表（仅已发布）=====
  const reports = ref<Report[]>([])
  const totalItems = ref(0)
  const currentPage = ref(1)
  const pageSize = ref(10)
  const loading = ref(false)

  // ===== 筛选 / 排序 =====
  const search = ref('')
  const reportType = ref<string>('all')
  const timeRange = ref<ShowcaseTimeRange>('all')
  const startDate = ref('')
  const endDate = ref('')
  const sort = ref<ShowcaseSort>({ sortBy: 'createdAt', order: 'desc' })

  // ===== 算法卡片网格：GET /algorithm/definitions（全量含描述/分组/状态）=====
  const loadAlgorithms = async () => {
    loadingAlgorithms.value = true
    algorithmError.value = ''
    try {
      const result = await algorithmPort.getDefinitions({ page: 1, perPage: 100 })
      // 按 displayOrder 稳定排序，保证卡片次序可预期
      algorithms.value = [...(result?.data || [])].sort(
        (a, b) => (a.displayOrder ?? 0) - (b.displayOrder ?? 0)
      )
    } catch (e) {
      console.error('加载算法详情失败:', e)
      algorithmError.value = '算法详情暂不可用'
      algorithms.value = []
    } finally {
      loadingAlgorithms.value = false
    }
  }

  /** 点击算法卡片：切换选中（'all' = 全部算法），列表随之过滤；选中值持久化到全局算法键 */
  const selectAlgorithm = (type: string) => {
    selectedAlgorithm.value = type
    persistAlgorithm(type)
    currentPage.value = 1
    loadReports()
  }

  const isAlgorithmSelected = (type: string) => selectedAlgorithm.value === type

  // ===== 报告列表 =====
  const calculateDateRange = () => {
    const now = new Date()
    switch (timeRange.value) {
      case 'today':
        startDate.value = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString().split('T')[0]
        endDate.value = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).toISOString().split('T')[0]
        break
      case 'yesterday':
        startDate.value = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1).toISOString().split('T')[0]
        endDate.value = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString().split('T')[0]
        break
      case 'week':
        startDate.value = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 7).toISOString().split('T')[0]
        endDate.value = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).toISOString().split('T')[0]
        break
      case 'month':
        startDate.value = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 30).toISOString().split('T')[0]
        endDate.value = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).toISOString().split('T')[0]
        break
      case 'custom':
        return
      default:
        startDate.value = ''
        endDate.value = ''
    }
  }

  const loadReports = async () => {
    loading.value = true
    try {
      const params: ReportListQuery = {
        page: currentPage.value,
        perPage: pageSize.value,
        sortBy: sort.value.sortBy,
        order: sort.value.order,
        // 展示页仅已发布报告（草稿/回收站不在此页展示）
        status: 'published',
      }
      if (search.value) params.keyword = search.value
      if (reportType.value && reportType.value !== 'all') params.type = reportType.value
      if (selectedAlgorithm.value !== 'all') params.algorithmType = selectedAlgorithm.value
      if (startDate.value) params.startTime = startDate.value
      if (endDate.value) params.endTime = endDate.value

      const data = await reportsPort.getAll(params)
      reports.value = data?.items || []
      totalItems.value = data?.total || 0
    } catch (e) {
      console.error('加载已发布报告失败:', e)
      showToast('error', '加载报告失败，请稍后重试')
      reports.value = []
      totalItems.value = 0
    } finally {
      loading.value = false
    }
  }

  const handleFilterChange = () => {
    calculateDateRange()
    currentPage.value = 1
    loadReports()
  }
  const handleSearchInput = () => {
    // 输入防抖由视图层 300ms 触发；此处直接刷新
    currentPage.value = 1
    loadReports()
  }

  const handleTypeFilterChange = (value: string | number) => {
    reportType.value = String(value)
    handleFilterChange()
  }

  const handleTimeRangeChange = (value: string | number) => {
    timeRange.value = String(value) as ShowcaseTimeRange
    handleFilterChange()
  }

  const clearDateRange = () => {
    startDate.value = ''
    endDate.value = ''
    handleFilterChange()
  }

  const handleSortChange = (sortBy: ShowcaseSort['sortBy']) => {
    if (sort.value.sortBy === sortBy) {
      sort.value.order = sort.value.order === 'asc' ? 'desc' : 'asc'
    } else {
      sort.value.sortBy = sortBy
      sort.value.order = 'desc'
    }
    currentPage.value = 1
    loadReports()
  }

  // ===== 行操作（仅查看 / 复制链接）=====
  const viewReport = (reportId: string | number) => {
    router.push({ name: 'reportView', params: { id: reportId } })
  }

  const copyReportLink = async (report: Report) => {
    // hash 路由：复制当前站内直达链接（#/report/{id}）
    const href = `${window.location.origin}${window.location.pathname}#/report/${report.id}`
    const ok = await copyToClipboard(href)
    showToast(ok ? 'success' : 'error', ok ? '链接已复制' : '复制链接失败')
  }

  // ===== 分页 =====
  const totalPages = computed(() => Math.max(1, Math.ceil(totalItems.value / pageSize.value)))

  const handlePrevPage = () => {
    if (currentPage.value > 1) {
      currentPage.value--
      loadReports()
    }
  }

  const handleNextPage = () => {
    if (currentPage.value < totalPages.value) {
      currentPage.value++
      loadReports()
    }
  }

  const handleGoToPage = (page: number) => {
    currentPage.value = page
    loadReports()
  }

  const handlePageSizeChange = (newSize: number) => {
    pageSize.value = newSize
    currentPage.value = 1
    loadReports()
  }

  onMounted(() => {
    loadAlgorithms()
    loadReports()
  })

  return {
    algorithms,
    selectedAlgorithm,
    loadingAlgorithms,
    algorithmError,
    selectAlgorithm,
    isAlgorithmSelected,
    reports,
    totalItems,
    currentPage,
    pageSize,
    loading,
    search,
    reportType,
    timeRange,
    startDate,
    endDate,
    sort,
    toast,
    showToast,
    handleSearchInput,
    handleTypeFilterChange,
    handleTimeRangeChange,
    handleFilterChange,
    clearDateRange,
    handleSortChange,
    viewReport,
    copyReportLink,
    handlePrevPage,
    handleNextPage,
    handleGoToPage,
    handlePageSizeChange,
    totalPages,
    getReportTypeLabel,
    formatDate,
  }
}
