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
  trashMode: boolean
  hasPermission: (permission: string) => boolean
  onRowAction: (report: ReportListItem, action: ReportRowAction) => void
  onCardClick: (report: ReportListItem) => void
}

export function ReportCardGrid({
  items,
  trashMode,
  hasPermission,
  onRowAction,
  onCardClick,
}: ReportCardGridProps) {
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
