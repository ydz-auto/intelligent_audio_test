/**
 * ChartComponent 对位（15_报告域.md §3.7：Chart.js v4 + chartjs-plugin-zoom）。
 * props: title/data(labels+datasets)/type(bar|line|radar|distribution)/showHeader/showActions/
 *         loading/stats/enableZoom/height；chartReady/export 事件。
 * distribution 模式：x 轴「不同区间的{title}」（linear）、y 轴「区间内用例数量」（stepSize:1）、
 * zoom/pan 后重分箱（rebinDistributionData 固定 20 区间）+ resetZoom 恢复原始。
 * 深浅色/多主题走语义 token（图例/网格/tooltip 色，canvas 色板为 chartConfig 等价 hex）。
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
import { useEffect, useRef } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import type {
  ChartSeriesData,
  DistributionChartData,
} from '@/application/report-view/use-report-charts'
import {
  getDefaultChartConfig,
  rebinDistributionData,
} from '@/infrastructure/adapters/chartConfig'
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
}: ReportChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<ChartJS | null>(null)

  const isDark = typeof document !== 'undefined'
    ? (document.documentElement.classList.contains('dark') ?? false)
    : false

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const base = getDefaultChartConfig(isDark) as ChartOptions

    const buildOptions = (): ChartOptions => {
      const isDistribution = type === 'distribution'
      if (isDistribution && distribution) {
        const rebin = rebinDistributionData(
          distribution.rawData,
          distribution.labels,
          distribution.stats?.min ?? 0,
          distribution.stats?.max ?? 1
        )
        return {
          ...base,
          indexAxis: 'x',
          scales: {
            x: {
              ...base.scales?.x,
              type: 'linear',
              title: { display: true, text: `不同区间的${title}`, color: (base.scales?.x?.ticks as { color?: string })?.color },
              min: distribution.stats?.min,
              max: distribution.stats?.max,
            },
            y: {
              ...base.scales?.y,
              title: { display: true, text: '区间内用例数量', color: (base.scales?.y?.ticks as { color?: string })?.color },
              ticks: { ...(base.scales?.y?.ticks as object), stepSize: 1 },
            },
          },
          plugins: {
            ...base.plugins,
            zoom: enableZoom
              ? {
                  pan: { enabled: true, mode: 'x' },
                  zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' },
                }
              : { zoom: false, pan: false },
          },
        }
      }
      return {
        ...base,
        plugins: {
          ...base.plugins,
          zoom: enableZoom
            ? {
                pan: { enabled: true, mode: 'x' },
                zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' },
              }
            : { zoom: false, pan: false },
        },
      }
    }

    // 装配 datasets（distribution 用重分箱直方图）
    const datasets = distribution && type === 'distribution'
      ? rebinDistributionData(
          distribution.rawData,
          distribution.labels,
          distribution.stats?.min ?? 0,
          distribution.stats?.max ?? 1
        ).datasets.map((d) => ({
          ...d,
          borderRadius: 4,
          barPercentage: 0.9,
          categoryPercentage: 0.85,
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
  }, [title, type, series, distribution, enableZoom, isDark])

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

  return (
    <div className={cn('bg-card rounded-2xl border shadow-xs p-4', className)}>
      <div className='flex items-start justify-between gap-2'>
        <div>
          <h4 className='text-sm font-semibold'>{title}</h4>
          {subtitle && (
            <p className='text-muted-foreground text-xs'>{subtitle}</p>
          )}
        </div>
        <ChartActions onResetZoom={handleResetZoom} onExportPng={handleExportPng} />
      </div>

      {type === 'distribution' && distribution && (
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
