/**
 * Benchmark 排行区块（15_报告域.md §3.8 + 14_benchmark排行.md §10.3 组件规格）。
 * 内嵌参考线图（横向柱状图 + 中位数/最佳参考线）。
 * INT-1273：图表引擎由 echarts 换成 Visactor VChart（全站一套，与 report-chart 同库）；
 * 排序/柱宽/圆角/数值标签/参考线口径保持不变。
 * 数据经 infrastructure 获取（后端 GET /benchmarks/reports/{id} 待立项 → benchmarkApi 桩）+ 来源筛选
 * （仅实测/仅导入/全部/仅看有差异的）+ 版本标注 + 发布 Benchmark 报告。
 * 报告详情页内嵌于总览分区前（§3.1 type=benchmark 分发）。
 */
import { VChart } from '@visactor/react-vchart'
import type { IBarChartSpec, ISpec } from '@visactor/vchart'
import { useCallback, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/infrastructure/api/api-error'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { useBenchmarkRanking, type BenchmarkSourceFilter } from '@/application/report-view/use-benchmark-ranking'
import { CHART_COLORS, getChartAxisColors } from '@/application/report-view/use-report-charts'
import {
  useChartTheme,
  useThemePresetKey,
  VCHART_OPTION,
} from '@/features/dashboard/lib/vchart'
import { cn } from '@/lib/utils'
import { formatDateTime } from '@/lib/date-time'

const SOURCE_FILTERS: { value: BenchmarkSourceFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'measured', label: '仅实测' },
  { value: 'imported', label: '仅导入' },
  { value: 'diff', label: '仅看有差异的' },
]

interface BenchmarkRankingBlockProps {
  reportId: number
  reportName: string
}

export function BenchmarkRankingBlock({ reportId, reportName }: BenchmarkRankingBlockProps) {
  const {
    computing,
    error,
    source,
    setSource,
    data,
    filteredRows,
    publishBenchmarkReport,
  } = useBenchmarkRanking(reportId)

  const rows = data ? filteredRows(data.rows) : []
  const [publishOpen, setPublishOpen] = useState(false)
  const { themeReady, themeKey, resolvedTheme } = useChartTheme()
  const presetKey = useThemePresetKey()

  // 横向柱状图 + 中位数/最佳参考线（排行区块独立模块；深浅色轴色随主题 token）
  const chartSpec = useMemo(() => {
    if (!data) return null
    const isDark = resolvedTheme === 'dark'
    const axisColors = getChartAxisColors(isDark)
    const textColor = axisColors.tickColor
    const gridColor = axisColors.gridColor
    const list = rows
      .map((row) => ({ 被测主体: row.subjectName, 指标值: row.metricValue }))
      .sort((a, b) => a.指标值 - b.指标值)

    return {
      type: 'bar',
      direction: 'horizontal',
      data: [{ id: 'benchmark-ranking', values: list }],
      xField: '指标值',
      yField: '被测主体',
      color: [CHART_COLORS.primary],
      legends: { visible: false },
      barMaxWidth: 18,
      bar: { style: { cornerRadius: [0, 4, 4, 0] } },
      label: {
        visible: true,
        position: 'right',
        formatMethod: (value: unknown) => `${String(value)}${data.unit}`,
        style: { fill: textColor, fontSize: 11 },
      },
      axes: [
        {
          orient: 'left',
          type: 'band',
          label: {
            style: { fill: textColor, fontSize: 12, textAlign: 'right' },
            autoHide: true,
            autoLimit: true,
          },
          grid: { visible: false },
          domainLine: { visible: true, style: { stroke: gridColor } },
          tick: { visible: false },
        },
        {
          orient: 'bottom',
          type: 'linear',
          label: { style: { fill: textColor, fontSize: 11 } },
          grid: { visible: true, style: { stroke: gridColor, lineDash: [3, 3] } },
          domainLine: { visible: false },
          tick: { visible: false },
        },
      ],
      // 中位数与最佳参考线（§3.8 实测：中位数 dashed warning + 最佳 dashed success）
      markLine: [
        {
          x: data.median,
          line: { style: { stroke: CHART_COLORS.warning, lineDash: [4, 4], lineWidth: 1.5 } },
          label: {
            visible: true,
            text: `中位数 ${data.median}`,
            style: { fill: CHART_COLORS.warning, fontSize: 10 },
          },
        },
        {
          x: data.best,
          line: { style: { stroke: CHART_COLORS.success, lineDash: [4, 4], lineWidth: 1.5 } },
          label: {
            visible: true,
            text: `最佳 ${data.best}`,
            style: { fill: CHART_COLORS.success, fontSize: 10 },
          },
        },
      ],
      tooltip: {
        mark: {
          content: [
            {
              key: (datum?: Record<string, unknown>) => String(datum?.['被测主体'] ?? ''),
              value: (datum?: Record<string, unknown>) =>
                `${data.metricName}：${String(datum?.['指标值'] ?? '')}${data.unit}`,
            },
          ],
        },
      },
      background: 'transparent',
      animation: true,
    } satisfies IBarChartSpec
  }, [data, rows, resolvedTheme])

  // benchmarks 排行图高度随行数增长（沿用改造前 34px/行、最小 240px）
  const chartHeight = Math.max(240, rows.length * 34)

  const handlePublish = useCallback(async () => {
    setPublishOpen(false)
    try {
      await publishBenchmarkReport()
      toast.success('Benchmark 报告已发布')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.userMessage : '发布失败，请重试')
    }
  }, [publishBenchmarkReport])

  if (computing) {
    return (
      <section id='report-benchmark-ranking' aria-label='Benchmark 排行' className='bg-card rounded-2xl border shadow-xs p-4 sm:p-5'>
        <div className='flex items-center justify-between gap-2'>
          <h4 className='text-sm font-semibold'>Benchmark 排行</h4>
          <Badge variant='outline'>计算中...</Badge>
        </div>
        <div className='mt-4 space-y-3'>
          <Skeleton className='h-4 w-full' />
          <Skeleton className='h-4 w-2/3' />
        </div>
        <p className='text-muted-foreground mt-2 text-xs'>正在计算排行结果…</p>
      </section>
    )
  }

  if (error) {
    return (
      <section id='report-benchmark-ranking' aria-label='Benchmark 排行' className='bg-card rounded-2xl border shadow-xs p-4 sm:p-5'>
        <h4 className='text-sm font-semibold'>Benchmark 排行</h4>
        <p className='text-destructive mt-2 text-sm'>排行数据加载失败，请稍后重试</p>
      </section>
    )
  }

  if (!data) {
    return (
      <section id='report-benchmark-ranking' aria-label='Benchmark 排行' className='bg-card rounded-2xl border shadow-xs p-4 sm:p-5'>
        <h4 className='text-sm font-semibold'>Benchmark 排行</h4>
        <p className='text-muted-foreground mt-2 text-sm'>暂无排行数据</p>
      </section>
    )
  }

  return (
    <section id='report-benchmark-ranking' aria-label='Benchmark 排行' className='bg-card rounded-2xl border shadow-xs p-4 sm:p-5'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <div className='flex items-center gap-2'>
          <h4 className='text-sm font-semibold'>Benchmark 排行</h4>
          <Badge variant='outline' className='font-mono'>实测轨 {data.version}</Badge>
          <Badge variant='secondary'>{data.metricName}</Badge>
        </div>
        <Button size='sm' onClick={() => setPublishOpen(true)}>
          发布 Benchmark 报告
        </Button>
      </div>
      <p className='text-muted-foreground mt-1 text-xs'>
        计算时间 {formatDateTime(data.computedAt)} · 中位数 {data.median}{data.unit} · 最佳 {data.best}{data.unit}
      </p>

      {/* 来源筛选（仅实测/仅导入/全部/仅看有差异的） */}
      <div role='group' aria-label='来源筛选' className='mt-4 flex flex-wrap gap-1.5'>
        {SOURCE_FILTERS.map((filter) => (
          <button
            key={filter.value}
            type='button'
            className={cn(
              'h-8 rounded-lg px-3 text-sm font-medium transition-colors',
              source === filter.value
                ? 'bg-primary text-primary-foreground'
                : 'hover:bg-muted text-muted-foreground'
            )}
            onClick={() => setSource(filter.value)}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {/* 排行表 */}
      <div className='mt-4 overflow-x-auto'>
        <table className='w-full text-sm'>
          <thead className='bg-muted/40 text-muted-foreground text-xs'>
            <tr>
              <th className='px-3 py-2.5 text-start font-medium'>名次</th>
              <th className='px-3 py-2.5 text-start font-medium'>被测主体</th>
              <th className='px-3 py-2.5 text-start font-medium'>主体类型</th>
              <th className='px-3 py-2.5 text-start font-medium'>数据来源</th>
              <th className='px-3 py-2.5 text-end font-medium'>指标值</th>
              <th className='px-3 py-2.5 text-end font-medium'>与头部差距</th>
              <th className='px-3 py-2.5 text-start font-medium'>百分位</th>
              <th className='px-3 py-2.5 text-end font-medium'>实测-导入差异</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.rank} className='hover:bg-muted/30 border-t first:border-t-0'>
                <td className='font-mono px-3 py-2.5 tabular-nums'>
                  <span className={cn(row.rank <= 3 && 'font-semibold')}>#{row.rank}</span>
                </td>
                <td className='px-3 py-2.5 font-medium'>{row.subjectName}</td>
                <td className='px-3 py-2.5'>
                  <Badge variant='outline'>{row.subjectType}</Badge>
                </td>
                <td className='px-3 py-2.5'>
                  <Badge variant={row.source === 'measured' ? 'secondary' : 'outline'}>
                    {row.source === 'measured' ? '实测' : '导入'}
                  </Badge>
                </td>
                <td className='font-mono px-3 py-2.5 text-end tabular-nums'>
                  {row.metricValue}{data.unit}
                </td>
                <td className={cn('font-mono px-3 py-2.5 text-end tabular-nums', row.gapBest === 0 ? 'text-success' : 'text-muted-foreground')}>
                  {row.gapBest === 0 ? '—' : `${row.gapBest}`}
                </td>
                <td className='px-3 py-2.5'>
                  <div className='flex items-center gap-2'>
                    <div className='bg-muted h-1.5 w-20 overflow-hidden rounded-full'>
                      <div
                        className='bg-primary h-full rounded-full'
                        style={{ width: `${row.percentile}%` }}
                      />
                    </div>
                    <span className='font-mono text-xs tabular-nums'>{row.percentile}</span>
                  </div>
                </td>
                <td className={cn(
                  'font-mono px-3 py-2.5 text-end tabular-nums',
                  row.delta === null ? 'text-muted-foreground'
                    : row.delta > 0 ? 'text-success'
                      : 'text-destructive'
                )}>
                  {row.delta === null ? '—' : row.delta > 0 ? `+${row.delta}` : `${row.delta}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className='text-muted-foreground px-3 py-6 text-center text-sm'>暂无匹配的排行数据</p>
        )}
      </div>

      {/* VChart 参考线图（独立模块） */}
      <div className='mt-4'>
        <p className='text-muted-foreground mb-2 text-xs font-medium'>指标值参考线（中位数 / 最佳）</p>
        {chartSpec && themeReady && rows.length > 0 ? (
          <VChart
            key={['benchmark-ranking', themeKey, presetKey].join('|')}
            spec={{ ...chartSpec, theme: themeKey, background: 'transparent' } as unknown as ISpec}
            options={VCHART_OPTION}
            style={{ height: chartHeight, width: '100%' }}
          />
        ) : (
          <div
            className='text-muted-foreground flex items-center justify-center text-sm'
            style={{ height: chartHeight }}
          >
            {rows.length === 0 ? '暂无匹配的排行数据' : '图表加载中...'}
          </div>
        )}
      </div>

      <p className='text-muted-foreground mt-3 text-xs leading-5'>
        {reportName}：发布后将当前排行结果生成独立 Benchmark 报告，可查看与导出。
      </p>

      {/* 发布确认（§4.13 ConfirmDialog：生成并发布为落库不可逆动作，确认后执行，主钮 destructive） */}
      <ConfirmDialog
        open={publishOpen}
        onOpenChange={setPublishOpen}
        title='发布 Benchmark 报告'
        desc='将当前排行结果生成独立 Benchmark 报告，可查看与导出。'
        confirmText='发布'
        destructive
        handleConfirm={() => void handlePublish()}
      />
    </section>
  )
}
