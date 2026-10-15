/**
 * ③ 最近任务面板（04_控制台.md §3.6，PanelWrapper 形态）。
 * mock 8 行覆盖状态徽章五色（success/info/warning/danger/neutral + merged=chart-4）；
 * 头部「状态演示」切换为视觉稿两态演示控件（loading Skeleton / 空态）——接线后移除。
 */
import { Link } from '@tanstack/react-router'
import { ClipboardList } from 'lucide-react'
import { useState } from 'react'

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

type DemoState = 'data' | 'loading' | 'empty'

const DEMO_STATE_OPTIONS: Array<{ value: DemoState; label: string }> = [
  { value: 'data', label: '数据' },
  { value: 'loading', label: '加载中' },
  { value: 'empty', label: '空态' },
]

function DemoStateSwitch(props: {
  value: DemoState
  onChange: (value: DemoState) => void
}) {
  return (
    <div className='bg-muted/60 inline-flex h-7 items-center rounded-lg border p-0.5'>
      <span className='text-muted-foreground px-2 text-[11px] font-medium'>
        状态演示
      </span>
      {DEMO_STATE_OPTIONS.map((option) => (
        <button
          key={option.value}
          type='button'
          onClick={() => props.onChange(option.value)}
          className={cn(
            'shrink-0 rounded-md px-2.5 text-xs font-medium transition-colors',
            props.value === option.value
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function RecentTasksPanel() {
  const { hasPermission } = usePermissions()
  const summaryQuery = useDashboardSummary()
  // 两态演示控件默认「数据」——React Query 侧另有 loading 分支（mock 即时返回，不触发）
  const [demoState, setDemoState] = useState<DemoState>('data')

  const tasks = summaryQuery.data?.recent_tasks ?? []
  const loading = demoState === 'loading' || summaryQuery.isLoading
  const empty = demoState === 'empty' || (!loading && tasks.length === 0)

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
      description='最新创建的 5 个任务（视觉稿 mock 8 行，覆盖状态徽章五色）'
      loading={loading}
      empty={empty}
      emptyMessage='发起第一次测试后，最近任务会显示在这里'
      height='h-72'
      contentClassName='p-0'
      headerActions={
        <div className='flex flex-wrap items-center gap-2'>
          <DemoStateSwitch value={demoState} onChange={setDemoState} />
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
            const algorithmLabel = getAlgorithmTypeLabel(task.algorithm_type)
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
                  用例 {task.completed_cases}/{task.total_cases} ·{' '}
                  {formatDateTime(task.created_at)}
                </div>
              </button>
            )
          })}
        </div>
      </ScrollArea>
    </PanelWrapper>
  )
}
