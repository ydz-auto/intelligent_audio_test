/**
 * 报告统计分析（application 层；15_报告域.md §2.2，INT-381 返修补全）。
 * 维度 Select × 时间范围 → 执行统计分析 → 统计卡/表格/图表/异常识别。
 * INT-643 接线：数据源从 mock 常量切真实端点——
 *   GET /reports/tab-counts（报告数量卡）+ GET /reports（时间/设备类型维度聚合、
 *   case-averages 任务上下文取最近任务报告 task_id）
 *   + POST /reports/case-averages（评估维度/散点·热力图/指标·设备卡）。
 *   snake→camel 转换只在 infrastructure 层（reports-api），本层只见 camelCase 域数据；
 *   异常识别后端无接口 → 空态（不虚构）；统计导出见 use-statistics-export。
 * INT-1297：移除「任务类型」统计维度（负责人 2026-10-22：前端不再区分 API测试/E2E测试）。
 * INT-1802：统计上下文不再认已删任务的报告（task_name 为空），避免 case-averages 400 整卡空态。
 * 对应报告管理功能设计文档.md §3.6.1/:318-340 + §5.2.4/:570-594。
 */
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'

import type { ChartSeriesData } from '@/application/report-view/use-report-charts'
import { CHART_COLORS, colorArray } from '@/application/report-view/use-report-charts'
import type { ReportCounts, ReportListItem } from '@/domain/models/report'
import type {
  ReportCaseAveragesData,
  ReportCaseAverageMetric,
  StatisticDimension,
} from '@/domain/models/report-statistics'
import {
  fetchCaseAverages,
  fetchReportCounts,
  fetchReportList,
} from '@/infrastructure/api/reports-api'

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
  /** 统计范围内的报告 id（统计结果导出的 ids 口径，POST /reports/export） */
  reportIds: number[]
}

const DAY_MS = 24 * 60 * 60 * 1000

const DEVICE_TYPE_LABELS: Record<string, string> = {
  smart_speaker: '智能音箱',
  car_voice: '车载助手',
  headphone: '耳机',
}

/** 今日 0 点时间戳 */
function dayStart(ts: number): number {
  const d = new Date(ts)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/** 报告列表按维度分组计数（时间/任务类型/设备类型维度数据源，全部来自 GET /reports 真实项） */
function groupedRows(
  reports: ReportListItem[],
  keyOf: (r: ReportListItem) => string | undefined,
  labels: Record<string, string>
): StatisticTableRow[] {
  const map = new Map<string, number>()
  for (const r of reports) {
    const key = keyOf(r) || 'unknown'
    map.set(key, (map.get(key) ?? 0) + 1)
  }
  const total = reports.length || 1
  return [...map.entries()].map(([key, value]) => ({
    dimension: labels[key] ?? key,
    value,
    ratio: Math.round((value / total) * 1000) / 10,
    change: 0,
    status: 'normal' as const,
  }))
}

/** 时间维度行：报告按创建时间落入 今日/近7天/近30天（+自定义时间范围） */
function timeRows(reports: ReportListItem[], range: StatisticsTimeRange): StatisticTableRow[] {
  const now = Date.now()
  const startTs = range.start ? new Date(range.start).getTime() : null
  const endTs = range.end ? new Date(range.end).getTime() : null
  const created = (r: ReportListItem): number => {
    const t = new Date(r.created_at).getTime()
    return Number.isFinite(t) ? t : NaN
  }
  const buckets = [
    { key: '今日', in: (t: number) => t >= dayStart(now) },
    { key: '近7天', in: (t: number) => t >= now - 7 * DAY_MS },
    { key: '近30天', in: (t: number) => t >= now - 30 * DAY_MS },
  ]
  const total = reports.length || 1
  const rows: StatisticTableRow[] = buckets.map((b) => {
    const value = reports.filter((r) => {
      const t = created(r)
      return Number.isFinite(t) && b.in(t)
    }).length
    return {
      dimension: b.key,
      value,
      ratio: Math.round((value / total) * 1000) / 10,
      change: 0,
      status: 'normal' as const,
    }
  })
  if (startTs !== null && endTs !== null) {
    const value = reports.filter((r) => {
      const t = created(r)
      return Number.isFinite(t) && t >= startTs && t <= endTs
    }).length
    rows.push({
      dimension: '自定义',
      value,
      ratio: Math.round((value / total) * 1000) / 10,
      change: 0,
      status: 'normal' as const,
    })
  }
  return rows
}

/** 评估维度行：case-averages overall_averages（真实指标均值） */
function metricRows(averages: ReportCaseAveragesData | null): StatisticTableRow[] {
  return (averages?.overallAverages ?? []).map((m: ReportCaseAverageMetric) => ({
    dimension: m.metric,
    value: m.value,
    ratio: 0,
    change: 0,
    status: 'normal' as const,
  }))
}

/** 近 7 天报告创建数折线（时间趋势数据源；全部来自 GET /reports 真实创建时间） */
function buildTrend(reports: ReportListItem[]): ChartSeriesData {
  const labels: string[] = []
  const data: number[] = []
  const now = new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    labels.push(`${d.getMonth() + 1}-${d.getDate()}`)
    const start = new Date(d)
    start.setHours(0, 0, 0, 0)
    const end = new Date(d)
    end.setHours(23, 59, 59, 999)
    data.push(
      reports.filter((r) => {
        const t = new Date(r.created_at).getTime()
        return Number.isFinite(t) && t >= start.getTime() && t <= end.getTime()
      }).length
    )
  }
  return {
    labels,
    datasets: [
      {
        label: '报告数量（近7天）',
        data,
        backgroundColor: colorArray(0, '59'),
        borderColor: CHART_COLORS.primary,
        fill: false,
        tension: 0.3,
      },
    ],
  }
}

/** 资源×指标矩阵（case-averages metric_data → {resources, metrics, matrix}） */
function buildMetricMatrix(averages: ReportCaseAveragesData | null): {
  resources: string[]
  metrics: string[]
  matrix: Record<string, Record<string, number>>
} {
  const matrix: Record<string, Record<string, number>> = {}
  const metricSet = new Set<string>()
  const resourceSet = new Set<string>()
  for (const g of averages?.metricData ?? []) {
    const res = g.resource || '未知资源'
    resourceSet.add(res)
    const cells: Record<string, number> = {}
    for (const m of g.metrics ?? []) {
      cells[m.metric] = m.value
      metricSet.add(m.metric)
    }
    for (const c of g.categories ?? []) {
      for (const m of c.metrics ?? []) {
        cells[m.metric] = m.value
        metricSet.add(m.metric)
      }
    }
    matrix[res] = cells
  }
  return { resources: [...resourceSet], metrics: [...metricSet], matrix }
}

/** 散点·热力图（数据源 case-averages metric_data；无数据 → 空态由图表组件呈现） */
function buildCharts(
  averages: ReportCaseAveragesData | null
): { scatter: ChartSeriesData; heatmap: ChartSeriesData } {
  const { resources, metrics, matrix } = buildMetricMatrix(averages)
  const empty: ChartSeriesData = { labels: [], datasets: [] }

  // 散点：每个资源取前两个指标值作 x/y（「通过率 × 平均响应时间」两变量关系语义）
  const scatterPoints: ChartSeriesData =
    resources.length > 0 && metrics.length > 0
      ? {
          labels: [],
          datasets: [
            {
              label: '资源-指标关系',
              data: resources
                .map((r) => {
                  const x = matrix[r]?.[metrics[0]]
                  const y = matrix[r]?.[metrics[1] ?? metrics[0]]
                  return x !== undefined && y !== undefined ? { x, y } : null
                })
                .filter((p): p is { x: number; y: number } => p !== null),
              backgroundColor: CHART_COLORS.primary,
              pointRadius: 5,
            },
          ],
        }
      : empty

  // 热力：资源(y) × 指标(x) 值矩阵
  const heatmapCells: { x: number; y: number; v: number }[] = []
  metrics.forEach((m, mi) => {
    resources.forEach((r, ri) => {
      const v = matrix[r]?.[m]
      if (v !== undefined) heatmapCells.push({ x: mi, y: ri, v })
    })
  })
  const heatmap: ChartSeriesData =
    heatmapCells.length > 0
      ? {
          labels: metrics,
          yLabels: resources,
          datasets: [
            {
              label: '评估维度分布',
              data: heatmapCells,
              backgroundColor: CHART_COLORS.primary,
            },
          ],
        }
      : empty

  return { scatter: scatterPoints, heatmap }
}

/** 统计任务上下文（case-averages 数据源；来自报告列表最近任务报告的 task_id） */
export interface StatisticsTaskContext {
  id: number
  name: string
  type?: string
}

/** 真实数据 → 页面统计形态（纯函数；统计卡四枚 + 维度行 + 趋势/散点/热力） */
export function toReportStatisticsData(input: {
  counts: ReportCounts
  reports: ReportListItem[]
  averages: ReportCaseAveragesData | null
  task?: StatisticsTaskContext | null
  dimension: StatisticDimension
  range: StatisticsTimeRange
  /** case-averages 独立查询加载中（评估指标/设备卡提示「统计加载中」，不再误显示「暂无数据」） */
  averagesLoading?: boolean
}): ReportStatisticsData {
  const { counts, reports, averages, task, dimension, range, averagesLoading } = input
  const totalCases = reports.reduce((acc, r) => acc + (r.summary?.total_cases ?? 0), 0)
  const completed = reports.reduce((acc, r) => acc + (r.summary?.completed_cases ?? 0), 0)
  const failed = reports.reduce((acc, r) => acc + (r.summary?.failed_cases ?? 0), 0)
  const passRate = reports.length
    ? Math.round(reports.reduce((acc, r) => acc + (r.summary?.pass_rate ?? 0), 0) / reports.length)
    : 0
  const metricCount = averages?.overallAverages.length ?? 0
  const deviceCount = averages?.resources.length ?? 0
  /** 任务名（统计上下文；空 = 未选到任务仍在的报告，hint 不拼「任务「」」） */
  const taskName = (task?.name ?? '').trim()

  const summary: StatisticSummaryItem[] = [
    {
      key: 'reports',
      label: '报告数量',
      value: counts.all,
      hint: `草稿 ${counts.draft} · 已发布 ${counts.published} · 对比 ${counts.comparison}`,
    },
    {
      key: 'cases',
      label: '测试用例执行统计',
      value: totalCases,
      hint: `完成 ${completed} · 失败 ${failed} · 通过率 ${passRate}%`,
    },
    {
      key: 'metrics',
      label: '评估指标',
      value: metricCount,
      hint: averages
        ? taskName
          ? `任务「${taskName}」评估指标`
          : '任务评估指标'
        : averagesLoading
          ? '统计加载中…'
          : '暂无任务执行数据',
    },
    {
      key: 'devices',
      label: '设备性能',
      value: deviceCount,
      hint: averages ? `资源 ${deviceCount} 个` : averagesLoading ? '统计加载中…' : '暂无任务执行数据',
    },
  ]

  let rows: StatisticTableRow[]
  switch (dimension) {
    case 'time':
      rows = timeRows(reports, range)
      break
    case 'device_type':
      rows = groupedRows(reports, (r) => r.device_type, DEVICE_TYPE_LABELS)
      break
    case 'metric':
      rows = metricRows(averages)
      break
  }

  const { scatter, heatmap } = buildCharts(averages)

  return {
    summary,
    rows,
    // 异常统计识别：后端无接口 → 空态（「未识别到统计异常」），不虚构判定逻辑
    anomalyRows: [],
    trend: buildTrend(reports),
    scatter,
    heatmap,
    reportIds: reports.map((r) => r.id),
  }
}

/**
 * 统计上下文的候选任务报告（INT-1802）：task_id 有效且任务名非空。
 * 任务被物理删除后其报告的 task_name 为空（报告读模型口径），用已删任务的 task_id 调
 * POST /reports/case-averages 会 400「未找到指定任务」，导致评估指标 / 设备性能整卡空态、
 * 控制台一条 SEVERE；故统计上下文只认任务名非空的最近任务报告。
 */
export function isStatisticsTaskCandidate(report: ReportListItem): boolean {
  return (
    typeof report.task_id === 'number' &&
    report.task_id > 0 &&
    (report.task_name ?? '').trim() !== ''
  )
}

/** 统计基础数据（tab-counts + 报告列表；快表，先出页面） */
async function loadStatisticsBase(): Promise<{
  counts: ReportCounts
  reports: ReportListItem[]
  taskReport: ReportListItem | undefined
}> {
  const [counts, list] = await Promise.all([
    fetchReportCounts(),
    fetchReportList({
      page: 1,
      per_page: 1000,
      sort_by: 'created_at',
      order: 'desc',
      deleted: false,
      favorite: false,
    }),
  ])
  const reports = list.items
  // case-averages 需要任务上下文：取最近一份任务报告关联的 task_id（报告统计语义：
  // 统计该报告任务下的用例平均值；对比/二次对比/benchmark 报告无 task_id → 评估维度空态）
  const taskReport = reports.find(isStatisticsTaskCandidate)
  return { counts, reports, taskReport }
}

/** INT-1547 P2-3：case-averages 可选端点（实测 60s 才 504）独立成查询——
 * 统计卡/维度表格/趋势先出，评估指标与散点·热力随该查询到达后补齐，失败只降级该部分。 */
export function useReportStatistics(
  dimension: StatisticDimension,
  range: StatisticsTimeRange,
  /** 执行序号：点击「执行统计分析」+1 → queryKey 变化 → 重查 */
  seq = 0
) {
  const baseQuery = useQuery({
    queryKey: ['report-statistics', dimension, seq, range.start ?? '', range.end ?? ''],
    queryFn: loadStatisticsBase,
    staleTime: 60_000,
  })

  const taskReport = baseQuery.data?.taskReport
  const task: StatisticsTaskContext | null = taskReport
    ? {
        id: taskReport.task_id as number,
        name: taskReport.task_name,
        type: taskReport.task_type,
      }
    : null

  const averagesQuery = useQuery({
    queryKey: ['report-statistics-averages', task?.id ?? null, seq],
    queryFn: async () => {
      try {
        return await fetchCaseAverages(task!.id)
      } catch {
        // 单端点失败（后端缺口/任务无数据/超时）不拖垮整页：仅评估指标与散点·热力呈空态
        return null
      }
    },
    enabled: task !== null,
    staleTime: 60_000,
  })

  const data = useMemo(() => {
    if (!baseQuery.data) return undefined
    return toReportStatisticsData({
      counts: baseQuery.data.counts,
      reports: baseQuery.data.reports,
      averages: averagesQuery.data ?? null,
      task,
      dimension,
      range,
      averagesLoading: task !== null && averagesQuery.isPending,
    })
  }, [baseQuery.data, averagesQuery.data, averagesQuery.isPending, task, dimension, range])

  return {
    data,
    isLoading: baseQuery.isLoading,
    isError: baseQuery.isError,
    refetch: baseQuery.refetch,
    /** case-averages（评估指标/散点·热力）仍在加载 */
    averagesLoading: task !== null && (averagesQuery.isPending || averagesQuery.isFetching),
  }
}
