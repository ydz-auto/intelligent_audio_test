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
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { TaskListItem } from '@/domain/models/task'
import {
  getEvaluationStatusMeta,
  getExecutionStatusMeta,
} from '@/features/tasks/constants'
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
  const execMeta = getExecutionStatusMeta(task.execution_status)
  const evalMeta = getEvaluationStatusMeta(task.evaluation_status)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-5xl'>
        <DialogHeader>
          <DialogTitle className='flex flex-wrap items-center gap-2'>
            <span className='min-w-0 truncate'>{task.name}</span>
            <StatusBadge label={execMeta.label} variant={execMeta.variant} pulse={execMeta.pulse} />
            <StatusBadge label={evalMeta.label} variant={evalMeta.variant} pulse={evalMeta.pulse} />
          </DialogTitle>
        </DialogHeader>
        <TaskDetailContent taskId={task.id} compact />
      </DialogContent>
    </Dialog>
  )
}
