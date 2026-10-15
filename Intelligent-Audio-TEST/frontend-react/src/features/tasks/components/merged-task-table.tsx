/**
 * 合并任务表格（09_任务域.md §3.8：表格 + 展开源任务行）。
 * 列：任务名称（次行「合并自 {n} 个任务」）/执行状态/用例进度/创建时间/操作（行菜单）。
 * 展开行「源任务列表（{n} 个）」：每源行 名称+状态徽章+用例 n/m+创建时间+完整行操作按钮组。
 */
import { ChevronRight, GitMerge } from 'lucide-react'
import { Fragment, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { TaskListItem } from '@/domain/models/task'
import {
  formatDateTime,
  getExecutionStatusMeta,
} from '@/features/tasks/constants'
import { Progress } from '@/features/tasks/components/ui/progress'
import { TaskRowActions } from '@/features/tasks/components/task-row-actions'

export function MergedTaskTable({
  tasks,
  loading,
  onQuickView,
  onPublish,
}: {
  tasks: TaskListItem[]
  loading: boolean
  onQuickView: (task: TaskListItem) => void
  onPublish: (task: TaskListItem) => void
}) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const [expandedId, setExpandedId] = useState<number | null>(null)

  if (loading) {
    return (
      <div className='rounded-xl border'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
        ))}
      </div>
    )
  }

  if (tasks.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            <GitMerge aria-hidden='true' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>暂无合并任务</EmptyTitle>
            <EmptyDescription>
              在「日常」页签勾选多个已完成任务，点击「合并任务」创建
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </div>
    )
  }

  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
      <div className='overflow-x-auto'>
        <table className='w-full min-w-[760px] text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              <th className='w-11 px-3 py-2' />
              <th className='px-3 py-2 text-left font-medium'>任务名称</th>
              <th className='px-3 py-2 text-left font-medium'>执行状态</th>
              <th className='px-3 py-2 text-left font-medium'>用例进度</th>
              <th className='px-3 py-2 text-left font-medium'>创建时间</th>
              <th className='w-28 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              const execMeta = getExecutionStatusMeta(task.execution_status)
              const expanded = expandedId === task.id
              const completed = task.completed_cases ?? 0
              const total = task.total_cases ?? 0
              const progress = total > 0 ? Math.round((completed / total) * 100) : 0
              return (
                <Fragment key={task.id}>
                  <tr
                    key={task.id}
                    className={cn(
                      'hover:bg-muted/40 border-border/60 border-b transition-colors',
                      expanded && 'bg-muted/40'
                    )}
                  >
                    <td className='px-3 py-2'>
                      <Button
                        variant='ghost'
                        size='icon-xs'
                        aria-label={expanded ? '收起源任务' : '展开源任务'}
                        onClick={() => setExpandedId(expanded ? null : task.id)}
                      >
                        <ChevronRight
                          aria-hidden='true'
                          className={cn('size-4 transition-transform', expanded && 'rotate-90')}
                        />
                      </Button>
                    </td>
                    <td className='max-w-72 px-3 py-2'>
                      <button
                        type='button'
                        className='block max-w-full text-left'
                        onClick={() => void navigate({ to: '/tasks/$tab', params: { tab: String(task.id) } })}
                        title='查看详情'
                      >
                        <span className='block font-medium truncate'>{task.name}</span>
                        <span className='text-muted-foreground block truncate text-xs'>
                          合并自 {task.source_tasks.length} 个任务
                        </span>
                      </button>
                    </td>
                    <td className='px-3 py-2'>
                      <StatusBadge
                        label={execMeta.label}
                        variant={execMeta.variant}
                        pulse={execMeta.pulse}
                      />
                    </td>
                    <td className='min-w-28 px-3 py-2'>
                      <div className='font-mono text-xs tabular-nums'>
                        {completed}/{total}
                      </div>
                      <Progress value={progress} size='xs' className='mt-1' />
                    </td>
                    <td className='px-3 py-2 font-mono text-xs whitespace-nowrap tabular-nums'>
                      {formatDateTime(task.created_at)}
                    </td>
                    <td className='px-3 py-2 text-right'>
                      <TaskRowActions task={task} onQuickView={onQuickView} onPublish={onPublish} />
                    </td>
                  </tr>
                  {expanded && (
                    <tr key={`${task.id}-sources`} className='border-border/60 border-b'>
                      <td colSpan={6} className='bg-muted/20 px-4 py-3'>
                        <Collapsible defaultOpen>
                          <CollapsibleTrigger
                            className='text-muted-foreground hover:text-foreground flex items-center gap-1 text-xs font-medium transition-colors'
                          >
                            源任务列表（{task.source_tasks.length} 个）
                          </CollapsibleTrigger>
                          <CollapsibleContent className='mt-2'>
                            {task.source_tasks.length === 0 ? (
                              <p className='text-muted-foreground px-3 py-2 text-xs'>
                                该合并任务暂无来源任务记录
                              </p>
                            ) : (
                              <div className='flex flex-col gap-1.5'>
                                {task.source_tasks.map((source) => {
                                  const meta = getExecutionStatusMeta(source.status)
                                  return (
                                    <div
                                      key={source.id}
                                      className='hover:bg-muted/50 flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs transition-colors'
                                    >
                                      <span className='min-w-0 max-w-56 truncate font-medium'>
                                        {source.name}
                                      </span>
                                      <StatusBadge label={meta.label} variant={meta.variant} />
                                      <span className='font-mono text-muted-foreground tabular-nums'>
                                        用例 {source.completed_cases ?? 0}/{source.total_cases ?? 0}
                                      </span>
                                      <span className='text-muted-foreground font-mono tabular-nums'>
                                        {formatDateTime(source.created_at)}
                                      </span>
                                      <span className='ml-auto flex items-center gap-1.5'>
                                        {hasPermission('task:execute') && (
                                          <Button size='sm' variant='outline' className='h-6 px-2 text-xs' onClick={() => {}}>
                                            执行
                                          </Button>
                                        )}
                                        {hasPermission('report:read') && (
                                          <Button size='sm' variant='outline' className='h-6 px-2 text-xs' onClick={() => {}}>
                                            查看报告
                                          </Button>
                                        )}
                                        {hasPermission('evaluation:execute') && (
                                          <Button size='sm' variant='ghost' className='h-6 px-2 text-xs' onClick={() => {}}>
                                            重新评估
                                          </Button>
                                        )}
                                      </span>
                                    </div>
                                  )
                                })}
                              </div>
                            )}
                          </CollapsibleContent>
                        </Collapsible>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
