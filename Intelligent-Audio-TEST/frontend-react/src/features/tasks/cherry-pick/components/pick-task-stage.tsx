/**
 * 挑选阶段 1 · 选择任务（18_挑选合并交互重设计.md §3.8.2，INT-1047）。
 * 搜索（任务名）+ 多选 + 全选当前筛选 + 清空 + 下一步：选择结果；
 * 任务行 = Checkbox + 任务名 + 执行状态 StatusBadge + 结果计数「{n} 条」+ 创建时间（mono）。
 * 数据源 = 候选行聚合的可挑选终态任务集合（§3.8.2，按状态/名称排序）。
 */
import { ArrowRight, Search, TriangleAlert } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { formatPickDateTime } from '@/features/tasks/cherry-pick/constants'
import { cn } from '@/lib/utils'

/** 阶段 1 任务行（候选行按 taskId 聚合） */
export interface PickTaskRow {
  taskId: number
  taskName: string
  executionStatus: string
  createdAt: string | null
  count: number
}

export interface PickTaskStageProps {
  tasks: PickTaskRow[]
  selectedTaskIds: ReadonlySet<number>
  loading: boolean
  isError: boolean
  onRetry: () => void
  onToggle: (taskId: number) => void
  /** 全选当前筛选（传入搜索命中集） */
  onSelectAll: (taskIds: number[]) => void
  onClear: () => void
  onNext: () => void
}

/** 终态排序权重（§3.8.2 按状态/名称排序：已完成 → 执行失败 → 已停止） */
export function getTaskStatusOrder(status: string): number {
  switch (status) {
    case 'completed':
      return 0
    case 'failed':
      return 1
    case 'stopped':
      return 2
    default:
      return 3
  }
}

export function PickTaskStage({
  tasks,
  selectedTaskIds,
  loading,
  isError,
  onRetry,
  onToggle,
  onSelectAll,
  onClear,
  onNext,
}: PickTaskStageProps) {
  const [search, setSearch] = useState('')
  const kw = search.trim().toLowerCase()

  const filtered = useMemo(() => {
    if (!kw) return tasks
    return tasks.filter((t) => t.taskName.toLowerCase().includes(kw))
  }, [tasks, kw])

  const selectedCount = selectedTaskIds.size

  return (
    <div className='flex min-h-0 flex-1 flex-col gap-3'>
      <h3 className='text-sm font-medium'>挑选 · 阶段 1：选择任务</h3>
      <div className='flex flex-wrap items-center gap-2'>
        <div className='bg-muted/60 flex items-center gap-1.5 rounded-lg px-2 py-1'>
          <Search aria-hidden='true' className='text-muted-foreground size-3.5' />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder='搜索任务名称'
            className='h-6 w-52 text-[0.8rem]'
            aria-label='搜索任务名称'
          />
        </div>
        <span className='text-muted-foreground text-xs'>
          已选 <span className='font-medium'>{selectedCount}</span> 个任务
        </span>
        <span className='text-muted-foreground/70 ml-auto text-xs'>
          仅已完成、执行失败、已停止的终态任务可挑选
        </span>
      </div>

      <div className='min-h-0 flex-1 overflow-auto rounded-lg border'>
        {loading ? (
          <div className='flex flex-col gap-2 p-3'>
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className='h-9 w-full' />
            ))}
          </div>
        ) : isError ? (
          <div className='flex flex-col items-center gap-2 py-10 text-center'>
            <TriangleAlert aria-hidden='true' className='text-destructive size-6' />
            <p className='text-muted-foreground text-sm'>可挑选任务加载失败，请重试</p>
            <Button variant='outline' size='sm' className='mt-1' onClick={onRetry}>
              重试
            </Button>
          </div>
        ) : filtered.length === 0 ? (
          <div className='flex flex-col items-center gap-1 py-10 text-center'>
            <p className='text-muted-foreground text-sm'>
              {kw ? '没有符合搜索条件的任务' : '暂无可挑选的终态任务'}
            </p>
            <p className='text-muted-foreground/70 text-xs'>
              仅已完成、执行失败、已停止的终态任务可挑选
            </p>
          </div>
        ) : (
          <div className='flex flex-col p-2'>
            {filtered.map((task) => {
              const selected = selectedTaskIds.has(task.taskId)
              const statusLabel =
                task.executionStatus === 'completed'
                  ? '已完成'
                  : task.executionStatus === 'failed'
                    ? '执行失败'
                    : '已停止'
              const statusVariant =
                task.executionStatus === 'completed'
                  ? 'success'
                  : task.executionStatus === 'failed'
                    ? 'danger'
                    : 'neutral'
              return (
                <div
                  key={task.taskId}
                  data-testid={`pick-task-${task.taskId}`}
                  className={cn(
                    'hover:bg-muted/40 flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition-colors',
                    selected && 'bg-accent/40'
                  )}
                >
                  <Checkbox
                    checked={selected}
                    onCheckedChange={() => onToggle(task.taskId)}
                    aria-label={`选择任务 ${task.taskName}`}
                  />
                  <span className='min-w-0 flex-1 truncate font-medium'>
                    {task.taskName}
                  </span>
                  <StatusBadge label={statusLabel} variant={statusVariant} />
                  <Badge variant='secondary' className='shrink-0 font-mono text-[10px]'>
                    {task.count} 条
                  </Badge>
                  <span className='text-muted-foreground shrink-0 font-mono text-[10px] whitespace-nowrap tabular-nums'>
                    {formatPickDateTime(task.createdAt)}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className='flex flex-wrap items-center justify-between gap-2'>
        <div className='flex items-center gap-2'>
          <Button
            variant='outline'
            size='sm'
            disabled={filtered.length === 0}
            onClick={() => onSelectAll(filtered.map((t) => t.taskId))}
          >
            全选当前筛选
          </Button>
          <Button
            variant='ghost'
            size='sm'
            className='text-muted-foreground'
            disabled={selectedCount === 0}
            onClick={onClear}
          >
            清空
          </Button>
        </div>
        <Button
          size='sm'
          className='gap-1.5'
          disabled={selectedCount === 0}
          onClick={onNext}
        >
          <span>下一步：选择结果（{selectedCount}）</span>
          <ArrowRight aria-hidden='true' className='size-3.5' />
        </Button>
      </div>
    </div>
  )
}
