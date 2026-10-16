/**
 * 统计结果表（15_报告域.md §2.2「统计表格」+「异常统计识别」）。
 * 详细页签=统计行（维度/统计值/占比/环比/状态）；异常页签=异常行（维度/值/原因）。
 * 表格形态对齐 reports-table（HTML table + 语义 token），支持导出按钮（复用 §4.3 链路）。
 */
import { FileDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import type {
  StatisticAnomalyRow,
  StatisticTableRow,
} from '@/application/report-statistics/use-report-statistics'
import { cn } from '@/lib/utils'

interface StatisticsTableProps {
  rows: StatisticTableRow[]
  anomalies: StatisticAnomalyRow[]
  isLoading: boolean
  mode: 'detail' | 'anomaly'
  onExport: () => void
}

/** 环比状态语义色（normal 灰 / up 绿 / down 红） */
function changeMeta(change: number): { label: string; className: string } {
  if (change === 0) return { label: '—', className: 'text-muted-foreground' }
  if (change > 0) return { label: `+${change}`, className: 'text-success' }
  return { label: `${change}`, className: 'text-destructive' }
}

export function StatisticsTable({
  rows,
  anomalies,
  isLoading,
  mode,
  onExport,
}: StatisticsTableProps) {
  if (isLoading) {
    return (
      <div aria-busy='true' className='overflow-hidden rounded-lg border'>
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className='flex gap-4 border-b p-4 last:border-0'>
            <Skeleton className='h-5 w-40' />
            <Skeleton className='h-5 w-24' />
            <Skeleton className='h-5 flex-1' />
          </div>
        ))}
      </div>
    )
  }

  if (mode === 'anomaly') {
    if (anomalies.length === 0) {
      return (
        <Empty className='min-h-[240px]'>
          <EmptyHeader>
            <EmptyMedia variant='icon' />
            <EmptyTitle>暂无统计数据</EmptyTitle>
            <EmptyDescription>当前维度与时间范围内未识别到统计异常</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )
    }
    return (
      <div className='overflow-hidden rounded-lg border'>
        <div className='flex items-center justify-between border-b px-4 py-2.5'>
          <span className='text-sm font-medium'>异常统计识别</span>
          <Button variant='ghost' size='sm' onClick={onExport}>
            <FileDown data-icon='inline-start' />
            导出
          </Button>
        </div>
        <table className='w-full text-sm'>
          <thead className='bg-muted/40 text-muted-foreground text-xs'>
            <tr>
              <th className='px-4 py-2.5 text-start font-medium'>统计维度</th>
              <th className='px-4 py-2.5 text-start font-medium'>统计值</th>
              <th className='px-4 py-2.5 text-start font-medium'>异常原因</th>
            </tr>
          </thead>
          <tbody>
            {anomalies.map((row, index) => (
              <tr key={index} className='hover:bg-muted/30 border-t first:border-t-0'>
                <td className='px-4 py-3 font-medium'>{row.dimension}</td>
                <td className='font-mono px-4 py-3 tabular-nums'>{row.value}</td>
                <td className='text-muted-foreground px-4 py-3'>{row.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <Empty className='min-h-[240px]'>
        <EmptyHeader>
          <EmptyMedia variant='icon' />
          <EmptyTitle>暂无统计数据</EmptyTitle>
          <EmptyDescription>请选择其他统计维度或调整时间范围后重试</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className='overflow-hidden rounded-lg border'>
      <div className='flex items-center justify-between border-b px-4 py-2.5'>
        <span className='text-sm font-medium'>统计结果明细</span>
        <Button variant='ghost' size='sm' onClick={onExport}>
          <FileDown data-icon='inline-start' />
          导出
        </Button>
      </div>
      <table className='w-full text-sm'>
        <thead className='bg-muted/40 text-muted-foreground text-xs'>
          <tr>
            <th className='px-4 py-2.5 text-start font-medium'>统计维度</th>
            <th className='px-4 py-2.5 text-end font-medium'>统计值</th>
            <th className='px-4 py-2.5 text-end font-medium'>占比</th>
            <th className='px-4 py-2.5 text-end font-medium'>环比</th>
            <th className='px-4 py-2.5 text-start font-medium'>状态</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const change = changeMeta(row.change)
            return (
              <tr key={index} className='hover:bg-muted/30 border-t first:border-t-0'>
                <td className='px-4 py-3 font-medium'>{row.dimension}</td>
                <td className='font-mono px-4 py-3 text-end tabular-nums'>{row.value}</td>
                <td className='font-mono px-4 py-3 text-end tabular-nums'>
                  {row.ratio > 0 ? `${row.ratio}%` : '—'}
                </td>
                <td className={cn('font-mono px-4 py-3 text-end tabular-nums', change.className)}>
                  {change.label}
                </td>
                <td className='px-4 py-3'>
                  <Badge
                    variant={row.status === 'up' ? 'secondary' : row.status === 'down' ? 'destructive' : 'outline'}
                  >
                    {row.status === 'up' ? '上升' : row.status === 'down' ? '下降' : '平稳'}
                  </Badge>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
