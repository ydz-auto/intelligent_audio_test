/**
 * 报告查看图表数据装配 + VChart spec（application 层；规范 §4.5）。
 * 图表引擎=VChart（@visactor/react-vchart），主题适配照 newAPI model-details-charts：
 * getChartThemeTokens 深浅文本/网格色 + background:'transparent'；series 配色走语义 token
 * --chart-1..5（随主题预设联动，lake-view 默认），useThemePresetKey 变化整图重建。
 */
import type {
  ReportDetailData,
  ReportMetricDataGroup,
} from '@/domain/models/report'

export function getChartThemeTokens(resolvedTheme: string): {
  textColor: string
  gridColor: string
} {
  return resolvedTheme === 'dark'
    ? { textColor: 'rgba(255,255,255,0.68)', gridColor: 'rgba(255,255,255,0.12)' }
    : { textColor: 'rgba(15,23,42,0.58)', gridColor: 'rgba(15,23,42,0.12)' }
}

/** 读取语义 token 图表色板（--chart-1..5，随预设联动；缺省回退 lake-view 基座色） */
export function resolveChartColors(count: number): string[] {
  const fallback = ['#00d294', '#138187', '#5ee9b5', '#5de9e5', '#d0fae5']
  if (typeof document === 'undefined') return fallback.slice(0, count)
  const styles = getComputedStyle(document.documentElement)
  const resolved: string[] = []
  for (let i = 1; i <= Math.max(count, 5); i++) {
    const value = styles.getPropertyValue(`--chart-${i}`).trim()
    resolved.push(value || fallback[i - 1] || '#00d294')
  }
  return resolved.slice(0, count)
}

export type ChartSpec = Record<string, unknown>

/**
 * 指标对比柱状图（各资源 × 指标均值分组柱；Tooltip 中文键值）。
 * 空数据 → 占位 title（页面级占位卡另行渲染，这里返回 null）。
 */
export function buildMetricBarSpec(
  metricData: ReportMetricDataGroup[],
  resources: string[],
  options: { chartRadius?: number; colors: string[]; textColor: string; gridColor: string }
): ChartSpec | null {
  const values = metricData.flatMap((group) =>
    group.metrics.map((m) => ({
      Metric: m.metric,
      Resource: group.resource,
      Value: Number(m.value.toFixed(2)),
    }))
  )
  if (values.length === 0) return null
  return {
    type: 'bar',
    data: [{ id: 'metricData', values }],
    xField: 'Metric',
    yField: 'Value',
    seriesField: 'Resource',
    color: { type: 'ordinal', domain: resources, range: options.colors },
    legends: { visible: true, orient: 'top' },
    label: { visible: false },
    bar: {
      style:
        options.chartRadius == null ? {} : { cornerRadius: options.chartRadius },
      state: { hover: { stroke: '#000', lineWidth: 1 } },
    },
    axes: [
      { orient: 'left', label: { fill: options.textColor, fontSize: 10 }, grid: { lineDash: [3, 3], stroke: options.gridColor } },
      { orient: 'bottom', label: { fill: options.textColor, fontSize: 10 } },
    ],
    tooltip: { mark: { content: [{ key: '指标', value: 'Metric' }, { key: '资源', value: 'Resource' }, { key: '值', value: (d: Record<string, unknown>) => `${Number(d.Value ?? 0).toFixed(2)}` }] } },
    animation: true,
  }
}

/**
 * 通过率/成功率趋势折线（line + smooth + point）：device_stats.success_rate × 资源；
 * 对比报告=各任务通过率（resources=task ids）。
 */
export function buildPassRateTrendSpec(
  metricData: ReportMetricDataGroup[],
  options: { colors: string[]; textColor: string; gridColor: string }
): ChartSpec | null {
  // 取每资源的「通过率/成功率」维度（metric 名含 通过率/成功 优先，否则取首个指标）
  const values = metricData
    .map((group) => {
      const rateMetric = group.metrics.find(
        (m) => m.metric.includes('通过率') || m.metric.includes('成功')
      )
      return {
        Resource: group.resource,
        Rate: Number((rateMetric ?? group.metrics[0])?.value.toFixed(2) ?? 0),
      }
    })
    .filter((item) => Number.isFinite(item.Rate))
  if (values.length === 0) return null
  return {
    type: 'line',
    data: [{ id: 'rateTrend', values }],
    xField: 'Resource',
    yField: 'Rate',
    seriesField: 'Resource',
    smooth: true,
    point: { visible: true, style: { size: 5, stroke: '#ffffff', lineWidth: 1.5 } },
    line: { style: { lineWidth: 2 } },
    color: { type: 'ordinal', domain: values.map((v) => v.Resource), range: options.colors },
    legends: { visible: false },
    axes: [
      { orient: 'left', label: { fill: options.textColor, fontSize: 10 }, grid: { lineDash: [3, 3], stroke: options.gridColor } },
      { orient: 'bottom', label: { fill: options.textColor, fontSize: 10 }, tick: { visible: false } },
    ],
    tooltip: { mark: { content: [{ key: '资源', value: 'Resource' }, { key: '通过率', value: (d: Record<string, unknown>) => `${Number(d.Rate ?? 0).toFixed(1)}%` }] } },
    animation: true,
  }
}

/**
 * 多维对比雷达图（评估维度 × 资源；维度值归一化百分比）。
 */
export function buildRadarSpec(
  metricData: ReportMetricDataGroup[],
  options: { colors: string[]; textColor: string; gridColor: string }
): ChartSpec | null {
  if (metricData.length === 0) return null
  const metrics = Array.from(
    new Set(metricData.flatMap((g) => g.metrics.map((m) => m.metric)))
  )
  // 归一化：每维度按各资源最大值为 100%
  const maxByMetric: Record<string, number> = {}
  for (const group of metricData) {
    for (const m of group.metrics) {
      maxByMetric[m.metric] = Math.max(maxByMetric[m.metric] ?? 0, m.value)
    }
  }
  const series = metricData.map((group) => ({
    resource: group.resource,
    values: metrics.map((metric) => {
      const m = group.metrics.find((x) => x.metric === metric)
      const max = maxByMetric[metric] ?? 1
      return {
        metric,
        value: max > 0 ? Number(((m?.value ?? 0) / max) * 100).toFixed(1) : 0,
      }
    }),
  }))
  const data = series.flatMap((s) =>
    s.values.map((v) => ({ Resource: s.resource, Metric: v.metric, Value: Number(v.value) }))
  )
  return {
    type: 'radar',
    data: [{ id: 'radarData', values: data }],
    categoryField: 'Metric',
    valueField: 'Value',
    seriesField: 'Resource',
    color: { type: 'ordinal', domain: series.map((s) => s.resource), range: options.colors },
    legends: { visible: true, orient: 'top' },
    axes: [
      { orient: 'angle', label: { fill: options.textColor, fontSize: 10 } },
      { orient: 'radius', label: { fill: options.textColor, fontSize: 10 }, grid: { lineDash: [3, 3], stroke: options.gridColor } },
    ],
    tooltip: { mark: { content: [{ key: '指标', value: 'Metric' }, { key: '资源', value: 'Resource' }, { key: '归一化', value: (d: Record<string, unknown>) => `${Number(d.Value ?? 0).toFixed(1)}%` }] } },
    animation: true,
  }
}

export function isEmptyChartData(metricData: ReportMetricDataGroup[]): boolean {
  return metricData.every((g) => g.metrics.length === 0)
}

/** 图例显隐（≤6 显，>6 折叠为 Tooltip 切换） */
export function shouldShowLegend(resourceCount: number): boolean {
  return resourceCount <= 6
}

export type { ReportDetailData }
