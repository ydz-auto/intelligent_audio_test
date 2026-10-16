/**
 * 报告统计分析（application 层；15_报告域.md §2.2，INT-381 返修补全）。
 * 维度 Select × 时间范围 → 执行统计分析 → 统计卡/表格/图表/异常识别。
 * 数据 mock 常量（红线④），后续接线替换 API 桩即可，页面层不返工。
 * 对应报告管理功能设计文档.md §3.6.1/:318-340 + §5.2.4/:570-594。
 */
import { useQuery } from '@tanstack/react-query'

import type { ChartSeriesData } from '@/application/report-view/use-report-charts'
import { CHART_COLORS, colorArray } from '@/application/report-view/use-report-charts'
import type { StatisticDimension } from '@/domain/models/report-statistics'

export interface StatisticsTimeRange {
  start?: string
  end?: string
}

export interface StatisticSummaryItem {
  key: 'reports' | 'cases' | 'metrics' | 'devices'
  label: string
  value: number
  hint: string
}

export interface StatisticTableRow {
  dimension: string
  value: number
  ratio: number
  change: number
  status: 'normal' | 'up' | 'down'
}

export interface StatisticAnomalyRow {
  dimension: string
  value: number
  reason: string
}

export interface ReportStatisticsData {
  summary: StatisticSummaryItem[]
  rows: StatisticTableRow[]
  anomalyRows: StatisticAnomalyRow[]
  trend: ChartSeriesData
  scatter: ChartSeriesData
  heatmap: ChartSeriesData
}

/** 按维度生成统计 mock（确定性：维度不同 → 行/图不同，可走查；纯函数，供测试） */
export function computeStatistics(dimension: StatisticDimension): ReportStatisticsData {
  const rowsByDimension: Record<StatisticDimension, StatisticTableRow[]> = {
    time: [
      { dimension: '今日', value: 12, ratio: 10.8, change: 2, status: 'up' },
      { dimension: '近7天', value: 86, ratio: 77.5, change: 5, status: 'up' },
      { dimension: '近30天', value: 342, ratio: 11.7, change: -3, status: 'down' },
      { dimension: '自定义', value: 18, ratio: 0.0, change: 0, status: 'normal' },
    ],
    task_type: [
      { dimension: 'e2e 端到端', value: 186, ratio: 54.4, change: 8, status: 'up' },
      { dimension: 'api 接口', value: 112, ratio: 32.7, change: -2, status: 'down' },
      { dimension: 'mixed 混合', value: 44, ratio: 12.9, change: 1, status: 'normal' },
    ],
    device_type: [
      { dimension: '智能音箱', value: 168, ratio: 49.1, change: 6, status: 'up' },
      { dimension: '车载助手', value: 96, ratio: 28.1, change: -1, status: 'down' },
      { dimension: '耳机', value: 78, ratio: 22.8, change: 3, status: 'up' },
    ],
    metric: [
      { dimension: '唤醒成功率', value: 95.8, ratio: 0.0, change: 0.4, status: 'up' },
      { dimension: '识别准确率', value: 93.1, ratio: 0.0, change: -0.2, status: 'down' },
      { dimension: '平均响应时间', value: 412, ratio: 0.0, change: -8, status: 'up' },
    ],
  }

  const summary: StatisticSummaryItem[] = [
    { key: 'reports', label: '报告数量', value: 42, hint: '近30天 32 · 草稿 8 · 已发布 2' },
    { key: 'cases', label: '测试用例执行统计', value: 1186, hint: '完成 1092 · 失败 54 · 通过率 92.1%' },
    { key: 'metrics', label: '评估指标', value: 24, hint: '主维度 8 · 子维度 16' },
    { key: 'devices', label: '设备性能', value: 8, hint: '在线 6 · 离线 2 · 平均延迟 412ms' },
  ]

  const anomalyRows: StatisticAnomalyRow[] = [
    { dimension: '识别准确率', value: 93.1, reason: '入门机型低于旗舰约 2.4 个百分点' },
    { dimension: '平均响应时间', value: 486, reason: '入门机型延迟偏高，超过基线 15%' },
    { dimension: 'e2e 端到端', value: 186, reason: '周环比显著上升（+8），需关注回归覆盖' },
  ]

  const labels =
    dimension === 'time'
      ? ['10-11', '10-12', '10-13', '10-14', '10-15', '10-16']
      : dimension === 'task_type'
        ? ['e2e 端到端', 'api 接口', 'mixed 混合']
        : dimension === 'device_type'
          ? ['智能音箱', '车载助手', '耳机']
          : ['唤醒成功率', '识别准确率', '平均响应时间']

  const trend: ChartSeriesData = {
    labels,
    datasets: [
      {
        label: '执行用例数',
        data: dimension === 'time' ? [286, 298, 312, 334, 328, 342] : [1186, 1092, 54, 342, 92.1, 412].slice(0, labels.length),
        backgroundColor: colorArray(0, '59'),
        borderColor: CHART_COLORS.primary,
      },
    ],
  }

  // 散点图：通过率 × 平均响应（两个变量关系）
  const scatter: ChartSeriesData = {
    labels: [],
    datasets: [
      {
        label: '设备-通过率×延迟',
        data: [
          { x: 96.5, y: 412 },
          { x: 95.4, y: 428 },
          { x: 93.1, y: 486 },
          { x: 97.2, y: 385 },
          { x: 91.8, y: 502 },
          { x: 94.7, y: 455 },
          { x: 98.1, y: 398 },
          { x: 90.2, y: 520 },
        ],
        backgroundColor: CHART_COLORS.primary,
        pointRadius: 5,
      },
    ],
  }

  // 热力图：设备 × 评估维度 值矩阵
  const heatmap: ChartSeriesData = {
    labels: ['唤醒成功率', '识别准确率', '平均响应时间', '误唤醒率'],
    yLabels: ['旗舰-01', '旗舰-02', '入门-03', 'asr-streaming-v3', 'wakeword-detect-v2'],
    datasets: [
      {
        label: '评估维度分布',
        data: [
          { x: 0, y: 0, v: 96.5 }, { x: 1, y: 0, v: 94.2 }, { x: 2, y: 0, v: 412 }, { x: 3, y: 0, v: 3.2 },
          { x: 0, y: 1, v: 95.4 }, { x: 1, y: 1, v: 93.1 }, { x: 2, y: 1, v: 428 }, { x: 3, y: 1, v: 2.8 },
          { x: 0, y: 2, v: 93.1 }, { x: 1, y: 2, v: 91.8 }, { x: 2, y: 2, v: 486 }, { x: 3, y: 2, v: 4.1 },
          { x: 0, y: 3, v: 97.2 }, { x: 1, y: 3, v: 95.6 }, { x: 2, y: 3, v: 385 }, { x: 3, y: 3, v: 2.1 },
          { x: 0, y: 4, v: 94.8 }, { x: 1, y: 4, v: 92.4 }, { x: 2, y: 4, v: 201 }, { x: 3, y: 4, v: 2.4 },
        ],
      },
    ],
  }

  return {
    summary,
    rows: rowsByDimension[dimension],
    anomalyRows,
    trend,
    scatter,
    heatmap,
  }
}

export function useReportStatistics(
  dimension: StatisticDimension,
  range: StatisticsTimeRange,
  /** 执行序号：点击「执行统计分析」+1 → queryKey 变化 → 重查 */
  seq = 0
) {
  return useQuery({
    queryKey: ['report-statistics', dimension, seq, range.start ?? '', range.end ?? ''],
    queryFn: () => computeStatistics(dimension),
    staleTime: 60_000,
  })
}
