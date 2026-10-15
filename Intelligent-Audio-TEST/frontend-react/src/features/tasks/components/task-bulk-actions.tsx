/**
 * 批量操作浮条（09_任务域.md §3.10 DataTableBulkActions 照搬）：
 * `fixed bottom-6 left-1/2 z-50 w-max max-w-[calc(100vw-2rem)] -translate-x-1/2` +
 * 内层 `p-2 shadow-xl rounded-xl border bg-background/95 supports-[backdrop-filter]:bg-background/60 backdrop-blur-lg`。
 * 左起：X 清选钮（Tooltip「清除选择 (Esc)」）｜分隔｜计数 Badge +「个任务已选择」｜按钮组。
 * 日常（普通态）：批量删除/发布/任务对比（≥2）/合并任务（仅已完成·已合并）/导出数据；
 * 日常（回收站态）：批量恢复/批量彻底删除。mock 态动作全部 toast 演示。
 */
import { X } from 'lucide-react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
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
}: {
  tasks: TaskListItem[]
  selected: Set<number>
  onClear: () => void
  trash: boolean
}) {
  const { hasPermission } = usePermissions()
  const count = selected.size
  if (count === 0) return null

  const selectedTasks = tasks.filter((t) => selected.has(t.id))
  const hasTerminal = selectedTasks.every((t) =>
    ['completed', 'failed', 'stopped', 'pending'].includes(t.execution_status ?? '')
  )

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
                onClick={() => toast.success('已批量恢复')}
              >
                批量恢复
              </Button>
            )}
            {hasPermission('task:delete') && (
              <Button
                size='sm'
                variant='destructive'
                onClick={() => toast.success('已批量彻底删除')}
              >
                批量彻底删除
              </Button>
            )}
          </>
        ) : (
          <>
            {hasPermission('task:delete') && (
              <Button
                size='sm'
                variant='destructive'
                onClick={() => toast.success('已移入回收站')}
              >
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
                      onClick={() => toast.success('批量发布完成：成功 3 个')}
                    />
                  }
                >
                  发布
                </TooltipTrigger>
                <TooltipContent>
                  {hasTerminal
                    ? '名称沿用源任务名，不可发布状态自动跳过'
                    : '名称沿用源任务名，不可发布状态自动跳过'}
                </TooltipContent>
              </Tooltip>
            )}
            {count >= 2 && hasPermission('report:compare') && (
              <Button
                size='sm'
                variant='outline'
                onClick={() => toast.success('已进入任务对比工作区（§6）')}
              >
                任务对比
              </Button>
            )}
            {hasPermission('task:merge') && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      size='sm'
                      variant='outline'
                      disabled={!selectedTasks.every((t) =>
                        ['completed', 'merged'].includes(t.execution_status ?? '')
                      )}
                      onClick={() => toast.success('已创建合并任务')}
                    />
                  }
                >
                  合并任务
                </TooltipTrigger>
                <TooltipContent>仅已完成/已合并任务可合并</TooltipContent>
              </Tooltip>
            )}
            {hasPermission('task:export') && (
              <Button
                size='sm'
                variant='outline'
                onClick={() => toast.success('导出流程见导出数据弹窗（§5.12）')}
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
