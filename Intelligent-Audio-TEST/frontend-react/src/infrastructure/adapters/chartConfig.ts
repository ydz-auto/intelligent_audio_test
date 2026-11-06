/**
 * 图表数据适配（infrastructure/adapters 层，INT-439 报告域图表引擎裁定；INT-1273 收敛到 VChart）。
 * 照现前端 frontend/src/chart/utils/chartConfig.ts 平移：CHART_COLORS 用与 tokens.css
 * 等价的 hex 常量（token 解析失败时的回落值）；calculateDistributionStats/rebinDistributionData
 * 照 shared/useReportShared.ts generateDistributionChartData 平移（15_报告域.md §3.7）。
 * INT-1273：chart.js 四件套（chart.js / chartjs-chart-matrix / chartjs-plugin-zoom）移除，
 * 本文件只保留与图表引擎无关的数据口径（色板、分布统计、重分箱、轴色）；渲染 spec 见
 * components/common/report-chart/report-chart-spec.ts。
 */

/** 图表语义色常量（照现前端 chartConfig.ts:11-18 实测值；与 tokens.css --chart-1..5 等价映射） */
export const CHART_COLORS = {
  primary: '#1976D2',
  secondary: '#FF6A00',
  success: '#52C41A',
  warning: '#FFA940',
  info: '#1976D2',
  purple: '#F5222D',
  /** 数据集循环色板 */
  palette: ['#1976D2', '#FF6A00', '#52C41A', '#FFA940', '#F5222D', '#13C2C2', '#722ED1', '#2F54EB'],
} as const

/** 数据集色循环 + bar/line 加 alpha 'B3'（照现前端 colorArray 实测） */
export function colorArray(index: number, alpha?: string): string {
  const base = CHART_COLORS.palette[index % CHART_COLORS.palette.length]
  return alpha ? `${base}${alpha}` : base
}

export interface DistributionStats {
  count: number
  mean: number
  stdDev: number
  min: number
  q1: number
  q2: number
  q3: number
  max: number
  /** 正方向区间百分比 [0,μ) / (μ,μ+σ] / (μ+σ,μ+2σ] / (μ+2σ,μ+3σ] / 超出+(μ+3σ) */
  positiveRanges: { label: string; percent: number }[]
  /** 负方向区间（有负值时） */
  negativeRanges: { label: string; percent: number }[]
}

/** 四分位数（照现前端 calculateDistributionStats 实测） */
function quantile(values: number[], q: number): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const pos = (sorted.length - 1) * q
  const base = Math.floor(pos)
  const rest = pos - base
  if (sorted[base + 1] !== undefined) {
    return sorted[base] + rest * (sorted[base + 1] - sorted[base])
  }
  return sorted[base]
}

/** 均值/标准差/区间统计（照 shared/useReportShared.ts calculateNormalDistribution + calculateDistributionStats） */
export function calculateDistributionStats(values: number[]): DistributionStats | null {
  const numeric = values.filter((v) => Number.isFinite(v))
  if (numeric.length === 0) return null
  const mean = numeric.reduce((s, v) => s + v, 0) / numeric.length
  const variance =
    numeric.reduce((s, v) => s + (v - mean) ** 2, 0) / numeric.length
  const stdDev = Math.sqrt(variance)
  const min = Math.min(...numeric)
  const max = Math.max(...numeric)

  const positiveRanges = [
    { label: '[0, μ)', percent: 0 },
    { label: '(μ, μ+σ]', percent: 0 },
    { label: '(μ+σ, μ+2σ]', percent: 0 },
    { label: '(μ+2σ, μ+3σ]', percent: 0 },
    { label: `超出+(μ+3σ)`, percent: 0 },
  ]
  for (const v of numeric) {
    if (v < mean) positiveRanges[0].percent += 1
    else if (v <= mean + stdDev) positiveRanges[1].percent += 1
    else if (v <= mean + 2 * stdDev) positiveRanges[2].percent += 1
    else if (v <= mean + 3 * stdDev) positiveRanges[3].percent += 1
    else positiveRanges[4].percent += 1
  }

  const negativeRanges = [
    { label: '[-μ, 0)', percent: 0 },
    { label: '[-(μ+σ), -μ)', percent: 0 },
    { label: '[-(μ+2σ), -(μ+σ))', percent: 0 },
    { label: `[-(μ+3σ), -(μ+2σ))`, percent: 0 },
    { label: `超出-(μ+3σ)`, percent: 0 },
  ]
  for (const v of numeric) {
    if (v >= 0) continue
    const abs = Math.abs(v)
    if (abs < mean) negativeRanges[0].percent += 1
    else if (abs < mean + stdDev) negativeRanges[1].percent += 1
    else if (abs < mean + 2 * stdDev) negativeRanges[2].percent += 1
    else if (abs < mean + 3 * stdDev) negativeRanges[3].percent += 1
    else negativeRanges[4].percent += 1
  }

  const toPercent = (r: { label: string; percent: number }[]) =>
    r.map((x) => ({ ...x, percent: numeric.length ? (x.percent / numeric.length) * 100 : 0 }))

  return {
    count: numeric.length,
    mean,
    stdDev,
    min,
    q1: quantile(numeric, 0.25),
    q2: quantile(numeric, 0.5),
    q3: quantile(numeric, 0.75),
    max,
    positiveRanges: toPercent(positiveRanges),
    negativeRanges: toPercent(negativeRanges),
  }
}

export interface RebinResult {
  labels: string[]
  datasets: { label: string; data: number[]; backgroundColor?: string; borderColor?: string }[]
  /** 区间步长 */
  step: number
}

/** zoom/pan 后重分箱：固定 20 区间按可见范围重计 → 更新 datasets + 固定 x min/max（照 rebinDistributionData） */
export function rebinDistributionData(
  rawData: Record<string, number[]>,
  labels: Record<string, string>,
  min: number,
  max: number,
  intervals = 20
): RebinResult {
  const step = (max - min) / intervals || 1
  const allKeys = Object.keys(rawData)
  const buckets: Record<string, number[]> = {}
  for (const key of allKeys) {
    const counts = new Array(intervals).fill(0)
    for (const v of rawData[key]) {
      if (v < min || v > max) continue
      let idx = Math.floor((v - min) / step)
      if (idx >= intervals) idx = intervals - 1
      counts[idx] += 1
    }
    buckets[key] = counts
  }
  const outLabels = Array.from({ length: intervals }, (_, i) => {
    const start = min + i * step
    const end = start + step
    return `${start.toFixed(1)}~${end.toFixed(1)}`
  })
  return {
    labels: outLabels,
    datasets: allKeys.map((key, i) => ({
      label: labels[key] ?? key,
      data: buckets[key],
      backgroundColor: colorArray(i, 'B3'),
      borderColor: colorArray(i),
    })),
    step,
  }
}

/** 图表轴色/网格色（深浅两套；INT-596 P3 起集中在此，供报告图表 / 排行区块等共用，消除 rgba 魔数重复） */
export function getChartAxisColors(isDark: boolean): { gridColor: string; tickColor: string } {
  return {
    gridColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)',
    tickColor: isDark ? 'rgba(255,255,255,0.65)' : 'rgba(0,0,0,0.55)',
  }
}
