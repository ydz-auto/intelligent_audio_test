/**
 * ChartComponent 对位（15_报告域.md §3.7：报告图表 + 缩放）。
 * props: title/data(labels+datasets)/type(bar|line|radar|distribution|scatter|heatmap|pie/doughnut/polarArea)/
 *         showHeader/showActions/loading/stats/enableZoom/height；chartReady/export 事件。
 * distribution 模式：x 轴「不同区间的{title}」、y 轴「区间内用例数量」、
 * 折线图/直方图子类型切换（chartSubType）+ zoom/pan 后固定 20 区间按可见范围重分箱
 * （rebinDistributionData）+ resetZoom 恢复原始。
 * INT-1273：图表引擎由 chart.js v4（+ matrix / zoom 插件）换成 Visactor VChart 一套，
 * 与 dashboard / devices / rankings / spl-mapping 同库；spec 装配见 ./report-chart-spec。
 * 深浅色/多主题走 ThemeManager + CSS 语义 token（轴色/网格色/--chart-1..8 色板）。
 * INT-430 前置条件：本组件为共享平台件，驻留 components/common/report-chart（dashboard/benchmark 复用）。
 */
import { VChart } from '@visactor/react-vchart'
import type { ISpec, IVChart } from '@visactor/vchart'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import type {
  ChartSeriesData,
  DistributionChartData,
} from '@/application/report-view/use-report-charts'
import { getChartAxisColors } from '@/application/report-view/use-report-charts'
import {
  useChartTheme,
  useThemePresetKey,
  useThemeRadiusPx,
  VCHART_OPTION,
} from '@/features/dashboard/lib/vchart'
import { cn } from '@/lib/utils'

import { ChartActions } from './chart-actions'
import { ChartStatsCard } from './chart-stats-card'
import {
  buildEmptySpec,
  buildReportChartSpec,
  getDistributionRange,
  resolveChartPalette,
  type DistributionRange,
  type ReportChartKind,
  type ReportChartSubKind,
  type ReportChartVisualTheme,
} from './report-chart-spec'

export type ChartKind = ReportChartKind
export type ChartSubKind = ReportChartSubKind

/**
 * 重分箱判定阈值：可见窗口与当前值域的差小于该比例时不再重算（避免机械抖动）。
 * 与 §3.7 的「按可见范围重分箱」同口径，纯交互节流参数。
 */
const REBIN_EPSILON = 0.01
/** 缩放停止后多久重分箱（对位 chartjs-plugin-zoom 的 onZoomComplete 时点） */
const REBIN_DELAY_MS = 260

interface ReportChartProps {
  title: string
  subtitle?: string
  type: ChartKind
  series: ChartSeriesData
  distribution?: DistributionChartData
  height?: number
  enableZoom?: boolean
  loading?: boolean
  className?: string
  /** distribution 模式 x 轴标题（默认「不同区间的{title}」；分布图卡片标题独立传 title） */
  xAxisTitle?: string
}

export function ReportChart({
  title,
  subtitle,
  type,
  series,
  distribution,
  height = 320,
  enableZoom = true,
  loading,
  className,
  xAxisTitle,
}: ReportChartProps) {
  const chartRef = useRef<IVChart | null>(null)
  const { themeReady, themeKey, resolvedTheme } = useChartTheme()
  const presetKey = useThemePresetKey()
  const chartRadius = useThemeRadiusPx()
  // 分布图子类型：折线图/直方图（§3.7 chartSubType）
  const [chartSubType, setChartSubType] = useState<ChartSubKind>('bar')
  // 缩放后重分箱的值域；null = 原始全量区间
  const [distributionRange, setDistributionRange] = useState<DistributionRange | null>(null)
  // 重置缩放：换 key 整图重建（与 dashboard 图表同款重建机制，dataZoom 状态随之归零）
  const [resetNonce, setResetNonce] = useState(0)
  const rebinTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const isDark = resolvedTheme === 'dark'

  const theme = useMemo<ReportChartVisualTheme>(() => {
    const axisColors = getChartAxisColors(isDark)
    return {
      axisLabelColor: axisColors.tickColor,
      gridColor: axisColors.gridColor,
      palette: resolveChartPalette(),
    }
    // 预设切换会改写 --chart-* token，需随 presetKey 重算
  }, [isDark, presetKey])

  /** 空数据态（§3.7「暂无数据」：distribution 看 rawData，其余看 datasets 是否有数据） */
  const hasData = useMemo(() => {
    if (type === 'distribution') {
      return Boolean(distribution && Object.keys(distribution.rawData ?? {}).length > 0)
    }
    return series.datasets.some((d) => d.data.length > 0)
  }, [type, series, distribution])

  // 数据/类型变化回到全量区间（重分箱窗口属于上一次数据，不跨数据复用）
  useEffect(() => {
    setDistributionRange(null)
  }, [type, distribution, series, chartSubType])

  const fullRange = useMemo(() => getDistributionRange(distribution), [distribution])
  const activeRange = distributionRange ?? fullRange

  const spec = useMemo(() => {
    if (!hasData) return buildEmptySpec(type)
    return buildReportChartSpec({
      kind: type,
      title,
      series,
      distribution,
      chartSubType,
      xAxisTitle,
      enableZoom,
      theme,
      chartRadius,
      distributionRange: activeRange,
    })
  }, [
    hasData,
    type,
    title,
    series,
    distribution,
    chartSubType,
    xAxisTitle,
    enableZoom,
    theme,
    chartRadius,
    activeRange,
  ])

  useEffect(() => () => {
    if (rebinTimer.current) clearTimeout(rebinTimer.current)
  }, [])

  /**
   * zoom/pan 后按可见范围重分箱（§3.7）：dataZoom 的百分比区间映射回值域，
   * 固定 20 区间重算后以新值域整图重建（x 域即当前可见窗口）。
   */
  const handleDataZoomChange = useCallback(
    (event: { value?: { start?: number; end?: number } }) => {
      if (type !== 'distribution' || !distribution) return
      const start = event?.value?.start
      const end = event?.value?.end
      if (typeof start !== 'number' || typeof end !== 'number') return
      if (end - start <= 0) return
      const span = activeRange.max - activeRange.min
      if (!Number.isFinite(span) || span <= 0) return
      const nextMin = activeRange.min + start * span
      const nextMax = activeRange.min + end * span
      const windowRatio = (nextMax - nextMin) / span
      if (windowRatio >= 1 - REBIN_EPSILON) return
      if (rebinTimer.current) clearTimeout(rebinTimer.current)
      rebinTimer.current = setTimeout(() => {
        setDistributionRange({ min: nextMin, max: nextMax })
      }, REBIN_DELAY_MS)
    },
    [type, distribution, activeRange]
  )

  const handleResetZoom = () => {
    setDistributionRange(null)
    setResetNonce((value) => value + 1)
  }

  const handleExportPng = async () => {
    const chart = chartRef.current
    if (!chart) return
    const dataUrl = await chart.getDataURL()
    if (!dataUrl) return
    const link = document.createElement('a')
    link.download = `${title}.png`
    link.href = dataUrl
    link.click()
  }

  const isDistribution = type === 'distribution'
  const rangeKey = `${activeRange.min.toFixed(3)}~${activeRange.max.toFixed(3)}`

  return (
    <div className={cn('bg-card rounded-2xl border shadow-xs p-4', className)}>
      <div className='flex items-start justify-between gap-2'>
        <div>
          <h4 className='text-sm font-semibold'>{title}</h4>
          {subtitle && (
            <p className='text-muted-foreground text-xs'>{subtitle}</p>
          )}
        </div>
        <div className='flex flex-wrap items-center gap-1.5'>
          {isDistribution && (
            <div role='group' aria-label='图表子类型' className='bg-muted/60 flex items-center rounded-lg border p-0.5'>
              <button
                type='button'
                className={cn(
                  'rounded-md px-2 py-0.5 text-xs transition-colors',
                  chartSubType === 'bar' ? 'bg-background shadow-sm' : 'text-muted-foreground'
                )}
                onClick={() => setChartSubType('bar')}
              >
                直方图
              </button>
              <button
                type='button'
                className={cn(
                  'rounded-md px-2 py-0.5 text-xs transition-colors',
                  chartSubType === 'line' ? 'bg-background shadow-sm' : 'text-muted-foreground'
                )}
                onClick={() => setChartSubType('line')}
              >
                折线图
              </button>
            </div>
          )}
          <ChartActions onResetZoom={handleResetZoom} onExportPng={() => void handleExportPng()} />
        </div>
      </div>

      {isDistribution && distribution && (
        <ChartStatsCard stats={distribution.stats} deviceStats={distribution.deviceStats} />
      )}

      <div className='relative' style={{ height }}>
        {loading ? (
          <div className='flex h-full items-center justify-center'>
            <Skeleton className='h-4 w-28' />
            <span className='text-muted-foreground ms-2 text-sm'>图表加载中...</span>
          </div>
        ) : !hasData ? (
          <div className='text-muted-foreground flex h-full items-center justify-center text-sm'>
            暂无数据
          </div>
        ) : !themeReady ? (
          <Skeleton className='h-full w-full' />
        ) : (
          <VChart
            // 主题/预设/子类型/缩放重置/重分箱窗口变化 → 整图重建（newAPI 同款机制）
            key={[type, chartSubType, themeKey, presetKey, resetNonce, isDistribution ? rangeKey : 'full'].join('|')}
            spec={{ ...spec, theme: themeKey, background: 'transparent' } as unknown as ISpec}
            options={VCHART_OPTION}
            onReady={(chart) => {
              chartRef.current = chart
            }}
            onDataZoomChange={handleDataZoomChange}
          />
        )}
      </div>
    </div>
  )
}
