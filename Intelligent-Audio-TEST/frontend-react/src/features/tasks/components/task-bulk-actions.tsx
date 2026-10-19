/**
 * 批量操作浮条（09_任务域.md §3.10 DataTableBulkActions 照搬；
 * 18_挑选合并交互重设计.md §2.2 裁定②：原「合并任务」钮撤销，吸收为「加入挑选」）：
 * `fixed bottom-6 left-1/2 z-50 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2` +
 * 内层 `p-2 shadow-xl rounded-xl border bg-background/95 supports-[backdrop-filter]:bg-background/60 backdrop-blur-lg`。
 * 左起：X 清选钮（Tooltip「清除选择 (Esc)」）｜分隔｜计数 Badge +「个任务已选择」｜按钮组。
 * 日常（普通态）：批量删除/发布/任务对比（≥2）/加入挑选（task:cherry_pick，等价旧「合并任务」）/导出数据；
 * 日常（回收站态）：批量恢复/批量彻底删除。「导出数据」经 onExport 打开 §5.12 导出弹窗。
 * INT-932 接线：批量删除（POST /tasks/batch-action）、批量恢复（POST /tasks/restore）、
 * 批量彻底删除（POST /tasks/purge）经 useTaskActions 发真实请求；任务对比经 onCompare
 * 生成对比报告（reports-api.compareReports）后跳转报告页。
 */
import { LoaderCircle, X } from 'lucide-react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTaskActions } from '@/application/tasks/use-task-actions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { TaskListItem } from '@/domain/models/task'

export function TaskBulkActions({
  tasks,
  selected,
  onClear,
  trash,
  onBatchPublish,
  onJoinPick,
  onExport,
  onCompare,
}: {
  tasks: TaskListItem[]
  selected: Set<number>
  onClear: () => void
  trash: boolean
  onBatchPublish?: (tasks: TaskListItem[]) => void
  /** 加入挑选（§2.2 裁定②：打开挑选向导并预选该批任务，等价旧「合并任务」入口） */
  onJoinPick?: (tasks: TaskListItem[]) => void
  /** 导出数据 → §5.12 导出弹窗 */
  onExport: (tasks: TaskListItem[]) => void
  /** 任务对比（≥2）：生成对比报告后跳转报告页（INT-932 接线；未传回落 toast） */
  onCompare?: (tasks: TaskListItem[]) => void
}) {
  const { hasPermission } = usePermissions()
  const actions = useTaskActions()
  const count = selected.size
  if (count === 0) return null

  const selectedTasks = tasks.filter((t) => selected.has(t.id))
  const hasTerminal = selectedTasks.every((t) =>
    ['completed', 'failed', 'stopped', 'pending'].includes(t.execution_status ?? '')
  )

  const busy = actions.batchRemove.isPending || actions.batchRestore.isPending || actions.batchPurge.isPending

  return (
    <div className='fixed bottom-6 left-1/2 z-50 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2'>
      <div className='bg-background/95 supports-backdrop-filter:bg-background/60 flex items-center gap-1 rounded-xl border p-2 shadow-xl backdrop-blur-lg'>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant='ghost'
                size='icon-sm'
                aria-label='清除选择 (Esc)'
                onClick={onClear}
              />
            }
          >
            <X aria-hidden='true' />
          </TooltipTrigger>
          <TooltipContent>清除选择 (Esc)</TooltipContent>
        </Tooltip>
        <Separator orientation='vertical' className='h-5' />
        <Badge className='min-w-8 justify-center rounded-lg'>{count}</Badge>
        <span className='text-sm'>个任务已选择</span>
        <Separator orientation='vertical' className='h-5' />
        {trash ? (
          <>
            {hasPermission('task:delete') && (
              <Button
                size='sm'
                variant='outline'
                disabled={busy}
                onClick={() => {
                  actions.batchRestore.mutate(selectedTasks.map((t) => t.id))
                  onClear()
                }}
              >
                {actions.batchRestore.isPending && <LoaderCircle aria-hidden='true' className='size-3.5 animate-spin' />}
                批量恢复
              </Button>
            )}
            {hasPermission('task:delete') && (
              <Button
                size='sm'
                variant='destructive'
                disabled={busy}
                onClick={() => {
                  actions.batchPurge.mutate(selectedTasks.map((t) => t.id))
                  onClear()
                }}
              >
                {actions.batchPurge.isPending && <LoaderCircle aria-hidden='true' className='size-3.5 animate-spin' />}
                批量彻底删除
              </Button>
            )}
          </>
        ) : (
          <>
            {hasPermission('task:batch') && (
              <Button
                size='sm'
                variant='destructive'
                disabled={busy}
                onClick={() => {
                  actions.batchRemove.mutate(selectedTasks.map((t) => t.id))
                  onClear()
                }}
              >
                {actions.batchRemove.isPending && <LoaderCircle aria-hidden='true' className='size-3.5 animate-spin' />}
                批量删除
              </Button>
            )}
            {hasPermission('task:publish') && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      size='sm'
                      variant='outline'
                      disabled={!hasTerminal}
                      onClick={() =>
                        onBatchPublish
                          ? onBatchPublish(selectedTasks)
                          : toast.success('批量发布完成：成功 3 个')
                      }
                    />
                  }
                >
                  发布
                </TooltipTrigger>
                <TooltipContent>名称沿用源任务名，不可发布状态自动跳过</TooltipContent>
              </Tooltip>
            )}
            {count >= 2 && hasPermission('report:compare') && (
              <Button
                size='sm'
                variant='outline'
                onClick={() =>
                  onCompare
                    ? onCompare(selectedTasks)
                    : toast.success('已进入任务对比工作区（§6）')
                }
              >
                任务对比
              </Button>
            )}
            {hasPermission('task:cherry_pick') && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      size='sm'
                      variant='outline'
                      disabled={!selectedTasks.every((t) =>
                        ['completed', 'failed', 'stopped'].includes(t.execution_status ?? '')
                      )}
                      onClick={() =>
                        onJoinPick
                          ? onJoinPick(selectedTasks)
                          : toast.success('已加入挑选向导（任务级预选）')
                      }
                    />
                  }
                >
                  加入挑选
                </TooltipTrigger>
                <TooltipContent>仅已完成/执行失败/已停止的终态任务可挑选（等价旧「合并任务」）</TooltipContent>
              </Tooltip>
            )}
            {hasPermission('task:export') && (
              <Button
                size='sm'
                variant='outline'
                onClick={() => onExport(selectedTasks)}
              >
                导出数据
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
