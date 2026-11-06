/**
 * 重命名任务弹窗（09_任务域.md §5.5 形态 + 注：日常/合并行菜单「重命名」= Dialog max-w-sm 单字段；
 * INT-1290 接线）。保存发真实 PUT /tasks/{id}（infrastructure/api/tasks-actions-api.updateTask，
 * 经 use-task-actions.rename），成功后 ['tasks'] 前缀失效 → 列表/详情名称同步刷新；
 * 失败 toast（ApiError.userMessage 中文文案），弹窗保留可重试。
 */
import { LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'

import { useTaskActions } from '@/application/tasks/use-task-actions'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

export interface RenameTaskTarget {
  id: number
  name: string
}

export function RenameTaskDialog({
  task,
  open,
  onOpenChange,
}: {
  task: RenameTaskTarget | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { rename } = useTaskActions()
  const [name, setName] = useState('')

  // 弹窗每次打开以当前任务名为初值（重开不同任务不残留上一任务输入）
  useEffect(() => {
    if (open) setName(task?.name ?? '')
  }, [open, task])

  const trimmed = name.trim()
  const dirty = trimmed.length > 0 && trimmed !== task?.name
  const submitting = rename.isPending

  const handleConfirm = () => {
    if (!dirty || !task) return
    rename.mutate(
      { taskId: task.id, patch: { name: trimmed } },
      { onSuccess: () => onOpenChange(false) }
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-sm'>
        <DialogHeader>
          <DialogTitle>重命名任务</DialogTitle>
          <DialogDescription className='truncate'>
            {task?.name ?? ''} · 请输入新的任务名称
          </DialogDescription>
        </DialogHeader>

        <div className='flex flex-col gap-2'>
          <label htmlFor='rename-task-input' className='text-sm font-medium'>
            新的任务名称
          </label>
          <Input
            id='rename-task-input'
            data-testid='rename-task-input'
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && dirty && !submitting) handleConfirm()
            }}
            placeholder={task?.name ?? '任务名称'}
            autoFocus
          />
        </div>

        <DialogFooter>
          <Button variant='outline' disabled={submitting} onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!dirty || submitting} onClick={handleConfirm}>
            {submitting ? (
              <>
                <LoaderCircle aria-hidden='true' className='size-3.5 animate-spin' />
                保存中…
              </>
            ) : (
              '确定'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
