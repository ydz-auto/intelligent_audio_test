/**
 * 对比 / 二次对比 Dialog（规范 §5.6，report:compare）：双来源 Tab——
 * ①基于任务（勾选任务 ≥2 → POST /reports/compare{task_ids}）
 * ②基于已选报告（列表勾选 ≥2 → POST /reports/secondary-compare{report_ids}）。
 * 提交后生成对比报告并跳转查看（mock 直接 resolve 报告 id）。
 */
import { GitCompareArrows } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useCompletedTasks } from '@/application/reports/use-completed-tasks'
import { useReportCompare } from '@/application/reports/use-report-compare'
import type { ReportListItem } from '@/domain/models/report'
import { cn } from '@/lib/utils'

interface ReportCompareDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 列表勾选的报告（二次对比数据源，≥2 可用） */
  selectedReports: ReportListItem[]
  onCompared: (reportId: number) => void
}

export function ReportCompareDialog({
  open,
  onOpenChange,
  selectedReports,
  onCompared,
}: ReportCompareDialogProps) {
  const [source, setSource] = useState<'task' | 'report'>('task')
  const [selectedTaskIds, setSelectedTaskIds] = useState<number[]>([])
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const { data: tasks = [] } = useCompletedTasks()
  const { compare, secondaryCompare } = useReportCompare()

  const taskCount = selectedTaskIds.length
  const reportCount = selectedReports.length
  const canSubmit =
    (source === 'task' && taskCount >= 2) ||
    (source === 'report' && reportCount >= 2)

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setSelectedTaskIds([])
      setName('')
    }
    onOpenChange(next)
  }

  const toggleTask = (id: number) => {
    setSelectedTaskIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    const resultId =
      source === 'task'
        ? await compare(selectedTaskIds, name || '对比报告')
        : await secondaryCompare(selectedReports.map((r) => r.id), name || undefined)
    setSubmitting(false)
    handleOpenChange(false)
    onCompared(resultId)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>报告对比</DialogTitle>
          <DialogDescription>
            选择至少两个任务或报告，生成对比报告以分析差异。
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={source}
          onValueChange={(v) => setSource(v as 'task' | 'report')}
        >
          <TabsList className='w-full sm:w-auto'>
            <TabsTrigger value='task' className='flex-1 sm:flex-none sm:px-4'>
              基于任务
            </TabsTrigger>
            <TabsTrigger value='report' className='flex-1 sm:flex-none sm:px-4'>
              基于已选报告
            </TabsTrigger>
          </TabsList>

          {source === 'task' ? (
            <div className='max-h-56 space-y-1 overflow-y-auto rounded-lg border p-2'>
              {tasks.map((task) => (
                <label
                  key={task.id}
                  className={cn(
                    'flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-muted/50'
                  )}
                >
                  <Checkbox
                    checked={selectedTaskIds.includes(task.id)}
                    onCheckedChange={() => toggleTask(task.id)}
                  />
                  <span className='min-w-0 flex-1 truncate'>{task.name}</span>
                  <span className='text-muted-foreground font-mono text-xs'>
                    #{task.id}
                  </span>
                </label>
              ))}
              <p className='text-muted-foreground px-2 pt-1 text-xs'>
                已选择 {taskCount} 个任务（≥2 可生成对比）
              </p>
            </div>
          ) : (
            <div className='max-h-56 space-y-1 overflow-y-auto rounded-lg border p-2'>
              {selectedReports.length === 0 ? (
                <p className='text-muted-foreground p-2 text-sm'>
                  请先在列表勾选至少 2 个报告
                </p>
              ) : (
                selectedReports.map((report) => (
                  <div
                    key={report.id}
                    className='flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm'
                  >
                    <GitCompareArrows className='text-muted-foreground size-4 shrink-0' />
                    <span className='min-w-0 flex-1 truncate'>{report.name}</span>
                    <span className='text-muted-foreground font-mono text-xs'>
                      #{report.id}
                    </span>
                  </div>
                ))
              )}
              <p className='text-muted-foreground px-2 pt-1 text-xs'>
                已选择 {reportCount} 个报告（≥2 可生成二次对比）
              </p>
            </div>
          )}
        </Tabs>

        <div className='space-y-2'>
          <Label htmlFor='compare-name'>名称</Label>
          <Input
            id='compare-name'
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder='对比报告'
          />
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => handleOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!canSubmit || submitting} onClick={() => void handleSubmit()}>
            {submitting ? '生成中...' : '生成对比报告'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
