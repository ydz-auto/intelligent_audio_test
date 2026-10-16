/**
 * 报告卡片视图（规范 §3.5：ModelCardGrid 同款卡片栅格；列 meta 出卡）。
 * 报告名/类型/状态/通过率/用例数/任务/时间/操作菜单。
 */
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
import { LayoutGrid } from 'lucide-react'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { ReportListItem } from '@/domain/models/report'
import { cn } from '@/lib/utils'

import {
  formatDateTime,
  getAlgorithmLabel,
  getSuccessRateVariant,
  REPORT_STATUS_META,
  REPORT_TYPE_META,
} from '@/features/reports/constants'
import { ReportRowActions, type ReportRowAction } from './report-row-actions'

interface ReportCardGridProps {
  items: ReportListItem[]
  isLoading?: boolean
  hasError?: boolean
  totalCount?: number
  trashMode: boolean
  hasPermission: (permission: string) => boolean
  onRowAction: (report: ReportListItem, action: ReportRowAction) => void
  onCardClick: (report: ReportListItem) => void
  onClearFilters?: () => void
  onRetry?: () => void
  /** 空态 CTA（「生成报告」等；undefined 不渲染） */
  emptyAction?: React.ReactNode
}

export function ReportCardGrid({
  items,
  isLoading,
  hasError,
  totalCount = 0,
  trashMode,
  hasPermission,
  onRowAction,
  onCardClick,
  onClearFilters,
  onRetry,
  emptyAction,
}: ReportCardGridProps) {
  if (isLoading && items.length === 0) {
    return (
      <div aria-busy='true' className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className='bg-card rounded-2xl border p-4'>
            <Skeleton className='h-5 w-2/3' />
            <Skeleton className='mt-2 h-4 w-1/3' />
            <Skeleton className='mt-4 h-4 w-3/4' />
            <Skeleton className='mt-2 h-4 w-1/2' />
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
            <LayoutGrid className='size-4' />
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
            <LayoutGrid className='size-4' />
          </EmptyMedia>
          <EmptyTitle>
            {trashMode ? '回收站是空的' : totalCount === 0 ? '暂无报告' : '未找到匹配报告'}
          </EmptyTitle>
          <EmptyDescription>
            {trashMode
              ? '删除的报告会保留在这里，可恢复或彻底删除'
              : totalCount === 0
                ? '测试任务执行完成后生成的报告将在此展示'
                : '换个关键词或清除筛选条件试试'}
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          {emptyAction}
          {onClearFilters && (
            <Button variant='outline' size='sm' onClick={onClearFilters}>
              清除全部筛选
            </Button>
          )}
        </EmptyContent>
      </Empty>
    )
  }
  return (
    <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
      {items.map((report) => {
        const typeMeta = REPORT_TYPE_META[report.type]
        const statusMeta = REPORT_STATUS_META[report.status]
        const rateVariant = getSuccessRateVariant(report.summary.pass_rate)
        return (
          <Card
            key={report.id}
            size='sm'
            className='hover:bg-muted/30 cursor-pointer transition-colors'
            onClick={() => onCardClick(report)}
          >
            <CardHeader>
              <CardTitle className='truncate text-sm font-medium'>
                {report.name}
              </CardTitle>
              <CardDescription className='flex items-center gap-2'>
                <StatusBadge label={typeMeta.label} variant={typeMeta.variant} />
                <StatusBadge label={statusMeta.label} variant={statusMeta.variant} />
              </CardDescription>
              <CardAction onClick={(event) => event.stopPropagation()}>
                <ReportRowActions
                  report={report}
                  trashMode={trashMode}
                  hasPermission={hasPermission}
                  onAction={(action) => onRowAction(report, action)}
                />
              </CardAction>
            </CardHeader>
            <CardContent className='flex flex-col gap-2'>
              <div className='flex items-center justify-between gap-2 text-xs'>
                <span className='text-muted-foreground truncate'>
                  {report.type === 'task'
                    ? report.task_name
                    : `${report.summary.task_count ?? 0} 个任务对比`}
                </span>
                <Badge variant='secondary' className='shrink-0'>
                  {getAlgorithmLabel(report.algorithm_type)}
                </Badge>
              </div>
              <div className='flex items-center gap-3 text-xs'>
                <span className='text-muted-foreground'>通过率</span>
                <span
                  className={cn(
                    'font-mono font-semibold tabular-nums',
                    report.summary.pass_rate > 0 &&
                      (rateVariant === 'success'
                        ? 'text-success'
                        : rateVariant === 'warning'
                          ? 'text-warning'
                          : 'text-destructive')
                  )}
                >
                  {report.summary.pass_rate > 0
                    ? `${report.summary.pass_rate.toFixed(1)}%`
                    : '—'}
                </span>
                <span className='text-muted-foreground ml-auto'>用例</span>
                <span className='font-mono tabular-nums'>
                  {report.type === 'task'
                    ? report.summary.total_cases
                    : `${report.summary.task_count ?? 0} 任务`}
                </span>
              </div>
              <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                {formatDateTime(report.created_at)}
              </span>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
