// -*- coding: utf-8 -*-
/**
 * 报告统计分析 composable（G04，INT-741）
 *
 * 后端状态：**待 FEAT**（无 `/reports/statistics*` 端点，总表 §3.3 F1）——
 * 本页为 UI 出壳：四页签（统计维度/统计结果/趋势分析/报表生成）+ 维度与时间范围
 * 表单 + 执行入口，**不发起真实请求、不造数据兜底**；执行入口点击提示待后端立项。
 *
 * 契约对应（React 15_报告域 §2.2；负责人 2026-10-22 口径：移除「任务类型」维度）：
 * 统计维度=时间/设备/指标；统计结果=概览/详细/图表/异常；
 * 趋势分析=时间趋势/维度趋势/趋势图表/预测分析；报表生成=报表类型/内容/格式/执行。
 */
import { ref } from 'vue'

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

/** 统计维度选项（负责人 2026-10-22 口径：移除「任务类型」维度，仅时间/设备类型/评估维度；后端维度仍返回时前端不展示） */
export const DIMENSION_OPTIONS = [
  { value: 'time', label: '时间' },
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
  { value: 'metric', label: '评估指标统计' },
  { value: 'device_perf', label: '设备性能统计' },
] as const

export const REPORT_FORMAT_OPTIONS = [
  { value: 'csv', label: 'CSV' },
  { value: 'excel', label: 'Excel' },
  { value: 'pdf', label: 'PDF' },
  { value: 'html', label: 'HTML' },
] as const

export function useReportStatistics() {
  const activeTab = ref<StatisticsTabValue>(STATISTICS_TABS[0].value)

  // 统计维度 / 时间范围（表单态；端点落地前不消费）
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

  /** 待后端立项提示文案（统一出口，FEAT 落地后移除） */
  const pendingNotice =
    '统计分析接口待后端立项（/reports/statistics*，总表 §3.3 F1）。接口落地后由【接线·新Vue·报告域】卡接入真实数据。'

  const handleTabChange = (tab: StatisticsTabValue) => {
    activeTab.value = tab
  }

  /**
   * 执行统计分析（G04 出壳）：端点未具，不做数据兜底——仅提示待后端立项。
   * FEAT 落地后此处改为调用 reportStatisticsApi.getStatistics 并渲染结果。
   */
  const executeStatistics = (showToast: (type: 'success' | 'error' | 'info', message: string) => void) => {
    showToast('info', '统计分析接口待后端立项，暂时无法执行。')
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
    pendingNotice,
    handleTabChange,
    executeStatistics,
  }
}
