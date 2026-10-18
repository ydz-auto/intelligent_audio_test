/**
 * ③ 最近任务面板（04_控制台.md §3.6，PanelWrapper 形态）。
 * 真实数据源 GET /home/stats/summary recent_tasks（INT-728 接线）；
 * 加载/空态由 React Query 态驱动（PanelWrapper loading Skeleton / empty 空态）。
 */
import { Link } from '@tanstack/react-router'
import { ClipboardList } from 'lucide-react'

import { useDashboardSummary } from '@/application/dashboard/use-dashboard-summary'
import { Badge } from '@/components/ui/badge'
import { IconBadge } from '@/components/ui/icon-badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { usePermissions } from '@/application/hooks/use-permissions'
import {
  formatDateTime,
  getAlgorithmTypeLabel,
  getTaskStatusMeta,
} from '@/features/dashboard/constants'
import { PanelWrapper } from '@/features/dashboard/components/ui/panel-wrapper'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { cn } from '@/lib/utils'

export function RecentTasksPanel() {
  const { hasPermission } = usePermissions()
  const summaryQuery = useDashboardSummary()

  const tasks = summaryQuery.data?.recentTasks ?? []
  const loading = summaryQuery.isLoading
  const empty = !loading && tasks.length === 0

  return (
    <PanelWrapper
      title={
        <span className='flex items-center gap-2'>
          <IconBadge tone='info' size='sm'>
            <ClipboardList />
          </IconBadge>
          最近任务
        </span>
      }
      description='最新创建的 5 个任务'
      loading={loading}
      empty={empty}
      emptyMessage='发起第一次测试后，最近任务会显示在这里'
      height='h-72'
      contentClassName='p-0'
      headerActions={
        <div className='flex flex-wrap items-center gap-2'>
          {hasPermission('task:read') && (
            <Link
              to='/tasks'
              className='text-muted-foreground hover:text-foreground text-xs font-medium transition-colors'
            >
              查看全部
            </Link>
          )}
        </div>
      }
    >
      <ScrollArea className='h-72'>
        <div>
          {tasks.map((task, index) => {
            const statusMeta = getTaskStatusMeta(task.status)
            const algorithmLabel = getAlgorithmTypeLabel(task.algorithmType)
            return (
              // TODO(API 接线): 行点击 → /tasks/{id}，详情路由随 INT-354 任务域卡落定
              <button
                key={task.id}
                type='button'
                className={cn(
                  'hover:bg-muted/40 block w-full px-3 py-2.5 text-left transition-colors sm:px-5 sm:py-3',
                  index < tasks.length - 1 && 'border-border/60 border-b'
                )}
              >
                <div className='flex items-center justify-between gap-3'>
                  <p className='line-clamp-1 text-sm font-medium'>{task.name}</p>
                  <div className='flex shrink-0 items-center gap-2'>
                    {algorithmLabel && (
                      <Badge variant='outline'>{algorithmLabel}</Badge>
                    )}
                    <StatusBadge
                      label={statusMeta.label}
                      variant={statusMeta.variant}
                      pulse={statusMeta.pulse}
                    />
                  </div>
                </div>
                <div className='text-muted-foreground/60 mt-1 text-xs tabular-nums'>
                  用例 {task.completedCases}/{task.totalCases} ·{' '}
                  {formatDateTime(task.createdAt)}
                </div>
              </button>
            )
          })}
        </div>
      </ScrollArea>
    </PanelWrapper>
  )
}
