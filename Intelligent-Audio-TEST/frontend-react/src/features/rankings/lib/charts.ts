/**
 * 排行榜图表 spec（interfaces 层，VChart 指标值横向对比条形图）。
 * 前端派生（数据已存在，不属 §2.4 缺口）：按 rank 升序自上而下；
 * 实测轨 `--chart-1` / 外部轨 `--chart-2` 双色，图例隐藏（行内徽章已区分）；
 * 轴文字/网格色照 14_benchmark排行.md §1.2 实测值（深浅色由组件按当前主题解析传入）。
 */
import type { BenchmarkSource, RankingRow } from '@/domain/models/benchmark'

export type VChartSpec = Record<string, unknown>

export interface MetricBarDatum {
  subject: string
  value: number
  source: BenchmarkSource
  unit: string
  rank: number
}

/** 组内行 → 图表数据（rank 升序，自上而下） */
export function toMetricBarData(rows: RankingRow[]): MetricBarDatum[] {
  const sorted = [...rows].sort((a, b) => a.rank - b.rank)
  return sorted.map((row) => ({
    subject: row.subjectName,
    value: row.metricValue,
    source: row.source,
    unit: row.unit,
    rank: row.rank,
  }))
}

export interface MetricBarChartTheme {
  /** --chart-1 实测轨（hex） */
  chart1: string
  /** --chart-2 外部轨（hex） */
  chart2: string
  /** 类目轴/数值轴文字色 */
  axisLabelColor: string
  /** 网格线色 */
  gridColor: string
}

/** 指标值横向对比条形图 spec（values 为空返回空 spec，组件显示「暂无图表数据」） */
export function buildMetricBarSpec(
  values: MetricBarDatum[],
  theme: MetricBarChartTheme
): VChartSpec {
  if (values.length === 0) {
    return { type: 'bar', data: [{ id: 'metricBar', values: [] }] }
  }

  return {
    type: 'bar',
    direction: 'horizontal',
    data: [
      {
        id: 'metricBar',
        values: values.map((d) => ({
          主体: d.subject,
          指标值: d.value,
          来源: d.source === 'platform_test' ? '平台实测' : '外部基线',
          名次: d.rank,
          unit: d.unit,
        })),
      },
    ],
    xField: '指标值',
    yField: '主体',
    seriesField: '来源',
    color: [theme.chart1, theme.chart2],
    legends: { visible: false },
    label: { visible: false },
    background: 'transparent',
    bar: {
      state: {
        hover: { stroke: '#000', lineWidth: 1 },
      },
    },
    axes: [
      {
        orient: 'left',
        type: 'band',
        tick: { visible: false },
        label: {
          style: {
            fontSize: 12,
            fill: theme.axisLabelColor,
            textAlign: 'right',
          },
          autoHide: true,
          autoLimit: true,
        },
        domainLine: { visible: false },
      },
      {
        orient: 'bottom',
        type: 'linear',
        label: {
          style: { fontSize: 11, fill: theme.axisLabelColor },
          formatMethod: (value: number) => compactAxisValue(value),
        },
        grid: {
          visible: true,
          style: { stroke: theme.gridColor, lineDash: [3, 3] },
        },
        domainLine: { visible: false },
      },
    ],
    tooltip: {
      mark: {
        content: [
          {
            key: (datum: Record<string, unknown>) => datum?.['主体'],
            value: (datum: Record<string, unknown>) => {
              const raw = Number(datum?.['指标值'])
              return `${Number.isFinite(raw) ? String(raw) : '--'}${String(datum?.['unit'] ?? '')}`
            },
          },
          {
            key: '来源',
            value: (datum: Record<string, unknown>) => String(datum?.['来源'] ?? '--'),
          },
          {
            key: '名次',
            value: (datum: Record<string, unknown>) => String(datum?.['名次'] ?? '--'),
          },
        ],
      },
    },
    animation: true,
  }
}

/** 数值轴紧凑显示（≥1000 → 1.2K/3.4M） */
function compactAxisValue(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${trimZeros((value / 1_000_000).toFixed(2))}M`
  if (abs >= 1_000) return `${trimZeros((value / 1_000).toFixed(2))}K`
  return String(value)
}

function trimZeros(text: string): string {
  return text.replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')
}
