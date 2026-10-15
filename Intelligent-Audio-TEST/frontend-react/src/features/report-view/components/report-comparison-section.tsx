/**
 * 对比报告差异（规范 §4.8，comparison/secondary_comparison 特有）：
 * 对比矩阵表（行=评估维度，列=各任务/各报告；最优 text-success / 最差 text-destructive 高亮）
 * + 趋势折线（VChart line，各任务关键指标；AI 预测虚线搁置，§10-4）。
 */
import { VChart } from '@visactor/react-vchart'
import type { ISpec } from '@visactor/vchart'
import { GitCompareArrows } from 'lucide-react'
import { useMemo } from 'react'

import {
  useChartTheme,
  useThemePresetKey,
  VCHART_OPTION,
} from '@/features/dashboard/lib/vchart'
import type { ReportDetailData } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import {
  buildPassRateTrendSpec,
  getChartThemeTokens,
  resolveChartColors,
} from '@/application/report-view/use-report-charts'

export function ReportComparisonSection({ report }: { report: ReportDetailData }) {
  const { themeReady, themeKey, resolvedTheme } = useChartTheme()
  const presetKey = useThemePresetKey()

  const metrics = Array.from(
    new Set(report.summary.metric_data.flatMap((g) => g.metrics.map((m) => m.metric)))
  )
  const resources = report.summary.resource_headers
  const valueOf = (resourceKey: string, metric: string): number | null =>
    report.summary.metric_data.find((g) => g.resource === resourceKey)?.metrics.find(
      (m) => m.metric === metric
    )?.value ?? null

  const colors = resolveChartColors(Math.max(resources.length, 3))
  const trendSpec = useMemo(
    () =>
      buildPassRateTrendSpec(report.summary.metric_data, {
        colors,
        ...getChartThemeTokens(resolvedTheme),
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [report.summary.metric_data, presetKey, resolvedTheme, report.id]
  )

  // 每指标行最优/最差值（跨资源比较）
  const extremes = metrics.map((metric) => {
    const values = resources
      .map((r) => valueOf(r.key, metric))
      .filter((v): v is number => v != null)
    if (values.length === 0) return { max: null, min: null }
    return { max: Math.max(...values), min: Math.min(...values) }
  })

  return (
    <div className='space-y-4'>
      <div className='flex items-center gap-2'>
        <GitCompareArrows className='text-muted-foreground size-4' aria-hidden='true' />
        <h3 className='text-sm font-semibold'>对比矩阵</h3>
        <span className='text-muted-foreground text-xs'>
          {report.type === 'secondary_comparison' ? '报告间差异' : '任务间差异'}
        </span>
      </div>

      <div className='overflow-x-auto rounded-lg border'>
        <table className='w-full min-w-[480px] text-sm'>
          <thead>
            <tr className='text-muted-foreground border-b bg-muted/30'>
              <th className='px-3 py-2 text-left font-medium'>评估维度</th>
              {resources.map((resource) => (
                <th key={resource.key} className='px-3 py-2 text-left font-medium'>
                  {resource.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map((metric, index) => {
              const { max, min } = extremes[index]
              return (
                <tr key={metric} className='border-b last:border-0 hover:bg-muted/30'>
                  <td className='px-3 py-2 font-medium'>{metric}</td>
                  {resources.map((resource) => {
                    const value = valueOf(resource.key, metric)
                    if (value == null) {
                      return (
                        <td key={resource.key} className='px-3 py-2'>
                          <span className='text-muted-foreground/50'>—</span>
                        </td>
                      )
                    }
                    const isBest = max != null && value === max
                    const isWorst = min != null && value === min
                    return (
                      <td key={resource.key} className='px-3 py-2'>
                        <span
                          title={isBest ? '最优' : isWorst ? '最差' : undefined}
                          className={cn(
                            'font-mono tabular-nums',
                            isBest && 'text-success font-semibold',
                            isWorst && 'text-destructive'
                          )}
                        >
                          {value.toFixed(2)}
                        </span>
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className='overflow-hidden rounded-lg border'>
        <div className='flex items-center gap-2 border-b px-3 py-2'>
          <h4 className='text-sm font-semibold'>趋势分析</h4>
          <span className='text-muted-foreground text-xs'>各任务关键指标对比</span>
        </div>
        <div className='h-56 p-2 sm:h-64 sm:p-3'>
          {themeReady && trendSpec ? (
            <VChart
              key={['compare-trend', themeKey, presetKey].join('-')}
              spec={
                { ...trendSpec, theme: themeKey, background: 'transparent' } as ISpec
              }
              options={VCHART_OPTION}
            />
          ) : (
            <div className='text-muted-foreground flex h-full items-center justify-center rounded-lg border text-xs'>
              暂无趋势数据
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
