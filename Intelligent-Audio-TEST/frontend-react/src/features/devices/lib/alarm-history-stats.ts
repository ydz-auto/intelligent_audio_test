/**
 * 历史监控统计分析图表规格（16_设备域.md §3.7：可用性统计/性能统计/错误统计/使用统计；
 * VChart + use-chart-theme，深浅两套随主题）。
 * 数据源：GET /test-devices/monitor-stats 真实聚合（契约 INT-1573，INT-2670 接线）；
 * 指标 null 原样保留为图表断点（无采点日不得补 0）。
 */
import type { DeviceStatsPoint } from '@/domain/models/deviceMonitorStats'
import type { DeviceStatusEventType } from '@/domain/models/alarm'

/** 四类历史事件类别 → eventType 集合（设备管理功能设计文档.md:411-429） */
export const HISTORY_CATEGORY_EVENT_TYPES: Record<
  string,
  ReadonlyArray<DeviceStatusEventType>
> = {
  status: ['online', 'offline', 'connecting', 'disconnecting', 'error'],
  performance: ['health_check'],
  operation: ['operation'],
  error: ['error'],
}

/** 时间范围（§3.7 工具行：今日/近7天/近30天/自定义） */
export type HistoryTimeRange = 'today' | '7d' | '30d' | 'custom'

/** 按时间范围过滤事件（P2-4 返修：时间范围筛选接入 createdAt） */
export function filterByTimeRange(
  createdAt: string | null,
  range: HistoryTimeRange,
  customStart?: string | null,
  customEnd?: string | null
): boolean {
  if (!createdAt) return true
  const time = new Date(createdAt).getTime()
  if (Number.isNaN(time)) return true
  const now = Date.now()
  if (range === 'today') {
    const startOfDay = new Date()
    startOfDay.setHours(0, 0, 0, 0)
    return time >= startOfDay.getTime()
  }
  if (range === '7d') return time >= now - 7 * 24 * 60 * 60 * 1000
  if (range === '30d') return time >= now - 30 * 24 * 60 * 60 * 1000
  if (range === 'custom') {
    const start = customStart ? new Date(customStart).getTime() : null
    const end = customEnd ? new Date(customEnd).getTime() : null
    if (start != null && Number.isFinite(start) && time < start) return false
    if (end != null && Number.isFinite(end) && time > end) return false
    return true
  }
  return true
}

/** 监控统计查询区间（YYYY-MM-DD，含首尾） */
export interface StatsDateRange {
  startDate: string
  endDate: string
}

/** 本地墙钟日期 → YYYY-MM-DD（不用 toISOString：UTC 换算在 UTC+8 晚间会跨日） */
export function toLocalIsoDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * 页面时间范围（今日/近7天/近30天/自定义）→ /monitor-stats 的 start_date / end_date。
 * 今日 = 当天；近7天/近30天按含首尾的自然日计；自定义起止未填全返回 null（不发请求）。
 */
export function resolveStatsDateRange(
  range: HistoryTimeRange,
  customStart?: string | null,
  customEnd?: string | null,
  now: Date = new Date()
): StatsDateRange | null {
  if (range === 'custom') {
    if (!customStart || !customEnd) return null
    return { startDate: customStart, endDate: customEnd }
  }
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const start = new Date(end)
  if (range === '7d') start.setDate(start.getDate() - 6)
  else if (range === '30d') start.setDate(start.getDate() - 29)
  return { startDate: toLocalIsoDate(start), endDate: toLocalIsoDate(end) }
}

/** 是否有真实采点：全 null 且无错误/操作 → 空态「暂无监控采点」，不用示例曲线充数 */
export function hasMonitorStatsData(points: DeviceStatsPoint[]): boolean {
  return points.some(
    (point) =>
      point.availability != null ||
      point.cpu != null ||
      point.memory != null ||
      point.battery != null ||
      point.errors > 0 ||
      point.operations > 0
  )
}

/**
 * 单日范围只有 1 个采点，线/面积没有可连的走向，必须用点标记把当日数值画出来；
 * 多日范围保持无点标记，避免密集点噪点。
 */
function singlePointVisible(points: DeviceStatsPoint[]): boolean {
  return points.length <= 1
}

/** 可用性统计趋势（面积图） */
export function buildAvailabilitySpec(points: DeviceStatsPoint[]): Record<string, unknown> {
  return {
    type: 'area',
    data: {
      values: points.map((p) => ({ date: p.date, 可用率: p.availability })),
    },
    xField: 'date',
    yField: '可用率',
    area: { style: { fill: { type: 'linear', gradient: 'x1', stops: [{ color: '#00d294' }, { color: 'rgba(0,210,148,0.1)' }] } } },
    line: { style: { stroke: '#00d294', lineWidth: 2 } },
    point: { visible: singlePointVisible(points), style: { fill: '#00d294' } },
    axes: [
      { orient: 'left', label: { formatMethod: (v: number) => `${v}%` } },
      { orient: 'bottom', tick: { visible: false } },
    ],
    height: 168,
  }
}

/** 性能统计趋势（CPU/内存/电量多线） */
export function buildPerformanceSpec(points: DeviceStatsPoint[]): Record<string, unknown> {
  return {
    type: 'line',
    data: {
      values: points.flatMap((p) => [
        { date: p.date, 指标: 'CPU', 值: p.cpu },
        { date: p.date, 指标: '内存', 值: p.memory },
        { date: p.date, 指标: '电量', 值: p.battery },
      ]),
    },
    xField: 'date',
    yField: '值',
    seriesField: '指标',
    line: { style: { lineWidth: 2 } },
    point: { visible: singlePointVisible(points) },
    axes: [{ orient: 'bottom', tick: { visible: false } }],
    height: 168,
  }
}

/** 错误统计柱状 */
export function buildErrorSpec(points: DeviceStatsPoint[]): Record<string, unknown> {
  return {
    type: 'bar',
    data: {
      values: points.map((p) => ({ date: p.date, 错误次数: p.errors })),
    },
    xField: 'date',
    yField: '错误次数',
    bar: { style: { fill: '#f04137' } },
    axes: [{ orient: 'bottom', tick: { visible: false } }],
    height: 168,
  }
}

/** 使用统计柱状（操作/测试次数） */
export function buildUsageSpec(points: DeviceStatsPoint[]): Record<string, unknown> {
  return {
    type: 'bar',
    data: {
      values: points.map((p) => ({ date: p.date, 操作次数: p.operations })),
    },
    xField: 'date',
    yField: '操作次数',
    bar: { style: { fill: '#138187' } },
    axes: [{ orient: 'bottom', tick: { visible: false } }],
    height: 168,
  }
}
