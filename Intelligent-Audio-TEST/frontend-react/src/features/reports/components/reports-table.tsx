/**
 * 报告列表数据表（规范 §3.6 DataTablePage 语义，用基座 ui/ 原语实现——基座未移植
 * newAPI data-table 全家桶，本卡以等价 HTML table + 语义 token 落地）：
 * 列=勾选/名称(次行类型+任务名)/状态/类型/算法/通过率/用例数/创建时间/操作；
 * 行 hover:bg-muted/30 cursor-pointer → 查看；空态/加载骨架见下。
 */
import { ArrowUpDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
import { cn } from '@/lib/utils'

import {
  formatDateTime,
  getAlgorithmLabel,
  getSuccessRateVariant,
  REPORT_STATUS_META,
  REPORT_TYPE_META,
} from '@/features/reports/constants'
import { ReportRowActions, type ReportRowAction } from './report-row-actions'

interface ReportsTableProps {
  items: ReportListItem[]
  isLoading?: boolean
  totalCount: number
  trashMode: boolean
  selectedIds: number[]
  onToggleRow: (id: number) => void
  onToggleAll: () => void
  hasPermission: (permission: string) => boolean
  onRowAction: (report: ReportListItem, action: ReportRowAction) => void
  onRowClick: (report: ReportListItem) => void
  onClearFilters: () => void
}

export function ReportsTable({
  items,
  isLoading,
  totalCount,
  trashMode,
  selectedIds,
  onToggleRow,
  onToggleAll,
  hasPermission,
  onRowAction,
  onRowClick,
  onClearFilters,
}: ReportsTableProps) {
  const allVisibleSelected = items.length > 0 && items.every((i) => selectedIds.includes(i.id))

  if (isLoading && items.length === 0) {
    return (
      <div aria-busy='true' className='overflow-hidden rounded-lg border'>
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className='flex gap-4 border-b p-4 last:border-0'>
            <Skeleton className='h-4 w-4' />
            <Skeleton className='h-5 w-48 max-w-full' />
            <Skeleton className='h-5 flex-1' />
            <Skeleton className='h-5 w-20' />
          </div>
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <Empty className='min-h-[320px] border-dashed'>
        <EmptyHeader>
          <EmptyMedia variant='icon'>
            <ArrowUpDown className='size-4' />
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
          <Button variant='outline' size='sm' onClick={onClearFilters}>
            清除全部筛选
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  return (
    <div className='overflow-hidden rounded-lg border'>
      <div className='overflow-x-auto'>
        <table className='w-full min-w-[720px] text-sm'>
          <thead>
            <tr className='text-muted-foreground border-b bg-muted/30'>
              <th className='w-11 px-3 py-2.5 text-left'>
                <Checkbox
                  aria-label='全选'
                  checked={allVisibleSelected}
                  onCheckedChange={onToggleAll}
                />
              </th>
              <th className='px-3 py-2.5 text-left font-medium'>名称</th>
              <th className='px-3 py-2.5 text-left font-medium'>状态</th>
              <th className='px-3 py-2.5 text-left font-medium'>类型</th>
              <th className='px-3 py-2.5 text-left font-medium'>算法</th>
              <th className='px-3 py-2.5 text-left font-medium'>通过率</th>
              <th className='px-3 py-2.5 text-left font-medium'>用例数</th>
              <th className='px-3 py-2.5 text-left font-medium'>创建时间</th>
              <th className='w-12 px-3 py-2.5' />
            </tr>
          </thead>
          <tbody>
            {items.map((report) => {
              const typeMeta = REPORT_TYPE_META[report.type]
              const statusMeta = REPORT_STATUS_META[report.status]
              const isSelected = selectedIds.includes(report.id)
              const passRate = report.summary.pass_rate
              return (
                <tr
                  key={report.id}
                  onClick={() => onRowClick(report)}
                  className={cn(
                    'hover:bg-muted/30 cursor-pointer border-b transition-colors last:border-0',
                    isSelected && 'bg-primary/5'
                  )}
                >
                  <td
                    className='px-3 py-3'
                    onClick={(event) => event.stopPropagation()}
                  >
                    <Checkbox
                      aria-label={`选择报告 ${report.name}`}
                      checked={isSelected}
                      onCheckedChange={() => onToggleRow(report.id)}
                    />
                  </td>
                  <td className='max-w-[240px] px-3 py-3'>
                    <div className='truncate font-medium'>{report.name}</div>
                    <div className='text-muted-foreground truncate text-xs'>
                      {report.type === 'task'
                        ? report.task_name
                        : `${report.summary.task_count ?? 0} 个任务对比`}
                    </div>
                  </td>
                  <td className='px-3 py-3'>
                    <StatusBadge label={statusMeta.label} variant={statusMeta.variant} />
                  </td>
                  <td className='px-3 py-3'>
                    <StatusBadge label={typeMeta.label} variant={typeMeta.variant} />
                  </td>
                  <td className='px-3 py-3'>
                    {report.algorithm_type ? (
                      <Badge variant='secondary'>{getAlgorithmLabel(report.algorithm_type)}</Badge>
                    ) : (
                      <span className='text-muted-foreground/50 text-xs'>—</span>
                    )}
                  </td>
                  <td className='px-3 py-3'>
                    {report.type === 'task' ? (
                      <span
                        className={cn(
                          'font-mono font-semibold tabular-nums',
                          report.summary.pass_rate > 0 &&
                            (getSuccessRateVariant(report.summary.pass_rate) === 'success'
                              ? 'text-success'
                              : getSuccessRateVariant(report.summary.pass_rate) === 'warning'
                                ? 'text-warning'
                                : 'text-destructive')
                        )}
                      >
                        {passRate > 0 ? `${passRate.toFixed(1)}%` : '—'}
                      </span>
                    ) : (
                      <span className='text-muted-foreground/50 text-xs'>—</span>
                    )}
                  </td>
                  <td className='px-3 py-3'>
                    <span className='font-mono tabular-nums'>
                      {report.type === 'task'
                        ? report.summary.total_cases
                        : `${report.summary.task_count ?? 0} 任务`}
                    </span>
                  </td>
                  <td className='px-3 py-3'>
                    <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                      {formatDateTime(report.created_at)}
                    </span>
                  </td>
                  <td
                    className='px-3 py-3 text-right'
                    onClick={(event) => event.stopPropagation()}
                  >
                    <ReportRowActions
                      report={report}
                      trashMode={trashMode}
                      hasPermission={hasPermission}
                      onAction={(action) => onRowAction(report, action)}
                    />
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
