/**
 * INT-1273：报告图表 spec 装配回归测试。
 * 重点拦「多系列柱/直方图被画在同一 x 上互相覆盖」——VChart 的分组柱依赖多字段 band 轴
 * （xField 含系列字段），只设 stack:false 不够。
 */
import { describe, expect, it } from 'vitest'

import type {
  ChartSeriesData,
  DistributionChartData,
} from '@/application/report-view/use-report-charts'

import {
  buildReportChartSpec,
  type ReportChartVisualTheme,
} from '../report-chart-spec'

const THEME: ReportChartVisualTheme = {
  axisLabelColor: '#666',
  gridColor: '#eee',
  palette: ['#1', '#2', '#3', '#4'],
}

const SERIES: ChartSeriesData = {
  labels: ['拒识'],
  datasets: [
    { label: '设备A', data: [1] },
    { label: '设备B', data: [0.5] },
  ],
}

function specOf(overrides: {
  kind: Parameters<typeof buildReportChartSpec>[0]['kind']
  series?: ChartSeriesData
  distribution?: DistributionChartData
  chartSubType?: 'bar' | 'line'
}) {
  return buildReportChartSpec({
    kind: overrides.kind,
    title: '指标',
    series: overrides.series ?? SERIES,
    distribution: overrides.distribution,
    chartSubType: overrides.chartSubType ?? 'bar',
    enableZoom: false,
    theme: THEME,
  })
}

const FULL_STATS = {
  count: 5,
  mean: 1,
  stdDev: 0.5,
  min: 0,
  q1: 0.5,
  q2: 1,
  q3: 1.5,
  max: 2,
  positiveRanges: [],
  negativeRanges: [],
}

describe('buildReportChartSpec', () => {
  it('多系列柱状图用多字段 band 轴分组（xField 含系列字段）', () => {
    const spec = specOf({ kind: 'bar' })
    expect(spec.type).toBe('bar')
    expect(spec.xField).toEqual(['分类', '系列'])
    expect(spec.seriesField).toBe('系列')
    expect(spec.stack).toBe(false)
  })

  it('单系列柱状图无需分组（xField 保持单字段）', () => {
    const spec = specOf({
      kind: 'bar',
      series: { labels: ['拒识'], datasets: [{ label: '设备A', data: [1] }] },
    })
    expect(spec.xField).toBe('分类')
  })

  it('折线图按单字段 x 轴（多字段会让每条线各占一组）', () => {
    const spec = specOf({ kind: 'line' })
    expect(spec.type).toBe('line')
    expect(spec.xField).toBe('分类')
  })

  it('正态分布直方图多系列同样分组，且按 20 区间重分箱', () => {
    const distribution: DistributionChartData = {
      rawData: { 设备A: [1, 1.1, 0.9], 设备B: [0.2, 0.3] },
      labels: { 设备A: '设备A', 设备B: '设备B' },
      stats: FULL_STATS,
      deviceStats: [],
    }
    const spec = specOf({ kind: 'distribution', distribution })
    expect(spec.type).toBe('bar')
    expect(spec.xField).toEqual(['区间', '系列'])
    expect(spec.stack).toBe(false)
    const rows = (spec.data as { values: Record<string, unknown>[] }[])[0].values
    const bins = new Set(rows.map((row) => row['区间']))
    expect(bins.size).toBe(20)
  })

  it('正态分布折线子类型保持单字段 x 轴', () => {
    const distribution: DistributionChartData = {
      rawData: { 设备A: [1, 1.1], 设备B: [0.2] },
      labels: { 设备A: '设备A', 设备B: '设备B' },
      stats: FULL_STATS,
      deviceStats: [],
    }
    const spec = specOf({ kind: 'distribution', distribution, chartSubType: 'line' })
    expect(spec.type).toBe('line')
    expect(spec.xField).toBe('区间')
  })

  it('热力图走 heatmap + 值域色阶', () => {
    const spec = specOf({
      kind: 'heatmap',
      series: {
        labels: ['设备A'],
        yLabels: ['维度1'],
        datasets: [{ label: '值', data: [{ x: 0, y: 0, v: 0.8 }] }],
      },
    })
    expect(spec.type).toBe('heatmap')
    expect(spec.xField).toBe('横轴')
    expect(spec.yField).toBe('纵轴')
  })

  it('饼/环形/极区走 pie / rose 单数据集', () => {
    expect(specOf({ kind: 'pie' }).type).toBe('pie')
    expect(specOf({ kind: 'doughnut' }).type).toBe('pie')
    expect(specOf({ kind: 'polarArea' }).type).toBe('rose')
  })
})
