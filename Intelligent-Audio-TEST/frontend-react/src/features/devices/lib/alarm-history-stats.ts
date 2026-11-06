/**
 * 历史监控统计分析图表规格（16_设备域.md §3.7：可用性统计/性能统计/错误统计/使用统计；
 * VChart + use-chart-theme，深浅两套随主题）。
 * 数据源 mock 日粒度采点（devices-mock MOCK_DEVICE_STATS），接线后换实时监控指标端点。
 */
import type { DeviceStatsPoint } from '@/infrastructure/mock/devices-mock'
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
    point: { visible: false },
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
    point: { visible: false },
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
