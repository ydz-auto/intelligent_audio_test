/*
Copyright (C) 2023-2026 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/
/**
 * 任务统计图表 spec（移植自 newAPI web/src/features/dashboard/lib/charts.ts 图表机制）：
 * getDashboardChartColors 按 VChart 内置 dataScheme 分档取色板；
 * 饼图 outerRadius 0.8 / innerRadius 0.5 / padAngle 0.6 + hover 0.85 + cornerRadius=--radius-md；
 * 面积图 fillOpacity 0.08 + monotone + point hidden；空数据空 spec（title subtext「暂无数据」）。
 * （newAPI 的配额换算/模型聚合等 LLM 业务逻辑不引入——04_控制台.md §8）
 */
import { dataScheme as vchartDefaultDataScheme } from '@visactor/vchart/esm/theme/color-scheme/builtin/default'

import type { TrendPoint } from '@/domain/models/stats'

export type VChartSpec = Record<string, unknown>

export function getDashboardChartColors(domainLength: number): string[] {
  const scheme =
    vchartDefaultDataScheme.find(
      (item) => !item.maxDomainLength || domainLength <= item.maxDomainLength
    ) ?? vchartDefaultDataScheme.at(-1)

  return (scheme?.scheme ?? []).filter(
    (color): color is string => typeof color === 'string'
  )
}

function formatInt(value: number): string {
  return Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(
    value
  )
}

function ordinalColor(domain: string[]) {
  return {
    type: 'ordinal' as const,
    domain,
    range: getDashboardChartColors(domain.length),
  }
}

const EMPTY_TITLE = {
  visible: true,
  text: '暂无数据',
}

export interface TrendTrendSpecOptions {
  variant: 'bar' | 'area'
  chartRadius?: number
}

/** 任务完成趋势：单系列柱状图/面积图（单系列不用 ordinal 多色，取色板首位） */
export function buildTrendSpec(
  trend: TrendPoint[],
  options: TrendTrendSpecOptions
): VChartSpec {
  const values = trend.map((point) => ({
    Time: point.key,
    Count: point.count,
  }))

  if (values.length === 0) {
    return {
      type: options.variant,
      data: [{ id: 'trendData', values: [] }],
      xField: 'Time',
      yField: 'Count',
      legends: { visible: false },
      label: { visible: false },
      title: { ...EMPTY_TITLE, subtext: '完成任务后这里会显示趋势' },
      animation: true,
    }
  }

  const total = values.reduce((sum, item) => sum + item.Count, 0)
  const tooltipAggregation = {
    dimension: {
      content: [
        {
          key: (datum: Record<string, unknown>) => datum?.Time,
          value: (datum: Record<string, unknown>) =>
            formatInt(Number(datum?.Count) || 0),
        },
      ],
      updateContent: (array: Array<Record<string, unknown>>) => {
        const lines: Array<Record<string, unknown>> = array.map((item) => ({
          ...item,
          value: formatInt(Number(item.value) || 0),
        }))
        lines.unshift({ key: '总计：', value: formatInt(total), hasShape: false })
        return lines
      },
    },
  }

  if (options.variant === 'area') {
    return {
      type: 'area',
      data: [{ id: 'trendData', values }],
      xField: 'Time',
      yField: 'Count',
      color: getDashboardChartColors(1)[0],
      legends: { visible: false },
      area: {
        style: {
          fillOpacity: 0.08,
          curveType: 'monotone',
        },
      },
      line: {
        style: {
          lineWidth: 2,
          curveType: 'monotone',
        },
      },
      point: { visible: false },
      tooltip: tooltipAggregation,
      animation: true,
    }
  }

  return {
    type: 'bar',
    data: [{ id: 'trendData', values }],
    xField: 'Time',
    yField: 'Count',
    color: getDashboardChartColors(1)[0],
    legends: { visible: false },
    bar: {
      state: {
        hover: { stroke: '#000', lineWidth: 1 },
      },
    },
    tooltip: tooltipAggregation,
    animation: true,
  }
}

export interface DistributionPieSpecOptions {
  chartRadius?: number
}

export interface PieDatum {
  type: string
  value: number
}

/** 分布饼图（任务状态分布等；键为后端原值，中文映射在 constants.ts 完成后再传入） */
export function buildDistributionPieSpec(
  values: PieDatum[],
  options: DistributionPieSpecOptions
): VChartSpec {
  if (values.length === 0) {
    return {
      type: 'pie',
      data: [{ id: 'id0', values: [] }],
      outerRadius: 0.8,
      innerRadius: 0.5,
      padAngle: 0.6,
      valueField: 'value',
      categoryField: 'type',
      title: { ...EMPTY_TITLE, subtext: '暂无可统计的分布数据' },
      legends: { visible: false },
      label: { visible: false },
      tooltip: { mark: { content: [] } },
      animation: true,
    }
  }

  const domain = values.map((item) => item.type)

  return {
    type: 'pie',
    data: [{ id: 'id0', values }],
    outerRadius: 0.8,
    innerRadius: 0.5,
    padAngle: 0.6,
    valueField: 'value',
    categoryField: 'type',
    pie: {
      style:
        options.chartRadius == null
          ? {}
          : { cornerRadius: options.chartRadius },
      state: {
        hover: { outerRadius: 0.85, stroke: '#000', lineWidth: 1 },
        selected: { outerRadius: 0.85, stroke: '#000', lineWidth: 1 },
      },
    },
    // 注记：newAPI 填充态饼图含内嵌 title；本页卡头已带同义标题，关闭内嵌 title 避免重复
    title: { visible: false },
    legends: { visible: true, orient: 'left', selectMode: 'single' },
    label: { visible: true },
    color: ordinalColor(domain),
    tooltip: {
      mark: {
        content: [
          {
            key: (datum: Record<string, unknown>) => datum?.type,
            value: (datum: Record<string, unknown>) =>
              formatInt(Number(datum?.value) || 0),
          },
        ],
      },
    },
    animation: true,
  }
}
