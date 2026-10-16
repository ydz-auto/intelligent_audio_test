/**
 * 报告图表数据装配（application 层，15_报告域.md §3.6/3.7）。
 * createCategoryChartData / createTagChartData → generateDistributionChartData 平移：
 *   柱状/折线/雷达：labels=分组|标签，datasets=每资源系列（均值）；
 *   正态分布图：矩阵 _raw 原始值集合 → 每资源直方图 + calculateDistributionStats。
 */
import { useMemo } from 'react'

import type { MetricMatrix } from '@/domain/models/report'
import {
  calculateDistributionStats,
  colorArray,
  type DistributionStats,
} from '@/infrastructure/adapters/chartConfig'
import { readMatrixCell } from './case-matrix'
import type { DisplayType } from './use-case-category-comparison'

export type { DisplayType }

export interface ChartSeriesData {
  labels: string[]
  datasets: { label: string; data: number[]; backgroundColor?: string; borderColor?: string; fill?: boolean; tension?: number }[]
}

export function createGroupChartData(
  matrix: MetricMatrix,
  groups: string[],
  resources: string[],
  metric: string,
  type: DisplayType
): ChartSeriesData {
  const labels = groups
  const datasets = resources.map((resource, i) => {
    const data = groups.map((g) => readMatrixCell(matrix, g, resource, metric).average ?? 0)
    if (type === 'bar') {
      return { label: resource, data, backgroundColor: colorArray(i, 'B3'), borderRadius: 4 }
    }
    if (type === 'line') {
      return { label: resource, data, borderColor: colorArray(i), backgroundColor: colorArray(i, 'B3'), fill: false, tension: 0.3 }
    }
    if (type === 'radar') {
      return { label: resource, data, borderColor: colorArray(i), backgroundColor: `${colorArray(i)}33` }
    }
    return { label: resource, data, backgroundColor: colorArray(i, 'B3') }
  })
  return { labels, datasets }
}

export interface DistributionChartData {
  rawData: Record<string, number[]>
  labels: Record<string, string>
  stats: DistributionStats | null
  deviceStats: { label: string; stats: DistributionStats | null }[]
}

/** 正态分布图数据装配（generateDistributionChartData：_raw 收集 + 去重 + 均值/标准差） */
export function buildDistributionChartData(
  matrix: MetricMatrix,
  groups: string[],
  resources: string[],
  metric: string
): DistributionChartData {
  const deviceRawDataMap: Record<string, number[]> = {}
  const allRaw: number[] = []
  for (const resource of resources) {
    const values: number[] = []
    for (const group of groups) {
      const cell = readMatrixCell(matrix, group, resource, metric)
      for (const v of cell.raw) {
        if (!Number.isFinite(v)) continue
        values.push(v)
      }
    }
    deviceRawDataMap[resource] = values
    for (const v of values) allRaw.push(v)
  }
  return {
    rawData: deviceRawDataMap,
    labels: Object.fromEntries(resources.map((r) => [r, r])),
    stats: calculateDistributionStats(allRaw),
    deviceStats: resources.map((resource) => ({
      label: resource,
      stats: calculateDistributionStats(deviceRawDataMap[resource] ?? []),
    })),
  }
}

export function useReportCharts(
  matrix: MetricMatrix,
  groups: string[],
  resources: string[],
  metric: string,
  type: DisplayType
) {
  const series = useMemo(
    () => createGroupChartData(matrix, groups, resources, metric, type),
    [matrix, groups, resources, metric, type]
  )
  const distribution = useMemo(
    () => buildDistributionChartData(matrix, groups, resources, metric),
    [matrix, groups, resources, metric]
  )
  return { series, distribution }
}
