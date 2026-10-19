// -*- coding: utf-8 -*-
/**
 * 报告统计分析 composable（G04，INT-859 接线）
 *
 * 四页签（统计维度/统计结果/趋势分析/报表生成）真实数据接入：
 * - executeStatistics → reportStatisticsPort.getStatistics（overview/detail/chart/anomaly）
 * - executeTrend       → reportStatisticsPort.getTrend（time_trend / dimension_trend）
 * - generateReport     → reportStatisticsPort.generateReport（Blob 下载）
 * 空/错态由页面按 loading / error / 无数据分支渲染，本层不造数据兜底。
 *
 * 契约对应（doc/接口文档/06_报告管理.md §8 + React 15_报告域 §2.2）：
 * 统计维度=时间/任务/设备/指标；统计结果=概览/详细/图表/异常；
 * 趋势分析=时间趋势/维度趋势/趋势图表/预测分析（预测呈现归前端）；
 * 报表生成=报表类型/内容/格式/执行。
 */
import { ref } from 'vue'
import { reportStatisticsPort } from '@/composables/report/reportStatisticsPort'
import { downloadBlob } from '@/utils/utils'
import type {
  ReportStatisticsData,
  ReportStatisticsTrendData,
  ReportStatisticsDimension,
  ReportStatisticsFormat,
  GenerateReportParams,
} from '@/domain'

export type StatisticsTabValue = 'dimension' | 'result' | 'trend' | 'report'

export interface StatisticsTabOption {
  value: StatisticsTabValue
  label: string
  icon: string
}

export const STATISTICS_TABS: ReadonlyArray<StatisticsTabOption> = [
  { value: 'dimension', label: '统计维度', icon: 'fas fa-table-columns' },
  { value: 'result', label: '统计结果', icon: 'fas fa-chart-pie' },
  { value: 'trend', label: '趋势分析', icon: 'fas fa-chart-line' },
  { value: 'report', label: '报表生成', icon: 'fas fa-file-export' },
]

/** 统计维度选项（§2.2：时间/任务类型/设备类型/评估维度） */
export const DIMENSION_OPTIONS = [
  { value: 'time', label: '时间' },
  { value: 'task_type', label: '任务类型' },
  { value: 'device_type', label: '设备类型' },
  { value: 'evaluation_metric', label: '评估维度' },
] as const

/** 统计结果子页签 */
export const RESULT_SUB_TABS = [
  { value: 'overview', label: '概览' },
  { value: 'detail', label: '详细' },
  { value: 'chart', label: '图表' },
  { value: 'anomaly', label: '异常' },
] as const

/** 趋势分析子页签 */
export const TREND_SUB_TABS = [
  { value: 'time_trend', label: '时间趋势' },
  { value: 'dimension_trend', label: '维度趋势' },
  { value: 'trend_chart', label: '趋势图表' },
  { value: 'forecast', label: '预测分析' },
] as const

/** 报表生成：报表类型/格式 */
export const REPORT_TYPE_OPTIONS = [
  { value: 'report_count', label: '报告数量统计' },
  { value: 'case_execution', label: '测试用例执行统计' },
  { value: 'evaluation_metric', label: '评估指标统计' },
  { value: 'device_performance', label: '设备性能统计' },
] as const

export const REPORT_FORMAT_OPTIONS = [
  { value: 'csv', label: 'CSV' },
  { value: 'excel', label: 'Excel' },
  { value: 'pdf', label: 'PDF' },
  { value: 'html', label: 'HTML' },
] as const

/** 趋势子页签 → trend_type 映射（图表/预测以时间趋势为数据源） */
const TREND_TYPE_BY_SUB_TAB: Record<string, 'time' | 'dimension'> = {
  time_trend: 'time',
  dimension_trend: 'dimension',
  trend_chart: 'time',
  forecast: 'time',
}

/** 报表格式 → 文件扩展名（BFF 未回传 Content-Disposition，本地按格式拼名） */
const FORMAT_EXTENSION: Record<ReportStatisticsFormat, string> = {
  csv: 'csv',
  excel: 'xlsx',
  pdf: 'pdf',
  html: 'html',
}

/** 报表生成本地记录（仅会话内呈现，非后端数据） */
export interface GeneratedReportRecord {
  filename: string
  format: string
  generatedAt: string
}

function nowStamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`
}

export function useReportStatistics() {
  const activeTab = ref<StatisticsTabValue>(STATISTICS_TABS[0].value)

  // 统计维度 / 时间范围（表单态）
  const dimension = ref<string>(DIMENSION_OPTIONS[0].value)
  const startDate = ref('')
  const endDate = ref('')

  // 统计结果子页签
  const resultSubTab = ref<string>(RESULT_SUB_TABS[0].value)
  // 趋势分析子页签
  const trendSubTab = ref<string>(TREND_SUB_TABS[0].value)
  // 报表生成表单态
  const reportType = ref<string>(REPORT_TYPE_OPTIONS[0].value)
  const reportFormat = ref<string>(REPORT_FORMAT_OPTIONS[0].value)
  const reportContent = ref('')

  // ---- 统计结果（GET /reports/statistics）----
  const statisticsLoading = ref(false)
  const statisticsError = ref('')
  const statisticsData = ref<ReportStatisticsData | null>(null)

  // ---- 趋势分析（GET /reports/statistics/trend）----
  const trendLoading = ref(false)
  const trendError = ref('')
  const trendData = ref<ReportStatisticsTrendData | null>(null)

  // ---- 报表生成（POST /reports/statistics/report）----
  const reportGenerating = ref(false)
  const generatedReports = ref<GeneratedReportRecord[]>([])

  const handleTabChange = (tab: StatisticsTabValue) => {
    activeTab.value = tab
  }

  /**
   * 执行统计分析：按当前维度 + 时间范围调用真实接口并渲染 overview/detail/chart/anomaly。
   * 失败时置 statisticsError（页面渲染错误态），不造数据兜底。
   */
  const executeStatistics = async (showToast: (type: 'success' | 'error' | 'info', message: string) => void) => {
    if (statisticsLoading.value) return
    statisticsLoading.value = true
    statisticsError.value = ''
    try {
      const result = await reportStatisticsPort.getStatistics({
        dimension: dimension.value as ReportStatisticsDimension,
        ...(startDate.value ? { startTime: startDate.value } : {}),
        ...(endDate.value ? { endTime: endDate.value } : {}),
      })
      statisticsData.value = result
      showToast('success', '统计分析完成')
    } catch (e: unknown) {
      const message = (e as Error)?.message || '统计分析失败'
      statisticsError.value = message
      statisticsData.value = null
      showToast('error', message)
    } finally {
      statisticsLoading.value = false
    }
  }

  /**
   * 执行趋势分析：按当前趋势子页签（time_trend/dimension_trend → trend_type）取趋势序列。
   */
  const executeTrend = async (showToast: (type: 'success' | 'error' | 'info', message: string) => void) => {
    if (trendLoading.value) return
    trendLoading.value = true
    trendError.value = ''
    try {
      const result = await reportStatisticsPort.getTrend({
        trendType: TREND_TYPE_BY_SUB_TAB[trendSubTab.value] ?? 'time',
        ...(startDate.value ? { startTime: startDate.value } : {}),
        ...(endDate.value ? { endTime: endDate.value } : {}),
      })
      trendData.value = result
      showToast('success', '趋势分析完成')
    } catch (e: unknown) {
      const message = (e as Error)?.message || '趋势分析失败'
      trendError.value = message
      trendData.value = null
      showToast('error', message)
    } finally {
      trendLoading.value = false
    }
  }

  /**
   * 生成报表：POST 真实接口 → Blob 下载。格式本地拼文件名（BFF 二进制链路不回传头）。
   */
  const generateReport = async (showToast: (type: 'success' | 'error' | 'info', message: string) => void) => {
    if (reportGenerating.value) return
    reportGenerating.value = true
    try {
      const params: GenerateReportParams = {
        reportType: reportType.value as GenerateReportParams['reportType'],
        format: reportFormat.value as ReportStatisticsFormat,
        ...(reportContent.value ? { content: reportContent.value } : {}),
        ...(startDate.value ? { startTime: startDate.value } : {}),
        ...(endDate.value ? { endTime: endDate.value } : {}),
      }
      const blob = await reportStatisticsPort.generateReport(params)
      const extension = FORMAT_EXTENSION[params.format] || params.format
      const filename = `statistics_report_${nowStamp()}.${extension}`
      downloadBlob(blob, filename)
      generatedReports.value.unshift({ filename, format: params.format, generatedAt: new Date().toLocaleString() })
      showToast('success', '报表已生成并开始下载')
    } catch (e: unknown) {
      const message = (e as Error)?.message || '报表生成失败'
      showToast('error', message)
    } finally {
      reportGenerating.value = false
    }
  }

  return {
    activeTab,
    dimension,
    startDate,
    endDate,
    resultSubTab,
    trendSubTab,
    reportType,
    reportFormat,
    reportContent,
    statisticsLoading,
    statisticsError,
    statisticsData,
    trendLoading,
    trendError,
    trendData,
    reportGenerating,
    generatedReports,
    handleTabChange,
    executeStatistics,
    executeTrend,
    generateReport,
  }
}
