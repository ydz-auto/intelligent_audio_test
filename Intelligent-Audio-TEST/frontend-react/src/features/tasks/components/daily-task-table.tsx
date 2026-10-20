/**
 * 日常任务表格（09_任务域.md §3.6，DataTablePage 骨架的轻量语义表格实现）。
 * 列：选择/任务名称/执行状态/评估状态/类型/用例进度/设备·API/标签/创建时间/操作。
 * 单元格 `py-2`、字号 13px；数值列 mono tabular-nums；回收站行 DISABLED_ROW（muted 底 + 左标线）。
 * 排序头/列显隐为演示控件（接线后接服务端 sortBy/sortOrder + useTableUrlState）。
 */
import { ClipboardList, RefreshCw, Star, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'

import { usePermissions } from '@/application/hooks/use-permissions'
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { TaskListItem } from '@/domain/models/task'
import {
  deriveTaskType,
  formatDateTime,
  getEvaluationStatusMeta,
  getExecutionStatusMeta,
  getTaskTypeLabel,
} from '@/features/tasks/constants'
import { Progress } from '@/features/tasks/components/ui/progress'
import { TaskBulkActions } from '@/features/tasks/components/task-bulk-actions'
import { TaskRowActions } from '@/features/tasks/components/task-row-actions'

/** 列显隐选项（视图下拉，§3.5） */
const COLUMN_OPTIONS = [
  { key: 'name', label: '任务名称' },
  { key: 'execution', label: '执行状态' },
  { key: 'evaluation', label: '评估状态' },
  { key: 'type', label: '类型' },
  { key: 'progress', label: '用例进度' },
  { key: 'resources', label: '设备/API' },
  { key: 'tags', label: '标签' },
  { key: 'createdAt', label: '创建时间' },
] as const

type ColumnKey = (typeof COLUMN_OPTIONS)[number]['key']

const DEFAULT_VISIBLE: ColumnKey[] = [
  'name',
  'execution',
  'evaluation',
  'type',
  'progress',
  'tags',
  'createdAt',
]

function TagCell({ tags }: { tags: string[] }) {
  if (tags.length === 0) return <span className='text-muted-foreground'>—</span>
  const visible = tags.slice(0, 2)
  return (
    <div className='flex flex-wrap items-center gap-1'>
      {visible.map((tag) => (
        <Badge key={tag} variant='outline' className='rounded-md px-1.5'>
          {tag}
        </Badge>
      ))}
      {tags.length > 2 && (
        <Badge variant='secondary' className='rounded-md px-1.5'>
          +{tags.length - 2}
        </Badge>
      )}
    </div>
  )
}

function SortableHeader({ label, active }: { label: string; active?: boolean }) {
  return (
    <button
      type='button'
      className={cn(
        'hover:text-foreground inline-flex items-center gap-1 text-xs font-medium transition-colors',
        active ? 'text-foreground' : 'text-muted-foreground'
      )}
      title='演示排序控件（接线后接服务端 sortBy/sortOrder）'
    >
      {label}
      <span aria-hidden='true' className='text-muted-foreground/50 text-[10px]'>
        ⇅
      </span>
    </button>
  )
}

function ViewOptions({
  visible,
  onChange,
}: {
  visible: Set<ColumnKey>
  onChange: (visible: Set<ColumnKey>) => void
}) {
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant='outline' size='sm' className='h-8 gap-1.5 px-2.5 font-normal' />
        }
      >
        <span className='text-muted-foreground'>视图</span>
        <span className='font-medium'>切换列</span>
      </PopoverTrigger>
      <PopoverContent align='end' className='min-w-40 p-1.5'>
        {COLUMN_OPTIONS.map((option) => {
          const checked = visible.has(option.key)
          return (
            <label
              key={option.key}
              className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors'
            >
              <Checkbox
                checked={checked}
                onCheckedChange={() => {
                  const next = new Set(visible)
                  if (checked) next.delete(option.key)
                  else next.add(option.key)
                  onChange(next)
                }}
              />
              {option.label}
            </label>
          )
        })}
      </PopoverContent>
    </Popover>
  )
}

export function DailyTaskTable({
  tasks,
  loading,
  error,
  onRetry,
  trash,
  onQuickView,
  onPublish,
  onBatchPublish,
  onJoinPick,
  selected,
  onSelectionChange,
  onCreate,
}: {
  tasks: TaskListItem[]
  loading: boolean
  /** 列表请求失败（P1-3：错误态 + 重试，不再渲染空态） */
  error?: boolean
  onRetry?: () => void
  trash: boolean
  onQuickView: (task: TaskListItem) => void
  onPublish: (task: TaskListItem) => void
  onBatchPublish: (tasks: TaskListItem[]) => void
  /** 加入挑选（§2.2 裁定②） */
  onJoinPick?: (tasks: TaskListItem[]) => void
  /** 勾选任务 id 集（受控：18 §3.8.1 工具栏「开始挑选」读取预选） */
  selected: Set<number>
  onSelectionChange: (next: Set<number>) => void
  onCreate: () => void
}) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const [visible, setVisible] = useState<Set<ColumnKey>>(
    () => new Set(DEFAULT_VISIBLE)
  )

  const toggleRow = (id: number, checked: boolean) => {
    const next = new Set(selected)
    if (checked) next.add(id)
    else next.delete(id)
    onSelectionChange(next)
  }

  const toggleAll = (checked: boolean) => {
    onSelectionChange(checked ? new Set(tasks.map((t) => t.id)) : new Set())
  }

  const allChecked = tasks.length > 0 && tasks.every((t) => selected.has(t.id))
  const col = (key: ColumnKey) => visible.has(key)

  if (loading) {
    return (
      <div className='rounded-xl border'>
        <Skeleton className='h-10 w-full rounded-none border-b' />
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className='h-12 w-full rounded-none border-b' />
        ))}
      </div>
    )
  }

  // P1-3：请求失败渲染错误态 + 重试（不再误示为空态）
  if (error) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            <RefreshCw aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>任务列表加载失败</EmptyTitle>
            <EmptyDescription>请检查网络或后端服务后重试</EmptyDescription>
            {onRetry && (
              <EmptyContent>
                <Button variant='outline' size='sm' onClick={onRetry}>
                  重试
                </Button>
              </EmptyContent>
            )}
          </EmptyHeader>
        </Empty>
      </div>
    )
  }

  if (tasks.length === 0) {
    return (
      <div className='bg-card ring-foreground/10 rounded-xl py-8 ring-1'>
        <Empty className='h-[400px]'>
          <EmptyMedia variant='icon'>
            {trash ? <Trash2 aria-hidden='true' /> : <ClipboardList aria-hidden='true' />}
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>{trash ? '回收站为空' : '暂无测试任务'}</EmptyTitle>
            <EmptyDescription>
              {trash
                ? '回收站中的任务会显示在这里'
                : '点击右上角「创建新任务」发起第一次测试，或调整筛选条件'}
            </EmptyDescription>
          </EmptyHeader>
          {!trash && hasPermission('task:create') && (
            <EmptyContent>
              <Button size='sm' onClick={onCreate}>
                + 创建新任务
              </Button>
            </EmptyContent>
          )}
        </Empty>
      </div>
    )
  }

  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl ring-1'>
      {/* 工具栏（搜索已并入筛选栏，此处仅视图选项与选择计数） */}
      <div className='flex items-center justify-between gap-2 border-b px-3 py-2'>
        <p className='text-muted-foreground text-xs'>
          {selected.size > 0 ? `已选择 ${selected.size} 个任务` : '全选以进行批量操作'}
        </p>
        <ViewOptions visible={visible} onChange={setVisible} />
      </div>

      <div className='overflow-x-auto'>
        <table className='w-full min-w-[860px] text-[13px]'>
          <thead>
            <tr className='bg-[var(--table-header)] text-xs'>
              <th className='w-11 px-3 py-2'>
                <Checkbox
                  checked={allChecked}
                  aria-label='全选'
                  onCheckedChange={toggleAll}
                />
              </th>
              {col('name') && (
                <th className='px-3 py-2 text-left font-medium'>
                  <SortableHeader label='任务名称' active />
                </th>
              )}
              {col('execution') && (
                <th className='px-3 py-2 text-left font-medium'>
                  <SortableHeader label='执行状态' />
                </th>
              )}
              {col('evaluation') && (
                <th className='px-3 py-2 text-left font-medium'>评估状态</th>
              )}
              {col('type') && (
                <th className='px-3 py-2 text-left font-medium'>类型</th>
              )}
              {col('progress') && (
                <th className='px-3 py-2 text-left font-medium'>用例进度</th>
              )}
              {col('resources') && (
                <th className='px-3 py-2 text-left font-medium'>设备/API</th>
              )}
              {col('tags') && (
                <th className='px-3 py-2 text-left font-medium'>标签</th>
              )}
              {col('createdAt') && (
                <th className='px-3 py-2 text-left font-medium'>
                  <SortableHeader label='创建时间' active />
                </th>
              )}
              <th className='w-28 px-3 py-2 text-right font-medium'>操作</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => {
              const execMeta = getExecutionStatusMeta(task.execution_status)
              const evalMeta = getEvaluationStatusMeta(task.evaluation_status)
              const disabled = task.deleted
              const completed = task.completed_cases ?? 0
              const total = task.total_cases ?? 0
              const failed = task.failed_cases ?? 0
              const progress =
                total > 0 ? Math.round((completed / total) * 100) : 0
              const failedProgress =
                total > 0 ? Math.round((failed / total) * 100) : 0

              return (
                <tr
                  key={task.id}
                  data-state={selected.has(task.id) ? 'selected' : undefined}
                  className={cn(
                    'hover:bg-muted/40 border-border/60 border-b transition-colors',
                    selected.has(task.id) && 'bg-accent/40',
                    disabled && 'bg-[var(--table-disabled)] text-muted-foreground',
                    disabled && '[&>td:first-child]:border-l-4 [&>td:first-child]:border-l-[var(--table-disabled-border)]'
                  )}
                >
                  <td className='px-3 py-2'>
                    <Checkbox
                      checked={selected.has(task.id)}
                      aria-label={`选择 ${task.name}`}
                      onCheckedChange={(c) => toggleRow(task.id, c)}
                    />
                  </td>
                  {col('name') && (
                    <td className='max-w-64 px-3 py-2'>
                      <button
                        type='button'
                        className='block max-w-full text-left'
                        onClick={() => void navigate({ to: '/tasks/$tab', params: { tab: String(task.id) } })}
                        title='查看详情'
                      >
                        <span className='flex items-center gap-1.5 font-medium truncate'>
                          {task.is_favorite && (
                            <Star
                              aria-hidden='true'
                              className='text-warning size-3 shrink-0 fill-current'
                            />
                          )}
                          <span className='truncate'>{task.name}</span>
                        </span>
                        <span className='text-muted-foreground block truncate'>
                          {disabled
                            ? `删除时间 ${formatDateTime(task.deleted_at)} · 删除人 ${task.deleted_by_user_id ? `用户#${task.deleted_by_user_id}` : '—'}`
                            : (task.description ?? '')}
                        </span>
                      </button>
                    </td>
                  )}
                  {col('execution') && (
                    <td className='px-3 py-2'>
                      {disabled ? (
                        <StatusBadge label='已删除' variant='danger' />
                      ) : (
                        <StatusBadge
                          label={execMeta.label}
                          variant={execMeta.variant}
                          pulse={execMeta.pulse}
                        />
                      )}
                    </td>
                  )}
                  {col('evaluation') && (
                    <td className='px-3 py-2'>
                      <StatusBadge
                        label={evalMeta.label}
                        variant={evalMeta.variant}
                        pulse={evalMeta.pulse}
                      />
                    </td>
                  )}
                  {col('type') && (
                    <td className='px-3 py-2'>
                      <Badge variant='outline' className='rounded-md px-1.5'>
                        {getTaskTypeLabel(deriveTaskType(task.device_types))}
                      </Badge>
                    </td>
                  )}
                  {col('progress') && (
                    <td className='min-w-28 px-3 py-2'>
                      <div className='font-mono text-xs tabular-nums'>
                        {completed}/{total}
                      </div>
                      <Progress
                        value={progress}
                        failedValue={failedProgress}
                        size='xs'
                        className='mt-1'
                      />
                    </td>
                  )}
                  {col('resources') && (
                    <td className='px-3 py-2 text-muted-foreground whitespace-nowrap'>
                      {task.device_count ? `${task.device_count} 设备` : ''}
                      {task.device_count && task.api_count ? ' · ' : ''}
                      {task.api_count ? `${task.api_count} API` : ''}
                      {!task.device_count && !task.api_count ? '—' : ''}
                    </td>
                  )}
                  {col('tags') && (
                    <td className='px-3 py-2'>
                      <TagCell tags={task.tags} />
                    </td>
                  )}
                  {col('createdAt') && (
                    <td className='px-3 py-2 font-mono text-xs whitespace-nowrap tabular-nums'>
                      {formatDateTime(task.created_at)}
                    </td>
                  )}
                  <td className='px-3 py-2 text-right'>
                    <TaskRowActions task={task} onQuickView={onQuickView} onPublish={onPublish} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <TaskBulkActions
        tasks={tasks}
        selected={selected}
        onClear={() => onSelectionChange(new Set())}
        trash={trash}
        onBatchPublish={onBatchPublish}
        onJoinPick={onJoinPick}
      />
    </div>
  )
}
