/**
 * 总览分区（规范 §4.3 OverviewCard 重设计）：
 * 指标卡行（用例总数/已执行/失败/通过率；对比报告追加任务对比数/生成耗时）+ 维度×资源矩阵表。
 * matrix 数据源 summary.metric_data（flatten：[{resource, metrics:[{id,metric,value}]}]）。
 */
import { CheckCircle2, CircleX, ListChecks, TrendingUp } from 'lucide-react'
import type { ReactNode } from 'react'

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import type { ReportDetailData } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import { getSuccessRateVariant } from '@/features/reports/constants'

function StatCard({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: ReactNode
  label: string
  value: string
  hint?: string
  tone?: 'success' | 'warning' | 'danger'
}) {
  return (
    <div className='bg-background rounded-lg border p-3'>
      <div className='flex items-center gap-2'>
        <span
          className={cn(
            'flex size-5 items-center justify-center rounded-md',
            tone === 'success'
              ? 'bg-success/10 text-success'
              : tone === 'warning'
                ? 'bg-warning/10 text-warning'
                : tone === 'danger'
                  ? 'bg-destructive/10 text-destructive'
                  : 'bg-muted text-muted-foreground'
          )}
        >
          {icon}
        </span>
        <span className='text-muted-foreground text-xs'>{label}</span>
      </div>
      <div
        className={cn(
          'font-mono mt-2 text-lg font-bold tabular-nums',
          tone === 'success' && 'text-success',
          tone === 'warning' && 'text-warning',
          tone === 'danger' && 'text-destructive'
        )}
      >
        {value}
      </div>
      {hint && <div className='text-muted-foreground mt-0.5 text-xs'>{hint}</div>}
    </div>
  )
}

interface ReportOverviewProps {
  report: ReportDetailData
}

export function ReportOverview({ report }: ReportOverviewProps) {
  const summary = report.summary
  const isComparison =
    report.type === 'comparison' || report.type === 'secondary_comparison'
  const passRate = summary.total_cases > 0
    ? (summary.completed_cases - summary.failed_cases) / summary.total_cases * 100
    : 0

  // 矩阵：维度（union metric 名）行 × 资源（resource_headers 标签）列
  const metrics = Array.from(
    new Set(summary.metric_data.flatMap((g) => g.metrics.map((m) => m.metric)))
  )
  const resources = summary.resource_headers
  const valueOf = (resourceKey: string, metric: string): number | null => {
    const group = summary.metric_data.find((g) => g.resource === resourceKey)
    return group?.metrics.find((m) => m.metric === metric)?.value ?? null
  }

  return (
    <div className='space-y-4'>
      <div className='grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4'>
        <StatCard
          icon={<ListChecks className='size-3' />}
          label='用例总数'
          value={String(summary.total_cases)}
          hint={isComparison ? '对比任务用例汇总' : '报告含用例数'}
        />
        <StatCard
          icon={<CheckCircle2 className='size-3' />}
          label='已执行'
          value={String(summary.completed_cases)}
          tone='success'
        />
        <StatCard
          icon={<CircleX className='size-3' />}
          label='失败'
          value={String(summary.failed_cases)}
          tone='danger'
        />
        {isComparison ? (
          <>
            <StatCard
              icon={<TrendingUp className='size-3' />}
              label='任务对比数'
              value={String(summary.resources.length)}
            />
            <StatCard
              icon={<TrendingUp className='size-3' />}
              label='生成耗时'
              value='3 分钟'
              hint='mock 快照口径'
            />
          </>
        ) : (
          <StatCard
            icon={<TrendingUp className='size-3' />}
            label='通过率'
            value={summary.total_cases > 0 ? `${passRate.toFixed(1)}%` : '—'}
            tone={getSuccessRateVariant(passRate)}
          />
        )}
      </div>

      <div>
        <div className='mb-2 flex items-baseline justify-between'>
          <h3 className='text-sm font-semibold'>维度 / 资源</h3>
          <span className='text-muted-foreground text-xs'>矩阵单元格保留 2 位小数</span>
        </div>
        {metrics.length === 0 || resources.length === 0 ? (
          <Empty className='min-h-32 border-dashed'>
            <EmptyHeader>
              <EmptyMedia variant='icon'>
                <ListChecks className='size-4' />
              </EmptyMedia>
              <EmptyTitle>暂无维度数据</EmptyTitle>
              <EmptyDescription>报告生成后评估维度数据将在此展示</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
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
                {metrics.map((metric) => (
                  <tr key={metric} className='border-b last:border-0 hover:bg-muted/30'>
                    <td className='px-3 py-2 font-medium'>{metric}</td>
                    {resources.map((resource) => {
                      const value = valueOf(resource.key, metric)
                      return (
                        <td key={resource.key} className='px-3 py-2'>
                          {value == null ? (
                            <span className='text-muted-foreground/50'>—</span>
                          ) : (
                            <span className='font-mono tabular-nums'>
                              {value.toFixed(2)}
                            </span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
