/**
 * 报告展示页卡片视图（15_报告域.md §2.1：卡片栅格，仅已发布展示）。
 * 卡片=类型徽标 + 报告名 + 算法 + 通过率 + 用例数 + 创建时间 + 「查看/复制链接」。
 * 骨架/错误态/空态与列表视图对齐（§2.1「暂无已发布报告」+ ErrorState + 卡片骨架）。
 */
import { ArrowUpDown, Copy, ExternalLink } from 'lucide-react'
import { toast } from 'sonner'

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
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

interface ReportShowcaseCardGridProps {
  items: ReportListItem[]
  isLoading?: boolean
  hasError?: boolean
  onRetry?: () => void
  onCardClick: (report: ReportListItem) => void
}

export function ReportShowcaseCardGrid({
  items,
  isLoading,
  hasError,
  onRetry,
  onCardClick,
}: ReportShowcaseCardGridProps) {
  if (isLoading && items.length === 0) {
    return (
      <div aria-busy='true' className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
        {Array.from({ length: 6 }).map((_, index) => (
          <Card key={index} size='sm'>
            <CardHeader>
              <div className='flex items-start justify-between gap-2'>
                <Skeleton className='h-5 w-16' />
                <Skeleton className='h-5 w-24' />
              </div>
              <Skeleton className='h-5 w-3/4' />
              <Skeleton className='h-4 w-full' />
            </CardHeader>
            <CardContent>
              <div className='flex items-center justify-between gap-2'>
                <Skeleton className='h-4 w-24' />
                <Skeleton className='h-7 w-24' />
              </div>
            </CardContent>
          </Card>
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
    <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
      {items.map((report) => {
        const typeMeta = getReportTypeMeta(report.type)
        const rateVariant = getSuccessRateVariant(report.summary.pass_rate)
        return (
          <Card
            key={report.id}
            size='sm'
            className='hover:bg-muted/30 cursor-pointer transition-colors'
            onClick={() => onCardClick(report)}
          >
            <CardHeader>
              <div className='flex items-start justify-between gap-2'>
                <StatusBadge label={typeMeta.label} variant={typeMeta.variant} />
                <Badge variant='secondary'>{getAlgorithmLabel(report.algorithm_type)}</Badge>
              </div>
              <CardTitle className='truncate text-sm font-medium'>
                {report.name}
              </CardTitle>
              <CardDescription className='line-clamp-2'>
                {report.description}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className='flex items-center justify-between gap-2'>
                <div className='text-muted-foreground flex items-center gap-3 text-xs tabular-nums'>
                  <span className={rateVariant === 'success' ? 'text-success' : rateVariant === 'warning' ? 'text-warning' : ''}>
                    通过率{' '}
                    {report.summary.pass_rate > 0
                      ? `${report.summary.pass_rate.toFixed(1)}%`
                      : '—'}
                  </span>
                  <span>
                    {(report.type === 'comparison' || report.type === 'secondary_comparison') &&
                    report.summary.task_count !== undefined
                      ? `${report.summary.task_count} 任务`
                      : `${report.summary.total_cases} 用例`}
                  </span>
                  <span className='font-mono'>{formatDateTime(report.created_at)}</span>
                </div>
                <CardAction>
                  <div className='flex items-center gap-1' onClick={(e) => e.stopPropagation()}>
                    <Button
                      variant='ghost'
                      size='sm'
                      className='h-7 gap-1 px-2 text-xs'
                      onClick={() => onCardClick(report)}
                    >
                      <ExternalLink aria-hidden='true' className='size-3.5' />
                      查看
                    </Button>
                    <Button
                      variant='ghost'
                      size='sm'
                      className='h-7 gap-1 px-2 text-xs'
                      aria-label='复制链接'
                      onClick={() => handleCopyLink(report)}
                    >
                      <Copy aria-hidden='true' className='size-3.5' />
                    </Button>
                  </div>
                </CardAction>
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
