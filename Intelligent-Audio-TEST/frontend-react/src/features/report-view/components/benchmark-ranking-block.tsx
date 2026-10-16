/**
 * Benchmark 排行区块（15_报告域.md §3.8 + 14_benchmark排行.md §10.3 组件规格）。
 * 独立模块：内嵌 ECharts 参考线图（横向柱状图 + 中位数/最佳参考线），与域图表 Chart.js v4 互不干扰
 * （INT-500 实施卡注意：排行区块专用 ECharts，独立引入 echarts，不混入 report-chart）。
 * 异步计算 + 进度轮询 + 来源筛选（仅实测/仅导入/全部/仅看有差异的）+ 版本标注 + 发布 Benchmark 报告。
 * 报告详情页内嵌于总览分区前（§3.1 type=benchmark 分发）。
 */
import { useCallback, useEffect, useRef } from 'react'
import { toast } from 'sonner'
import * as echarts from 'echarts'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useBenchmarkRanking, type BenchmarkSourceFilter } from '@/application/report-view/use-benchmark-ranking'
import { CHART_COLORS } from '@/infrastructure/adapters/chartConfig'
import { cn } from '@/lib/utils'

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
    progress,
    source,
    setSource,
    data,
    filteredRows,
    publishBenchmarkReport,
  } = useBenchmarkRanking(reportId)

  const rows = data ? filteredRows(data.rows) : []
  const chartRef = useRef<HTMLDivElement>(null)
  const echartsRef = useRef<echarts.ECharts | null>(null)

  // ECharts 横向柱状图 + 中位数/最佳参考线（排行区块独立模块；深浅色随主题 token 近似）
  useEffect(() => {
    const dom = chartRef.current
    if (!dom || !data) return
    if (!echartsRef.current) echartsRef.current = echarts.init(dom)
    const chart = echartsRef.current
    const isDark = document.documentElement.classList.contains('dark')
    const textColor = isDark ? 'rgba(255,255,255,0.65)' : 'rgba(0,0,0,0.55)'
    const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'

    const list = rows
      .map((r) => ({ name: r.subjectName, value: r.metricValue }))
      .sort((a, b) => a.value - b.value)

    chart.setOption({
      animationDuration: 400,
      grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: unknown) => {
          const items = Array.isArray(params) ? params : [params]
          const head = items[0] as { name: string; value: number } | undefined
          return head ? `${head.name}<br/>${data.metricName}：${head.value}${data.unit}` : ''
        },
      },
      xAxis: {
        type: 'value',
        axisLabel: { color: textColor },
        splitLine: { lineStyle: { color: gridColor } },
      },
      yAxis: {
        type: 'category',
        data: list.map((r) => r.name),
        axisLabel: { color: textColor },
        axisLine: { lineStyle: { color: gridColor } },
      },
      series: [
        {
          type: 'bar',
          data: list,
          barWidth: 18,
          itemStyle: {
            color: CHART_COLORS.primary,
            borderRadius: [0, 4, 4, 0],
          },
          label: {
            show: true,
            position: 'right',
            formatter: `{c}${data.unit}`,
            color: textColor,
            fontSize: 11,
          },
          // 中位数与最佳参考线（§3.8 实测）
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { type: 'dashed', color: CHART_COLORS.warning, width: 1.5 },
            label: { formatter: '中位数 {c}', color: CHART_COLORS.warning, fontSize: 10 },
            data: [{ xAxis: data.median, label: { formatter: '中位数' } }],
          },
        },
      ],
    })
    return () => {
      // chart 实例复用，组件卸载时销毁
    }
  }, [data, rows, source])

  useEffect(() => {
    return () => {
      echartsRef.current?.dispose()
      echartsRef.current = null
    }
  }, [])

  // 窗口 resize 跟随容器
  useEffect(() => {
    const handleResize = () => echartsRef.current?.resize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const handlePublish = useCallback(async () => {
    const result = await publishBenchmarkReport()
    if (result) toast.success('Benchmark 报告已发布')
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
        <div className='mt-4 h-1.5 overflow-hidden rounded-full bg-muted'>
          <div
            className='bg-primary h-full rounded-full transition-all duration-200'
            style={{ width: `${progress}%` }}
            aria-label={`排行计算进度 ${progress}%`}
          />
        </div>
        <p className='text-muted-foreground mt-2 text-xs tabular-nums'>正在计算排行结果... {progress}%</p>
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
        <Button size='sm' onClick={handlePublish}>
          发布 Benchmark 报告
        </Button>
      </div>
      <p className='text-muted-foreground mt-1 text-xs'>
        计算时间 {data.computedAt.replace('T', ' ').slice(0, 16)} · 中位数 {data.median}{data.unit} · 最佳 {data.best}{data.unit}
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

      {/* ECharts 参考线图（独立模块） */}
      <div className='mt-4'>
        <p className='text-muted-foreground mb-2 text-xs font-medium'>指标值参考线（中位数 / 最佳）</p>
        <div ref={chartRef} style={{ height: Math.max(240, rows.length * 34) }} className='w-full' />
      </div>

      <p className='text-muted-foreground mt-3 text-xs leading-5'>
        {reportName}：发布后将当前排行结果生成独立 Benchmark 报告，可查看与导出。
      </p>
    </section>
  )
}
