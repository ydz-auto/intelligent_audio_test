/**
 * 报告展示页列表（15_报告域.md §2.1：DataTablePage 展示视角，弱管理）。
 * 列=名称(次行 类型+任务名)/类型/算法/通过率/用例数/创建时间/操作；行点击 → /report/$reportId。
 * 行操作仅「查看」「复制链接」——生成/编辑/发布/删除/批量/导出/收藏/回收站等管理操作不在本页。
 * 空态「暂无已发布报告」；TableSkeleton/ErrorState。
 */
import { ArrowUpDown, Copy, ExternalLink } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { ReportListItem } from '@/domain/models/report'

import {
  formatDateTime,
  getAlgorithmLabel,
  getReportTypeMeta,
  getSuccessRateVariant,
} from '@/features/reports/constants'

interface ReportShowcaseListProps {
  items: ReportListItem[]
  isLoading?: boolean
  hasError?: boolean
  onRetry?: () => void
  onRowClick: (report: ReportListItem) => void
}

export function ReportShowcaseList({
  items,
  isLoading,
  hasError,
  onRetry,
  onRowClick,
}: ReportShowcaseListProps) {
  if (isLoading && items.length === 0) {
    return (
      <div aria-busy='true' className='overflow-hidden rounded-lg border'>
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className='flex gap-4 border-b p-4 last:border-0'>
            <Skeleton className='h-5 w-48 max-w-full' />
            <Skeleton className='h-5 w-20' />
            <Skeleton className='h-5 flex-1' />
            <Skeleton className='h-5 w-16' />
          </div>
        ))}
      </div>
    )
  }

  if (hasError && items.length === 0) {
    return (
      <Empty className='min-h-[320px] border-dashed'>
        <EmptyHeader>
          <EmptyMedia variant='icon'>
            <ArrowUpDown className='size-4' />
          </EmptyMedia>
          <EmptyTitle>加载失败</EmptyTitle>
          <EmptyDescription>报告列表加载失败，请重试</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button variant='outline' size='sm' onClick={onRetry}>
            请重试
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  if (items.length === 0) {
    return (
      <Empty className='min-h-[320px] border-dashed'>
        <EmptyHeader>
          <EmptyMedia variant='icon'>
            <ArrowUpDown className='size-4' />
          </EmptyMedia>
          <EmptyTitle>暂无已发布报告</EmptyTitle>
          <EmptyDescription>
            已发布的测试报告将在此展示；草稿与回收站报告请前往「报告中心」查看
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  const handleCopyLink = (report: ReportListItem) => {
    void navigator.clipboard?.writeText(`${window.location.origin}/report/${report.id}`)
    toast.success('链接已复制')
  }

  return (
    <div className='overflow-hidden rounded-lg border'>
      <div className='overflow-x-auto'>
        <table className='w-full min-w-[760px] text-sm'>
          <thead>
            <tr className='text-muted-foreground border-b bg-muted/30'>
              <th className='px-3 py-2.5 text-left font-medium'>名称</th>
              <th className='px-3 py-2.5 text-left font-medium'>类型</th>
              <th className='px-3 py-2.5 text-left font-medium'>算法</th>
              <th className='px-3 py-2.5 text-right font-medium'>通过率</th>
              <th className='px-3 py-2.5 text-right font-medium'>用例数</th>
              <th className='px-3 py-2.5 text-left font-medium'>创建时间</th>
              <th className='px-3 py-2.5 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((report) => {
              const typeMeta = getReportTypeMeta(report.type)
              const rateVariant = getSuccessRateVariant(report.summary.pass_rate)
              return (
                <tr
                  key={report.id}
                  className='hover:bg-muted/30 border-b transition-colors last:border-0'
                >
                  <td className='cursor-pointer px-3 py-2.5' onClick={() => onRowClick(report)}>
                    <p className='font-medium'>{report.name}</p>
                    <p className='text-muted-foreground text-xs'>
                      {typeMeta.label} · {report.task_name}
                    </p>
                  </td>
                  <td className='px-3 py-2.5'>
                    <StatusBadge label={typeMeta.label} variant={typeMeta.variant} />
                  </td>
                  <td className='px-3 py-2.5'>
                    <Badge variant='secondary'>
                      {getAlgorithmLabel(report.algorithm_type)}
                    </Badge>
                  </td>
                  <td className='text-muted-foreground px-3 py-2.5 text-right tabular-nums'>
                    <span className={rateVariant === 'success' ? 'text-success' : rateVariant === 'warning' ? 'text-warning' : ''}>
                      {report.summary.pass_rate > 0
                        ? `${report.summary.pass_rate.toFixed(1)}%`
                        : '—'}
                    </span>
                  </td>
                  <td className='text-muted-foreground px-3 py-2.5 text-right tabular-nums'>
                    {(report.type === 'comparison' || report.type === 'secondary_comparison') &&
                    report.summary.task_count !== undefined
                      ? `${report.summary.task_count} 任务`
                      : report.summary.total_cases}
                  </td>
                  <td className='text-muted-foreground px-3 py-2.5 font-mono text-xs tabular-nums'>
                    {formatDateTime(report.created_at)}
                  </td>
                  <td className='px-3 py-2.5'>
                    <div className='flex items-center justify-end gap-1'>
                      <Button
                        variant='ghost'
                        size='sm'
                        className='h-7 gap-1 px-2 text-xs'
                        onClick={() => onRowClick(report)}
                      >
                        <ExternalLink aria-hidden='true' className='size-3.5' />
                        查看
                      </Button>
                      <Button
                        variant='ghost'
                        size='sm'
                        className='h-7 gap-1 px-2 text-xs'
                        onClick={() => handleCopyLink(report)}
                      >
                        <Copy aria-hidden='true' className='size-3.5' />
                        复制链接
                      </Button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
