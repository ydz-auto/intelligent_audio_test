/**
 * 对比 / 二次对比 Dialog（规范 §5.6，report:compare）：双来源 Tab——
 * ①基于任务（勾选任务 ≥2 → POST /reports/compare{task_ids}）
 * ②基于已选报告（列表勾选 ≥2 → POST /reports/secondary-compare{report_ids}）
 * ③对比配置（§4.6：对比维度 × 对比指标 × 对比方式 × 报告配置，INT-596 P3 补全）。
 * 提交后生成对比报告并跳转查看（mock 直接 resolve 报告 id；配置随批透传 TODO(API 接线)）。
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useCompletedTasks } from '@/application/reports/use-completed-tasks'
import { useReportCompare } from '@/application/reports/use-report-compare'
import type { ReportListItem } from '@/domain/models/report'
import { cn } from '@/lib/utils'

/** §4.6 对比维度（测试用例/评估指标/设备性能/执行时间） */
const COMPARE_DIMENSIONS = [
  { value: 'test_cases', label: '测试用例' },
  { value: 'metrics', label: '评估指标' },
  { value: 'devices', label: '设备性能' },
  { value: 'execution_time', label: '执行时间' },
]

/** §4.6 对比指标多选（多友商横向对比常用评估指标） */
const COMPARE_METRICS = ['唤醒成功率', '识别准确率', '平均响应时间', '误唤醒率', '综合得分']

/** §4.6 对比方式（核心场景=多被测主体同集同指标横向对比，§3.4） */
const COMPARE_MODES = [
  { value: 'horizontal', label: '横向对比（同指标多主体）' },
  { value: 'vertical', label: '纵向对比（同主体多轮次）' },
]

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
  const [tab, setTab] = useState<'task' | 'report' | 'config'>('task')
  const [selectedTaskIds, setSelectedTaskIds] = useState<number[]>([])
  const [name, setName] = useState('')
  const [dimension, setDimension] = useState('test_cases')
  const [metrics, setMetrics] = useState<string[]>(['唤醒成功率'])
  const [mode, setMode] = useState('horizontal')
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

  const toggleMetric = (metric: string) => {
    setMetrics((prev) =>
      prev.includes(metric) ? prev.filter((x) => x !== metric) : [...prev, metric]
    )
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    const config = { dimension, metrics, mode }
    const resultId =
      source === 'task'
        ? await compare(selectedTaskIds, name || '对比报告', config)
        : await secondaryCompare(selectedReports.map((r) => r.id), name || undefined, config)
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
            选择至少两个任务或报告，生成对比报告以分析差异；对比维度/指标/方式可自定义。
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={tab}
          onValueChange={(v) => {
            const next = v as 'task' | 'report' | 'config'
            if (next === 'config') setTab(next)
            else {
              setSource(next)
              setTab(next)
            }
          }}
        >
          <TabsList className='w-full sm:w-auto'>
            <TabsTrigger value='task' className='flex-1 sm:flex-none sm:px-4'>
              基于任务
            </TabsTrigger>
            <TabsTrigger value='report' className='flex-1 sm:flex-none sm:px-4'>
              基于已选报告
            </TabsTrigger>
            <TabsTrigger value='config' className='flex-1 sm:flex-none sm:px-4'>
              对比配置
            </TabsTrigger>
          </TabsList>

          {tab === 'task' ? (
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
          ) : tab === 'report' ? (
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
          ) : (
            <div className='space-y-3'>
              {/* §4.6 对比维度 */}
              <div className='flex flex-col gap-1.5'>
                <Label className='text-xs'>对比维度</Label>
                <Select value={dimension} onValueChange={(v) => setDimension(v ?? 'test_cases')}>
                  <SelectTrigger className='h-9'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent align='start'>
                    {COMPARE_DIMENSIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* §4.6 对比指标（多选） */}
              <div className='flex flex-col gap-1.5'>
                <Label className='text-xs'>对比指标</Label>
                <div className='flex flex-wrap gap-1.5'>
                  {COMPARE_METRICS.map((metric) => {
                    const active = metrics.includes(metric)
                    return (
                      <button
                        key={metric}
                        type='button'
                        aria-pressed={active}
                        className={cn(
                          'rounded-md px-2 py-0.5 text-xs transition-colors',
                          active
                            ? 'bg-primary text-primary-foreground'
                            : 'hover:bg-muted text-muted-foreground'
                        )}
                        onClick={() => toggleMetric(metric)}
                      >
                        {metric}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* §4.6 对比方式 */}
              <div className='flex flex-col gap-1.5'>
                <Label className='text-xs'>对比方式</Label>
                <Select value={mode} onValueChange={(v) => setMode(v ?? 'horizontal')}>
                  <SelectTrigger className='h-9'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent align='start'>
                    {COMPARE_MODES.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* §4.6 报告配置（名称 + 描述） */}
              <div className='space-y-2'>
                <Label htmlFor='compare-name'>报告名称</Label>
                <Input
                  id='compare-name'
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder='对比报告'
                />
              </div>
            </div>
          )}
        </Tabs>

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
