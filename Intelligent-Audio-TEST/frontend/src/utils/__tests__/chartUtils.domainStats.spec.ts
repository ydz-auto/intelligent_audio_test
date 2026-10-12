/**
 * INT-200：图表数据源改为任务域全量聚合（typeCounts / statusCounts / trend 分桶）。
 * 覆盖：三图数据成形、稀疏趋势分桶按时间轴补零（day/week/month）、
 * useTaskCharts 从 taskStats 重建三图。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('chart.js/auto', () => ({ Chart: vi.fn() }))

import { Chart } from 'chart.js/auto'
import { createTaskTypeChart, createTaskTrendChart, createTaskStatusChart } from '../chartUtils'
import { useTaskCharts } from '@/composables/task/useTaskCharts'

const ctx = {} as any
const chartMock = Chart as unknown as ReturnType<typeof vi.fn>

/** 与 chartUtils.getWeekNumber 相同口径的周键（日历年-W ISO 周数，不补零） */
function isoWeekKey(d: Date): string {
  const date = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const dayNum = date.getDay() || 7
  date.setDate(date.getDate() + 4 - dayNum)
  const yearStart = new Date(date.getFullYear(), 0, 1)
  const week = Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
  return `${d.getFullYear()}-W${week}`
}

beforeEach(() => {
  chartMock.mockClear()
})

describe('图表数据成形（INT-200 聚合数据源）', () => {
  it('类型分布图直接消费聚合 typeCounts', () => {
    createTaskTypeChart(ctx, { api: 12, e2e: 8, mixed: 1 })
    const cfg = chartMock.mock.calls[0][1]
    expect(cfg.data.datasets[0].data).toEqual([12, 8, 1])
  })

  it('状态分布图按枚举键读聚合 statusCounts，缺失状态补 0', () => {
    createTaskStatusChart(ctx, { pending: 3, completed: 10 })
    const cfg = chartMock.mock.calls[0][1]
    expect(cfg.data.datasets[0].data).toEqual([3, 0, 0, 10, 0])
  })

  it('趋势图（day）对稀疏分桶按 30 天时间轴补零', () => {
    const today = new Date()
    const d2 = new Date(today)
    d2.setDate(d2.getDate() - 2)
    const keyOf = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    createTaskTrendChart(ctx, [{ key: keyOf(d2), count: 2 }, { key: keyOf(today), count: 5 }], { granularity: 'day' })
    const cfg = chartMock.mock.calls[0][1]
    const labels: string[] = cfg.data.labels
    const data: number[] = cfg.data.datasets[0].data
    expect(labels).toHaveLength(30)
    expect(data[data.length - 1]).toBe(5)  // 今日为最后一格
    expect(data[data.length - 3]).toBe(2)  // 前天
    expect(data[0]).toBe(0)                // 30 天前无数据
  })

  it('趋势图（week/month）后端键与轴键匹配', () => {
    const now = new Date()
    const monthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    createTaskTrendChart(ctx, [{ key: monthKey, count: 7 }], { granularity: 'month' })
    let cfg = chartMock.mock.calls[0][1]
    expect(cfg.data.datasets[0].data).toHaveLength(12)
    expect(cfg.data.datasets[0].data[11]).toBe(7)

    createTaskTrendChart(ctx, [{ key: isoWeekKey(now), count: 9 }], { granularity: 'week' })
    cfg = chartMock.mock.calls[1][1]
    expect(cfg.data.datasets[0].data).toHaveLength(12)
    expect(cfg.data.datasets[0].data[11]).toBe(9)
  })

  it('趋势图非法分桶键不落入时间轴（仅补零）', () => {
    createTaskTrendChart(ctx, [{ key: 'not-a-date-key', count: 99 }], { granularity: 'day' })
    const cfg = chartMock.mock.calls[0][1]
    const data: number[] = cfg.data.datasets[0].data
    expect(data.reduce((a, b) => a + b, 0)).toBe(0)
  })
})

describe('useTaskCharts 从 taskStats 重建三图（INT-200）', () => {
  it('create*Chart 消费 taskStats 数据源', () => {
    const stats = ref({
      total: 25,
      deletedTotal: 4,
      statusCounts: { pending: 3, queued: 2, running: 1, completed: 10, failed: 5 },
      typeCounts: { api: 12, e2e: 8, mixed: 1 },
      trend: [{ key: '2026-10-12', count: 3 }],
      granularity: 'day',
    })
    const charts = useTaskCharts(stats)
    charts.createTaskTypeChart(ctx)
    charts.createTaskTrendChart(ctx, 'day')
    charts.createTaskStatusChart(ctx)
    expect(chartMock.mock.calls).toHaveLength(3)
    // 状态图数据来自 taskStats.statusCounts
    expect(chartMock.mock.calls[2][1].data.datasets[0].data).toEqual([3, 2, 1, 10, 5])
    // 趋势图数据来自 taskStats.trend
    expect(chartMock.mock.calls[1][1].data.datasets[0].data.filter((n: number) => n > 0)).toEqual([3])
  })

  it('taskStats 为空时三图渲染全 0 而不抛错', () => {
    const charts = useTaskCharts(ref(null))
    expect(() => {
      charts.createTaskTypeChart(ctx)
      charts.createTaskTrendChart(ctx, 'day')
      charts.createTaskStatusChart(ctx)
    }).not.toThrow()
    expect(chartMock.mock.calls[0][1].data.datasets[0].data).toEqual([0, 0, 0])
    expect(chartMock.mock.calls[2][1].data.datasets[0].data).toEqual([0, 0, 0, 0, 0])
  })
})
