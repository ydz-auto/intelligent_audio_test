/**
 * 报告图表 VChart spec 装配（15_报告域.md §3.7）。
 * INT-1273：图表库三套收敛为 Visactor VChart 一套 —— 本文件承担原 chart.js 侧
 * （ReportChart 内联 options 组装 + chartConfig.getDefaultChartConfig）的职责：
 *   bar / line / radar（多资源系列）· distribution（正态分布直方图 + 缩放后重分箱）·
 *   scatter（两变量关系）· heatmap（密度矩阵）· pie / doughnut / polarArea（图例右置）。
 * 配置写法照 features/dashboard/lib/charts.ts 既有 VChart 实现：ThemeManager 主题键、
 * 轴色/网格色由组件按当前深浅色解析传入、色板取自 CSS 语义 token（--chart-1..8）。
 * 数据转换仍留在 application 层（ChartSeriesData 为 camelCase 领域对象），本文件只做
 * 「领域对象 → VChart spec」的呈现层映射。
 */
import type {
  ChartSeriesData,
  DistributionChartData,
} from '@/application/report-view/use-report-charts'
// P2-20：interfaces/呈现层不直 import infrastructure，经 application 层再导出
import {
  CHART_COLORS,
  colorArray,
  rebinDistributionData,
} from '@/application/report-view/use-report-charts'

export type VChartSpec = Record<string, unknown>

/** 报告图表可渲染类型（对位 ChartKind） */
export type ReportChartKind =
  | 'bar'
  | 'line'
  | 'pie'
  | 'doughnut'
  | 'polarArea'
  | 'radar'
  | 'distribution'
  | 'scatter'
  | 'heatmap'

/** 分布图子类型（§3.7 chartSubType） */
export type ReportChartSubKind = 'bar' | 'line'

/** 图表可见主题（组件按当前深浅色 + 预设解析后传入；spec 保持纯对象便于 diff） */
export interface ReportChartVisualTheme {
  /** 类目轴/数值轴文字色 */
  axisLabelColor: string
  /** 网格线色 */
  gridColor: string
  /** 数据集循环色板（--chart-1..8 解析值） */
  palette: string[]
}

/** 分布图分箱区间（重分箱后 x 值域） */
export interface DistributionRange {
  min: number
  max: number
}

/** 一屏 20 个区间（§3.7 重分箱固定档位） */
export const DISTRIBUTION_BIN_COUNT = 20

/** 色板 token（与 src/styles 里 --chart-1..8 语义一致；解析失败时回落到 chartConfig 常量） */
const PALETTE_TOKEN_NAMES = [
  '--chart-1',
  '--chart-2',
  '--chart-3',
  '--chart-4',
  '--chart-5',
  '--chart-6',
  '--chart-7',
  '--chart-8',
] as const

/**
 * 读取当前主题预设的图表色板（多主题预设联动；SSR / 未注入时回落 CHART_COLORS.palette）。
 * canvas 时代只能用 hex 常量，VChart 走 SVG 可直接吃 token 值。
 */
export function resolveChartPalette(): string[] {
  if (typeof document === 'undefined') return [...CHART_COLORS.palette]
  const style = getComputedStyle(document.documentElement)
  return PALETTE_TOKEN_NAMES.map((token, index) => {
    const resolved = style.getPropertyValue(token).trim()
    return resolved || CHART_COLORS.palette[index] || CHART_COLORS.palette[0]
  })
}

/** 兼容旧调用点（报告域 / 统计页仍用 colorArray 取系列色） */
export function seriesColor(index: number): string {
  return colorArray(index)
}

function toNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

/** 共用坐标轴配置（类目轴无网格、数值轴虚线网格，深浅色由 theme 决定） */
function cartesianAxes(theme: ReportChartVisualTheme, options: {
  xType: 'band' | 'linear'
  xTitle?: string
  yTitle?: string
}): Record<string, unknown>[] {
  return [
    {
      orient: 'bottom',
      type: options.xType,
      title: options.xTitle
        ? { visible: true, text: options.xTitle, style: { fill: theme.axisLabelColor, fontSize: 11 } }
        : { visible: false },
      label: {
        style: { fill: theme.axisLabelColor, fontSize: 11 },
        autoHide: true,
        autoLimit: true,
      },
      grid: { visible: false },
      domainLine: { visible: true, style: { stroke: theme.gridColor } },
      tick: { visible: false },
    },
    {
      orient: 'left',
      type: 'linear',
      title: options.yTitle
        ? { visible: true, text: options.yTitle, style: { fill: theme.axisLabelColor, fontSize: 11 } }
        : { visible: false },
      label: { style: { fill: theme.axisLabelColor, fontSize: 11 } },
      grid: { visible: true, style: { stroke: theme.gridColor, lineDash: [3, 3] } },
      domainLine: { visible: false },
      tick: { visible: false },
    },
  ]
}

/** 滚轮/拖拽缩放的 dataZoom（对位 chartjs-plugin-zoom：pan x + wheel/pinch x，无滑块视觉） */
function zoomSpec(): Record<string, unknown> {
  return {
    orient: 'bottom',
    visible: false,
    start: 0,
    end: 1,
    filterMode: 'filter',
    roamZoom: { enable: true, rate: 1.2 },
    roamDrag: { enable: true, reverse: true },
    roamScroll: { enable: false },
    realTime: false,
  }
}

/** 多资源系列 → 长表（x 字段 / seriesField / y 字段），VChart 分组系列的标准形态 */
function toSeriesRows(
  series: ChartSeriesData,
  xField: string,
  yField: string,
  seriesField: string
): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = []
  series.labels.forEach((label, index) => {
    series.datasets.forEach((dataset) => {
      const value = dataset.data[index]
      if (typeof value !== 'number') return
      rows.push({ [xField]: label, [yField]: value, [seriesField]: dataset.label })
    })
  })
  return rows
}

function legendSpec(visible: boolean, orient: 'top' | 'right' = 'top'): Record<string, unknown> {
  return {
    visible,
    orient,
    padding: 0,
    item: { label: { style: { fontSize: 11 } } },
  }
}

/** 分布图：重分箱后的 20 个区间 → 每资源一组的直方图 */
export function buildDistributionValues(
  distribution: DistributionChartData,
  range: DistributionRange
): { labels: string[]; datasets: { label: string; data: number[] }[] } {
  const rebinned = rebinDistributionData(
    distribution.rawData,
    distribution.labels,
    range.min,
    range.max,
    DISTRIBUTION_BIN_COUNT
  )
  return { labels: rebinned.labels, datasets: rebinned.datasets }
}

export interface ReportChartSpecInput {
  kind: ReportChartKind
  title: string
  series: ChartSeriesData
  distribution?: DistributionChartData
  chartSubType: ReportChartSubKind
  xAxisTitle?: string
  enableZoom: boolean
  theme: ReportChartVisualTheme
  chartRadius?: number
  /** distribution 专用：当前展示的值域（缩放重分箱后变化） */
  distributionRange?: DistributionRange
}

/** 分布图值域（默认取统计 min/max，缺省 0~1） */
export function getDistributionRange(distribution?: DistributionChartData): DistributionRange {
  return {
    min: distribution?.stats?.min ?? 0,
    max: distribution?.stats?.max ?? 1,
  }
}

/**
 * 组装 spec。空数据时返回带「暂无数据」标题的空 spec（组件另有空态占位，这里兜底）。
 */
export function buildReportChartSpec(input: ReportChartSpecInput): VChartSpec {
  const { kind, series, distribution, enableZoom, theme, chartRadius } = input
  const radius = chartRadius ?? 4

  if (kind === 'distribution' && distribution) {
    const range = input.distributionRange ?? getDistributionRange(distribution)
    return buildDistributionSpec(distribution, range, input, theme, radius)
  }
  if (kind === 'heatmap') return buildHeatmapSpec(series, theme, radius)
  if (kind === 'scatter') return buildScatterSpec(series, theme, enableZoom)
  if (kind === 'pie' || kind === 'doughnut' || kind === 'polarArea') {
    return buildPieSpec(kind, series, theme, radius)
  }
  if (kind === 'radar') return buildRadarSpec(series, theme)
  // bar / line 共用长表装配
  return buildCartesianSpec(kind === 'line' ? 'line' : 'bar', series, theme, enableZoom, radius)
}

function buildCartesianSpec(
  type: 'bar' | 'line',
  series: ChartSeriesData,
  theme: ReportChartVisualTheme,
  enableZoom: boolean,
  radius: number
): VChartSpec {
  const rows = toSeriesRows(series, '分类', '数值', '系列')
  // VChart 的分组柱靠「多字段 band 轴」判定：xField 同时带类目与系列字段时，
  // 同一类目下的各系列才并排；只关 stack 不够（会画在同一 x 上互相覆盖）。
  const grouped = type === 'bar' && series.datasets.length > 1
  const spec: VChartSpec = {
    type,
    data: [{ id: 'report-series', values: rows }],
    xField: grouped ? ['分类', '系列'] : '分类',
    yField: '数值',
    seriesField: '系列',
    // 改造前 chart.js 多数据集为并排分组柱，VChart bar 默认堆叠，显式关闭
    stack: false,
    color: theme.palette,
    legends: legendSpec(series.datasets.length > 1),
    axes: cartesianAxes(theme, { xType: 'band' }),
    tooltip: { mark: { content: [{ key: (datum: Record<string, unknown>) => datum?.['系列'], value: (datum: Record<string, unknown>) => String(datum?.['数值'] ?? '') }] } },
    background: 'transparent',
    animation: true,
  }
  if (type === 'bar') {
    spec.bar = {
      style: { fillOpacity: 0.7, cornerRadius: radius },
      state: { hover: { stroke: theme.axisLabelColor, lineWidth: 1 } },
    }
  } else {
    spec.line = { style: { lineWidth: 2, curveType: 'monotone' } }
    spec.point = { visible: true, style: { size: 4, fillOpacity: 0.7 } }
  }
  if (enableZoom) spec.dataZoom = [zoomSpec()]
  return spec
}

function buildRadarSpec(series: ChartSeriesData, theme: ReportChartVisualTheme): VChartSpec {
  const rows = toSeriesRows(series, '维度', '数值', '系列')
  return {
    type: 'radar',
    data: [{ id: 'report-radar', values: rows }],
    categoryField: '维度',
    valueField: '数值',
    seriesField: '系列',
    color: theme.palette,
    legends: legendSpec(series.datasets.length > 1),
    axes: [
      {
        orient: 'angle',
        label: { style: { fill: theme.axisLabelColor, fontSize: 11 } },
        grid: { style: { lineDash: [3, 3], stroke: theme.gridColor } },
        domainLine: { visible: false },
      },
      {
        orient: 'radius',
        label: { style: { fill: theme.axisLabelColor, fontSize: 10 } },
        grid: { style: { lineDash: [3, 3], stroke: theme.gridColor } },
        domainLine: { visible: false },
      },
    ],
    area: { visible: true, style: { fillOpacity: 0.2 } },
    line: { style: { lineWidth: 2 } },
    point: { visible: true, style: { size: 4 } },
    background: 'transparent',
    animation: true,
  }
}

function buildDistributionSpec(
  distribution: DistributionChartData,
  range: DistributionRange,
  input: ReportChartSpecInput,
  theme: ReportChartVisualTheme,
  radius: number
): VChartSpec {
  const binned = buildDistributionValues(distribution, range)
  const isLine = input.chartSubType === 'line'
  const rows: Record<string, unknown>[] = []
  binned.labels.forEach((label, index) => {
    binned.datasets.forEach((dataset) => {
      rows.push({ 区间: label, 数量: dataset.data[index] ?? 0, 系列: dataset.label })
    })
  })

  const spec: VChartSpec = {
    type: isLine ? 'line' : 'bar',
    data: [{ id: 'report-distribution', values: rows }],
    // 直方图同样靠多字段 band 轴分组（每资源并排）；折线子类型仍按单字段
    xField: !isLine && binned.datasets.length > 1 ? ['区间', '系列'] : '区间',
    yField: '数量',
    seriesField: '系列',
    // 每资源独立系列并排（同改造前 chart.js 分组柱，不堆叠）
    stack: false,
    color: theme.palette,
    legends: legendSpec(binned.datasets.length > 1),
    axes: cartesianAxes(theme, {
      xType: 'band',
      xTitle: input.xAxisTitle ?? `不同区间的${input.title}`,
      yTitle: '区间内用例数量',
    }),
    // 分布图 tooltip：显 [start, end) 区间 + 「N 个」（§3.7）
    tooltip: {
      dimension: {
        title: {
          value: (datum: Record<string, unknown> | undefined) => {
            const label = String(datum?.['区间'] ?? '')
            const [start, end] = label.split('~')
            return start !== undefined && end !== undefined ? `[${start}, ${end})` : label
          },
        },
        content: [
          {
            key: (datum: Record<string, unknown>) => datum?.['系列'],
            value: (datum: Record<string, unknown>) => `${String(datum?.['数量'] ?? 0)} 个`,
          },
        ],
      },
    },
    background: 'transparent',
    animation: true,
  }
  if (isLine) {
    spec.line = { style: { lineWidth: 2, curveType: 'monotone' } }
    spec.point = { visible: true, style: { size: 3 } }
  } else {
    spec.bar = { style: { fillOpacity: 0.7, cornerRadius: radius } }
  }
  if (input.enableZoom) spec.dataZoom = [zoomSpec()]
  return spec
}

function flattenMatrixCells(series: ChartSeriesData): { x: number; y: number; v: number }[] {
  const cells: { x: number; y: number; v: number }[] = []
  for (const dataset of series.datasets) {
    for (const item of dataset.data) {
      if (typeof item === 'object' && item !== null && 'v' in item) {
        const cell = item as { x: number; y: number; v: number }
        if (Number.isFinite(cell.v)) cells.push(cell)
      }
    }
  }
  return cells
}

/** 色阶（对位 chartjs-chart-matrix 的 alpha 分级色阶：--chart-1..4 逐级加深） */
export function heatmapColorStops(palette: string[]): string[] {
  const primary = palette[0] ?? CHART_COLORS.primary
  const success = palette[2] ?? CHART_COLORS.success
  const warning = palette[3] ?? CHART_COLORS.warning
  const accent = palette[4] ?? CHART_COLORS.purple
  return [
    hexToRgba(primary, 0.18),
    hexToRgba(success, 0.35),
    hexToRgba(warning, 0.6),
    hexToRgba(accent, 0.85),
  ]
}

function hexToRgba(color: string, alpha: number): string {
  const hex = color.trim()
  if (!hex.startsWith('#') || (hex.length !== 7 && hex.length !== 4)) {
    return hex
  }
  const value = hex.length === 4
    ? hex.slice(1).split('').map((c) => c + c).join('')
    : hex.slice(1)
  const r = parseInt(value.slice(0, 2), 16)
  const g = parseInt(value.slice(2, 4), 16)
  const b = parseInt(value.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

function buildHeatmapSpec(
  series: ChartSeriesData,
  theme: ReportChartVisualTheme,
  radius: number
): VChartSpec {
  const yLabels = series.yLabels ?? series.labels
  const cells = flattenMatrixCells(series)
  const values = cells.map((cell) => cell.v)
  const min = values.length ? Math.min(...values) : 0
  const max = values.length ? Math.max(...values) : 1
  const rows = cells.map((cell) => ({
    横轴: series.labels[cell.x] ?? String(cell.x),
    纵轴: yLabels[cell.y] ?? String(cell.y),
    值: cell.v,
  }))

  return {
    type: 'heatmap',
    data: [{ id: 'report-heatmap', values: rows }],
    xField: '横轴',
    yField: '纵轴',
    valueField: '值',
    // 线性色阶：域取当前矩阵值域，range 为 4 档 alpha 分级色
    scales: [
      {
        id: 'color',
        type: 'linear',
        domain: [min, max === min ? min + 1 : max],
        range: heatmapColorStops(theme.palette),
      },
    ],
    legends: legendSpec(false),
    axes: [
      {
        orient: 'bottom',
        type: 'band',
        label: { style: { fill: theme.axisLabelColor, fontSize: 11 }, autoLimit: true },
        grid: { visible: false },
        domainLine: { visible: false },
        tick: { visible: false },
      },
      {
        orient: 'left',
        type: 'band',
        label: { style: { fill: theme.axisLabelColor, fontSize: 11 }, autoLimit: true },
        grid: { visible: false },
        domainLine: { visible: false },
        tick: { visible: false },
      },
    ],
    cell: { style: { cornerRadius: radius > 2 ? 2 : 0 } },
    tooltip: {
      mark: {
        content: [
          {
            key: (datum: Record<string, unknown>) => `${String(datum?.['横轴'] ?? '')} · ${String(datum?.['纵轴'] ?? '')}`,
            value: (datum: Record<string, unknown>) => String(datum?.['值'] ?? 0),
          },
        ],
      },
    },
    background: 'transparent',
    animation: true,
  }
}

function buildScatterSpec(
  series: ChartSeriesData,
  theme: ReportChartVisualTheme,
  enableZoom: boolean
): VChartSpec {
  const rows: Record<string, unknown>[] = []
  for (const dataset of series.datasets) {
    for (const item of dataset.data) {
      if (typeof item === 'object' && item !== null && 'x' in item && 'y' in item) {
        const point = item as { x: number; y: number }
        if (Number.isFinite(point.x) && Number.isFinite(point.y)) {
          rows.push({ x: point.x, y: point.y, 系列: dataset.label })
        }
      }
    }
  }

  const spec: VChartSpec = {
    type: 'scatter',
    data: [{ id: 'report-scatter', values: rows }],
    xField: 'x',
    yField: 'y',
    seriesField: '系列',
    color: theme.palette,
    legends: legendSpec(series.datasets.length > 1),
    axes: cartesianAxes(theme, { xType: 'linear' }),
    point: { style: { size: 5, fillOpacity: 0.85 } },
    tooltip: {
      mark: {
        content: [
          {
            key: (datum: Record<string, unknown>) => datum?.['系列'],
            value: (datum: Record<string, unknown>) =>
              `(${String(datum?.['x'] ?? '')}, ${String(datum?.['y'] ?? '')})`,
          },
        ],
      },
    },
    background: 'transparent',
    animation: true,
  }
  if (enableZoom) spec.dataZoom = [zoomSpec()]
  return spec
}

function buildPieSpec(
  kind: 'pie' | 'doughnut' | 'polarArea',
  series: ChartSeriesData,
  theme: ReportChartVisualTheme,
  radius: number
): VChartSpec {
  const primary = series.datasets[0]
  const rows = series.labels.map((label, index) => ({
    类别: label,
    值: toNumber(primary?.data[index]),
  }))
  if (kind === 'polarArea') {
    // 极区图 = 等角度扇区 + 半径映射值（VChart rose 默认形态）
    return {
      type: 'rose',
      data: [{ id: 'report-polar', values: rows }],
      categoryField: '类别',
      valueField: '值',
      color: theme.palette,
      legends: legendSpec(true, 'right'),
      label: { visible: false },
      background: 'transparent',
      animation: true,
    }
  }
  return {
    type: 'pie',
    data: [{ id: 'report-pie', values: rows }],
    categoryField: '类别',
    valueField: '值',
    color: theme.palette,
    outerRadius: 0.8,
    innerRadius: kind === 'doughnut' ? 0.5 : 0,
    padAngle: 0.6,
    cornerRadius: radius,
    legends: legendSpec(true, 'right'),
    label: { visible: false },
    background: 'transparent',
    animation: true,
  }
}

/** 空数据兜底 spec（组件本身另有「暂无数据」占位，这里保证标题/空态一致） */
export function buildEmptySpec(kind: ReportChartKind): VChartSpec {
  return {
    type: kind === 'polarArea' ? 'rose' : kind === 'heatmap' ? 'heatmap' : kind === 'scatter' ? 'scatter' : 'bar',
    data: [{ id: 'empty', values: [] }],
    title: { visible: true, text: '暂无数据' },
    background: 'transparent',
  }
}

/** 供单元测试/调试用的数据集色（第 i 个系列） */
export function datasetColor(theme: ReportChartVisualTheme, index: number): string {
  return theme.palette[index % theme.palette.length]
}

