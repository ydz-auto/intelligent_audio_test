/**
 * 报告统计分析常量（interfaces/features/report-statistics 层；15_报告域.md §2.2，INT-381 返修补全）。
 * 文案对照 §7「报告统计分析页面」与报告管理功能设计文档.md §3.6.1/:318-340 + §5.2.4/:570-594。
 * StatisticDimension 类型驻留 domain/models/report-statistics.ts（application 层反向引用解耦）。
 */
import type { StatisticDimension } from '@/domain/models/report-statistics'

export type { StatisticDimension } from '@/domain/models/report-statistics'

/** 统计维度（维度 Select；§2.2 时间/任务类型/设备类型/评估维度） */
export const STATISTIC_DIMENSIONS: { value: StatisticDimension; label: string }[] = [
  { value: 'time', label: '时间' },
  { value: 'task_type', label: '任务类型' },
  { value: 'device_type', label: '设备类型' },
  { value: 'metric', label: '评估维度' },
]

/** 四标签页（§5.2.4） */
export const STATISTIC_TABS: { value: StatisticTab; label: string }[] = [
  { value: 'dimension', label: '统计维度' },
  { value: 'result', label: '统计结果' },
  { value: 'trend', label: '趋势分析' },
  { value: 'report', label: '报表生成' },
]

export type StatisticTab = 'dimension' | 'result' | 'trend' | 'report'

/** 统计结果子页签：概览/详细/图表/异常 */
export const RESULT_SUB_TABS: { value: ResultSubTab; label: string }[] = [
  { value: 'overview', label: '概览' },
  { value: 'detail', label: '详细' },
  { value: 'chart', label: '图表' },
  { value: 'anomaly', label: '异常' },
]

export type ResultSubTab = 'overview' | 'detail' | 'chart' | 'anomaly'

/** 趋势分析子页签 */
export const TREND_SUB_TABS: { value: TrendSubTab; label: string }[] = [
  { value: 'time', label: '时间趋势' },
  { value: 'dimension', label: '维度趋势' },
  { value: 'chart', label: '趋势图表' },
  { value: 'forecast', label: '预测分析' },
]

export type TrendSubTab = 'time' | 'dimension' | 'chart' | 'forecast'

/** 统计图表类型（散点图/热力图，§2.2/§3.7） */
export const STATISTIC_CHART_TYPES: { value: 'scatter' | 'heatmap'; label: string }[] = [
  { value: 'scatter', label: '散点图' },
  { value: 'heatmap', label: '热力图' },
]

/** 报表生成：报表类型/报表格式 */
export const REPORT_FORM_TYPES: string[] = ['统计分析报告', '维度对比报表', '指标明细报表']
export const REPORT_FORM_FORMATS: { value: string; label: string }[] = [
  { value: 'excel', label: 'Excel' },
  { value: 'csv', label: 'CSV' },
  { value: 'pdf', label: 'PDF' },
  { value: 'html', label: 'HTML' },
]

/** 执行摘要统计卡（§2.2 功能：报告数量/用例执行统计/评估指标/设备性能） */
export const STATISTIC_SUMMARY_CARDS: {
  key: 'reports' | 'cases' | 'metrics' | 'devices'
  label: string
}[] = [
  { key: 'reports', label: '报告数量' },
  { key: 'cases', label: '测试用例执行统计' },
  { key: 'metrics', label: '评估指标' },
  { key: 'devices', label: '设备性能' },
]
