/**
 * ChartComponent 对位（15_报告域.md §3.7：Chart.js v4 + chartjs-plugin-zoom）。
 * props: title/data(labels+datasets)/type(bar|line|radar|distribution)/showHeader/showActions/
 *         loading/stats/enableZoom/height；chartReady/export 事件。
 * distribution 模式：x 轴「不同区间的{title}」（linear）、y 轴「区间内用例数量」（stepSize:1）、
 * 折线图/直方图子类型切换（chartSubType）+ zoom/pan 后固定 20 区间按可见范围重分箱
 * （rebinDistributionData）+ 固定 x min/max + resetZoom 恢复原始。
 * 深浅色/多主题走语义 token（图例/网格/tooltip 色，canvas 色板为 chartConfig 等价 hex）。
 * INT-430 前置条件：本组件为共享平台件，驻留 components/common/report-chart（dashboard/benchmark 复用）。
 */
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  RadialLinearScale,
  RadarController,
  Tooltip,
  Filler,
  type ChartOptions,
} from 'chart.js'
import zoomPlugin from 'chartjs-plugin-zoom'
import { useEffect, useRef, useState } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import type {
  ChartSeriesData,
  DistributionChartData,
} from '@/application/report-view/use-report-charts'
import {
  getDefaultChartConfig,
  rebinDistributionData,
} from '@/application/report-view/use-report-charts'
import { cn } from '@/lib/utils'

import { ChartActions } from './chart-actions'
import { ChartStatsCard } from './chart-stats-card'

ChartJS.register(
  BarController,
  BarElement,
  LineController,
  LineElement,
  PointElement,
  CategoryScale,
  LinearScale,
  RadialLinearScale,
  RadarController,
  Legend,
  Tooltip,
  Filler,
  zoomPlugin
)

export type ChartKind = 'bar' | 'line' | 'radar' | 'distribution'
export type ChartSubKind = 'bar' | 'line'

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
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<ChartJS | null>(null)
  // 分布图子类型：折线图/直方图（§3.7 chartSubType）
  const [chartSubType, setChartSubType] = useState<ChartSubKind>('bar')
  // zoom 回调需读最新子类型（useEffect 内闭包滞后，用 ref 透传）
  const chartSubTypeRef = useRef<ChartSubKind>(chartSubType)
  chartSubTypeRef.current = chartSubType

  const isDark = typeof document !== 'undefined'
    ? (document.documentElement.classList.contains('dark') ?? false)
    : false

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const base = getDefaultChartConfig(isDark) as ChartOptions

    /** zoom/pan 后按可见范围重分箱 + 固定 x min/max（§3.7） */
    const rebinToVisible = (chart: ChartJS) => {
      if (type !== 'distribution' || !distribution) return
      const xScale = chart.scales.x
      if (!xScale || !Number.isFinite(xScale.min) || !Number.isFinite(xScale.max)) return
      const min = xScale.min
      const max = xScale.max
      if (max <= min) return
      const rebinned = rebinDistributionData(
        distribution.rawData,
        distribution.labels,
        min,
        max,
        20
      )
      const isLine = chartSubTypeRef.current === 'line'
      chart.data.datasets = rebinned.datasets.map((d) => ({
        ...d,
        type: isLine ? 'line' : 'bar',
        borderRadius: isLine ? 0 : 4,
        barPercentage: 0.9,
        categoryPercentage: 0.85,
        fill: isLine ? false : undefined,
        tension: isLine ? 0.3 : undefined,
      }))
      chart.data.labels = rebinned.labels
      if (chart.options.scales) {
        chart.options.scales.x = {
          ...(chart.options.scales.x ?? {}),
          min,
          max,
        }
      }
      chart.update()
    }

    const zoomOptions = enableZoom
      ? {
          pan: { enabled: true, mode: 'x' },
          zoom: {
            wheel: { enabled: true },
            pinch: { enabled: true },
            mode: 'x' as const,
            onZoomComplete: ({ chart }: { chart: ChartJS }) => rebinToVisible(chart),
            onPanComplete: ({ chart }: { chart: ChartJS }) => rebinToVisible(chart),
          },
        }
      : { pan: { enabled: false }, zoom: { wheel: { enabled: false }, pinch: { enabled: false } } }

    const buildOptions = (): ChartOptions => {
      const isDistribution = type === 'distribution'
      if (isDistribution && distribution) {
        return {
          ...base,
          indexAxis: 'x',
          scales: {
            x: {
              ...(base.scales?.x ?? {}),
              type: 'linear',
              title: { display: true, text: xAxisTitle ?? `不同区间的${title}`, color: (base.scales?.x?.ticks as { color?: string } | undefined)?.color },
              min: distribution.stats?.min,
              max: distribution.stats?.max,
            },
            y: {
              ...(base.scales?.y ?? {}),
              title: { display: true, text: '区间内用例数量', color: (base.scales?.y?.ticks as { color?: string } | undefined)?.color },
              ticks: { ...((base.scales?.y?.ticks ?? {}) as Record<string, unknown>), stepSize: 1 },
            },
          },
          plugins: { ...base.plugins, zoom: zoomOptions },
        } as ChartOptions
      }
      return {
        ...base,
        plugins: { ...base.plugins, zoom: zoomOptions },
      } as ChartOptions
    }

    // 装配 datasets（distribution 用重分箱直方图）
    const isLine = chartSubType === 'line'
    const datasets = distribution && type === 'distribution'
      ? rebinDistributionData(
          distribution.rawData,
          distribution.labels,
          distribution.stats?.min ?? 0,
          distribution.stats?.max ?? 1
        ).datasets.map((d) => ({
          ...d,
          type: isLine ? 'line' : 'bar',
          borderRadius: isLine ? 0 : 4,
          barPercentage: 0.9,
          categoryPercentage: 0.85,
          fill: isLine ? false : undefined,
          tension: isLine ? 0.3 : undefined,
        }))
      : series.datasets

    chartRef.current = new ChartJS(canvas, {
      type: type === 'distribution' ? 'bar' : (type === 'radar' ? 'radar' : type),
      data: { labels: type === 'distribution' ? undefined : series.labels, datasets },
      options: buildOptions(),
    })

    return () => {
      chartRef.current?.destroy()
      chartRef.current = null
    }
  }, [title, type, series, distribution, enableZoom, isDark, chartSubType, xAxisTitle])

  const handleResetZoom = () => {
    chartRef.current?.resetZoom()
  }

  const handleExportPng = () => {
    const canvas = canvasRef.current
    if (!canvas) return
    const link = document.createElement('a')
    link.download = `${title}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
  }

  const isDistribution = type === 'distribution'

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
          <ChartActions onResetZoom={handleResetZoom} onExportPng={handleExportPng} />
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
        ) : (
          <canvas ref={canvasRef} />
        )}
      </div>
    </div>
  )
}
