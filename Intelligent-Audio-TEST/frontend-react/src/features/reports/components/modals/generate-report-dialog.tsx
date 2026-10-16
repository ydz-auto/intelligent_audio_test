/**
 * 生成报告 Dialog（规范 §5.1，report:create）：
 * 任务选择器（GET /tasks 已完成只读，mock）+ 名称/描述 + 生成报告 →
 * POST /reports/generate-task 后交页面打开进度 Dialog 并跳转报告查看。
 */
import { FilePlus2, Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCompletedTasks } from '@/application/reports/use-completed-tasks'
import { useReportActions } from '@/application/reports/use-report-actions'
import { cn } from '@/lib/utils'

interface GenerateReportDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onGenerated: (reportId: number) => void
}

export function GenerateReportDialog({
  open,
  onOpenChange,
  onGenerated,
}: GenerateReportDialogProps) {
  const [query, setQuery] = useState('')
  const [taskId, setTaskId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const { data: tasks = [] } = useCompletedTasks()
  const { generate } = useReportActions()

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return tasks
    return tasks.filter(
      (t) => t.name.toLowerCase().includes(q) || String(t.id).includes(q)
    )
  }, [query, tasks])

  const selectedTask = tasks.find((t) => t.id === taskId)

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setQuery('')
      setTaskId(null)
      setName('')
      setDescription('')
    }
    onOpenChange(next)
  }

  const handleSubmit = async () => {
    if (!taskId) return
    setSubmitting(true)
    const resultId = await generate(
      taskId,
      name || `${selectedTask?.name} 报告`,
      description || undefined
    )
    setSubmitting(false)
    handleOpenChange(false)
    onGenerated(resultId)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>生成报告</DialogTitle>
          <DialogDescription>
            基于已完成测试任务生成报告，可同时选择报告名称与描述。
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='space-y-2'>
            <Label>选择任务</Label>
            <div className='relative'>
              <Search className='text-muted-foreground/60 pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2' />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder='搜索任务名称或ID'
                className='pl-9'
              />
            </div>
            <div className='max-h-52 overflow-y-auto rounded-lg border'>
              {filtered.length === 0 ? (
                <Empty className='min-h-24 border-0'>
                  <EmptyHeader>
                    <EmptyMedia variant='icon'>
                      <FilePlus2 className='size-4' />
                    </EmptyMedia>
                    <EmptyTitle>暂无已完成任务</EmptyTitle>
                    <EmptyDescription>任务执行完成后即可在此生成报告</EmptyDescription>
                  </EmptyHeader>
                  <EmptyContent />
                </Empty>
              ) : (
                <ul className='divide-y'>
                  {filtered.map((task) => {
                    const active = taskId === task.id
                    return (
                      <li key={task.id}>
                        <button
                          type='button'
                          onClick={() => setTaskId(task.id)}
                          aria-pressed={active}
                          className={cn(
                            'flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors hover:bg-muted/50',
                            active && 'bg-primary/5'
                          )}
                        >
                          <span className='min-w-0'>
                            <span className='block truncate font-medium'>{task.name}</span>
                            <span className='text-muted-foreground font-mono text-xs'>
                              任务 #{task.id}
                            </span>
                          </span>
                          <span className='text-muted-foreground shrink-0 text-xs'>
                            {task.type} · 已完成
                          </span>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </div>

          <div className='grid gap-4 sm:grid-cols-2'>
            <div className='space-y-2'>
              <Label htmlFor='report-name'>报告名称</Label>
              <Input
                id='report-name'
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={selectedTask ? `${selectedTask.name} 报告` : '报告名称'}
              />
            </div>
            <div className='space-y-2'>
              <Label htmlFor='report-desc'>描述</Label>
              <Input
                id='report-desc'
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder='选填，简要说明报告内容'
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => handleOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!taskId || submitting} onClick={() => void handleSubmit()}>
            {submitting ? '生成中...' : '生成报告'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
