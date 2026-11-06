/**
 * 任务详情快览弹窗（09_任务域.md §5.1，Dialog sm:max-w-5xl）。
 * 标题=任务名 + 双状态徽章；内容=同一 `<TaskDetailContent taskId>`（compact 双形态复用）。
 */
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { TaskListItem } from '@/domain/models/task'
import {
  getEvaluationStatusMeta,
  getExecutionStatusMeta,
} from '@/features/tasks/constants'
import { MERGE_TYPE_LABELS } from '@/features/tasks/cherry-pick/constants'
import { TaskDetailContent } from '@/features/tasks/detail/task-detail-content'

export function QuickViewDialog({
  task,
  open,
  onOpenChange,
}: {
  task: TaskListItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  if (!task) return null
  const execMeta = getExecutionStatusMeta(task.executionStatus)
  const evalMeta = getEvaluationStatusMeta(task.evaluationStatus)
  const mergeType = task.mergeType ?? (task.isCherryPick ? 'picked' : null)
  const sourceCount = task.sourceTaskCount ?? task.sourceTasks.length
  // INT-1498：容器标识说明（合并方式 + 来源任务/结果计数），普通任务不渲染
  const mergeDesc = mergeType
    ? [
        MERGE_TYPE_LABELS[mergeType],
        sourceCount > 0 ? `来源 ${sourceCount} 个任务` : null,
        task.sourceResultCount != null ? `结果 ${task.sourceResultCount} 条` : null,
      ]
        .filter(Boolean)
        .join(' · ')
    : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-5xl'>
        <DialogHeader>
          <DialogTitle className='flex flex-wrap items-center gap-2'>
            <span className='min-w-0 truncate'>{task.name}</span>
            {mergeType && (
              <Badge variant={mergeType === 'whole' ? 'secondary' : 'outline'} title={mergeDesc ?? undefined}>
                挑选合并
              </Badge>
            )}
            <StatusBadge label={execMeta.label} variant={execMeta.variant} pulse={execMeta.pulse} />
            <StatusBadge label={evalMeta.label} variant={evalMeta.variant} pulse={evalMeta.pulse} />
          </DialogTitle>
          {mergeDesc && (
            <p className='text-muted-foreground text-xs'>{mergeDesc}</p>
          )}
        </DialogHeader>
        <TaskDetailContent taskId={task.id} compact />
      </DialogContent>
    </Dialog>
  )
}
