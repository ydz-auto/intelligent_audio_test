/**
 * 发布任务弹窗（09_任务域.md §5.2，Dialog sm:max-w-lg）。
 * 字段：来源任务*（Select，仅可发布状态）/已发布任务名称*（选源后自动带出）/说明/
 * 发布说明；「参与 Benchmark 排行」Checkbox + 展开 测试集标识 + 被测类别。
 * 数据源：来源任务取真实任务列表（fetchTaskList，按可发布执行状态过滤）；
 * 主钮「发布」POST /api/v1/published-tasks（published_task.py PublishedTaskCreateRequest 契约）。
 */
import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Badge } from '@/components/ui/badge'
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
import { Textarea } from '@/components/ui/textarea'
import { ApiError } from '@/infrastructure/api/api-error'
import { fetchTaskList, publishTask } from '@/infrastructure/api/tasks-list-api'
import type { TaskListItem } from '@/domain/models/task'
import { getExecutionStatusMeta } from '@/features/tasks/constants'

const BENCHMARK_CATEGORIES = [
  { value: 'none', label: '不指定' },
  { value: 'asr', label: '语音识别（ASR）' },
  { value: 'voice_llm', label: '语音大模型（Voice LLM）' },
  { value: 'tts', label: '语音合成（TTS）' },
  { value: 'translation', label: '翻译（Translation）' },
]

/** 可发布执行状态（§5.2：已完成/失败/已停止/待执行可发布为资产） */
const PUBLISHABLE_STATUSES = ['completed', 'failed', 'stopped', 'pending']

/** 超过该时长仍无结果 → 提示加载较慢（仍继续等待，可手动重新加载） */
const SOURCE_TASKS_SLOW_MS = 8_000
/** 硬超时：中止在途请求并转错误态 + 重试，不留永久「加载中…」（INT-1627） */
const SOURCE_TASKS_TIMEOUT_MS = 60_000

export function PublishTaskDialog({
  open,
  onOpenChange,
  task,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  task?: { id: number; name: string }
}) {
  const { hasPermission } = usePermissions()
  const [sourceTaskId, setSourceTaskId] = useState<string | null>(
    task ? String(task.id) : null
  )
  const [name, setName] = useState(task?.name ?? '')
  const [description, setDescription] = useState('')
  const [publishReason, setPublishReason] = useState('')
  const [benchmark, setBenchmark] = useState(false)
  const [benchmarkSuite, setBenchmarkSuite] = useState('')
  const [benchmarkCategory, setBenchmarkCategory] = useState('none')
  const [publishing, setPublishing] = useState(false)
  const [sourceTasks, setSourceTasks] = useState<TaskListItem[]>([])
  const [tasksLoading, setTasksLoading] = useState(false)
  /** 来源任务列表错误文案（失败/超时 → 错误态 + 重试，不再静默留空） */
  const [tasksError, setTasksError] = useState<string | null>(null)
  /** 加载超过阈值仍无结果（提示可继续等待或重新加载） */
  const [tasksSlow, setTasksSlow] = useState(false)
  /** 重新加载计数（重试按钮重新发起请求） */
  const [reloadTick, setReloadTick] = useState(0)

  // 打开弹窗时取真实任务列表作来源任务选项（可发布状态过滤；空库显示空态提示）
  useEffect(() => {
    if (!open) return
    let cancelled = false
    const controller = new AbortController()
    setTasksLoading(true)
    setTasksError(null)
    setTasksSlow(false)
    const slowTimer = setTimeout(() => {
      if (!cancelled) setTasksSlow(true)
    }, SOURCE_TASKS_SLOW_MS)
    const timeoutTimer = setTimeout(() => {
      controller.abort()
    }, SOURCE_TASKS_TIMEOUT_MS)
    fetchTaskList({ perPage: 100, signal: controller.signal })
      .then((res) => {
        if (cancelled) return
        setSourceTasks(res.items)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (controller.signal.aborted) {
          setTasksError('来源任务加载超时，请重试')
        } else {
          setTasksError(
            err instanceof ApiError && err.userMessage
              ? err.userMessage
              : '来源任务加载失败，请重试'
          )
        }
      })
      .finally(() => {
        if (cancelled) return
        clearTimeout(slowTimer)
        clearTimeout(timeoutTimer)
        setTasksLoading(false)
        setTasksSlow(false)
      })
    return () => {
      cancelled = true
      clearTimeout(slowTimer)
      clearTimeout(timeoutTimer)
      controller.abort()
    }
  }, [open, reloadTick])

  const publishable = useMemo(
    () =>
      sourceTasks.filter((t) =>
        PUBLISHABLE_STATUSES.includes(t.execution_status ?? '')
      ),
    [sourceTasks]
  )
  /** Select 选项表（base-ui 闭合态按 items 回显 label，缺省则显示裸 id—INT-1627） */
  const sourceItems = useMemo(() => {
    const list = publishable.map((t) => ({
      value: String(t.id),
      label: `${t.name}（${getExecutionStatusMeta(t.execution_status).label} · 用例 ${t.total_cases ?? 0}）`,
    }))
    if (task && !list.some((item) => item.value === String(task.id))) {
      list.unshift({ value: String(task.id), label: task.name })
    }
    return list
  }, [publishable, task])

  if (!hasPermission('task:publish')) return null

  const source = publishable.find((t) => String(t.id) === sourceTaskId)
  /** 预选来源任务（列表未就绪时先用入口带入的名称，避免摘要行空白） */
  const presetTask =
    task && String(task.id) === sourceTaskId ? task : undefined
  /** 预选任务在当前列表页中的真实行（用于判断状态下是否可发布） */
  const presetInList = sourceTasks.find((t) => String(t.id) === sourceTaskId)
  /** 列表已确认该来源任务状态不可发布 → 主钮禁用并说明原因 */
  const blockedByStatus = presetInList != null && source == null

  const retryTasks = () => setReloadTick((n) => n + 1)

  /** 提交用来源任务 id：列表命中优先，未就绪时回退入口带入的预选任务（对齐 V9.7.10 可提交口径） */
  const submitTaskId = source?.id ?? (sourceTaskId ? Number(sourceTaskId) : null)

  const handleSourceChange = (value: string | null) => {
    setSourceTaskId(value)
    const next = publishable.find((t) => String(t.id) === value)
    if (next) setName(next.name)
  }

  const publish = async () => {
    if (submitTaskId == null || Number.isNaN(submitTaskId) || !name.trim()) return
    setPublishing(true)
    try {
      await publishTask({
        sourceTaskId: submitTaskId,
        name: name.trim(),
        description: description.trim() || null,
        publishReason: publishReason.trim() || null,
        benchmark,
        benchmarkSuite: benchmark ? benchmarkSuite.trim() || null : null,
        benchmarkCategory:
          benchmark && benchmarkCategory !== 'none' ? benchmarkCategory : null,
      })
      toast.success('已发布任务创建成功')
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.userMessage : '发布失败，请重试')
    } finally {
      setPublishing(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>发布任务</DialogTitle>
          <DialogDescription>将日常任务发布为可复用、可追踪的已发布任务资产</DialogDescription>
        </DialogHeader>

        <div className='flex flex-col gap-3'>
          <div className='flex flex-col gap-1.5'>
            <Label className='text-sm'>
              来源任务 <span className='text-destructive'>*</span>
            </Label>
            <Select
              value={sourceTaskId ?? undefined}
              onValueChange={handleSourceChange}
              items={sourceItems}
            >
              <SelectTrigger className='w-full' aria-label='选择来源任务'>
                <SelectValue placeholder='选择要发布的任务' />
              </SelectTrigger>
              <SelectContent align='start'>
                {tasksLoading ? (
                  <SelectItem value='__loading__' disabled>
                    加载中…
                  </SelectItem>
                ) : (
                  publishable.map((t) => (
                    <SelectItem key={t.id} value={String(t.id)}>
                      {t.name}（{getExecutionStatusMeta(t.execution_status).label} · 用例 {t.total_cases ?? 0}）
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>

            {/* 加载慢/失败：给出可操作反馈，不把用户锁在 disabled（INT-1627） */}
            {(tasksError != null || tasksSlow) && (
              <div
                role={tasksError ? 'alert' : undefined}
                className={
                  tasksError
                    ? 'text-destructive flex items-center gap-2 text-xs'
                    : 'text-muted-foreground flex items-center gap-2 text-xs'
                }
              >
                {tasksError ? (
                  <AlertCircle aria-hidden='true' className='size-3.5 shrink-0' />
                ) : (
                  <RefreshCw aria-hidden='true' className='size-3.5 shrink-0 animate-spin' />
                )}
                <span className='flex-1'>
                  {tasksError ?? '来源任务加载较慢，仍在加载中'}
                </span>
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  className='h-6 gap-1 px-2'
                  onClick={retryTasks}
                >
                  {tasksError ? '重试' : '重新加载'}
                </Button>
              </div>
            )}

            {/* 列表加载成功但无可发布任务：明确空态原因（而非空白下拉） */}
            {!tasksLoading && tasksError == null && publishable.length === 0 && (
              <p className='text-muted-foreground text-xs'>
                暂无可发布的来源任务（需为已完成 / 失败 / 已停止 / 待执行）
              </p>
            )}

            {source ? (
              <div className='bg-muted/50 mt-1 flex items-center gap-2 rounded-lg border p-2 text-xs'>
                <Badge variant='outline' className='rounded-md px-1.5'>
                  {source.name}
                </Badge>
                <span className='text-muted-foreground'>
                  {getExecutionStatusMeta(source.execution_status).label} · 用例 {source.total_cases ?? 0} ·{' '}
                  {source.device_count ?? 0} 设备
                </span>
              </div>
            ) : (
              presetTask && (
                <div className='bg-muted/50 mt-1 flex items-center gap-2 rounded-lg border p-2 text-xs'>
                  <Badge variant='outline' className='rounded-md px-1.5'>
                    {presetTask.name}
                  </Badge>
                  <span className='text-muted-foreground'>
                    {tasksLoading
                      ? '来源任务状态加载中…'
                      : tasksError
                        ? '来源任务状态未知（列表加载失败，可直接发布由后端校验）'
                        : presetInList
                          ? `${getExecutionStatusMeta(presetInList.execution_status).label} · 当前状态不可发布`
                          : '来源任务状态未知（不在当前列表页）'}
                  </span>
                </div>
              )
            )}
          </div>

          <div className='flex flex-col gap-1.5'>
            <Label className='text-sm'>
              已发布任务名称 <span className='text-destructive'>*</span>
            </Label>
            <Input
              value={name}
              maxLength={255}
              placeholder='发布后展示的任务名称（选源后自动带出）'
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className='flex flex-col gap-1.5'>
            <Label className='text-sm'>说明</Label>
            <Textarea
              rows={2}
              placeholder='任务说明（可选）'
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className='flex flex-col gap-1.5'>
            <Label className='text-sm'>发布说明</Label>
            <Input
              placeholder='例如：完成基线验证（可选）'
              value={publishReason}
              onChange={(e) => setPublishReason(e.target.value)}
            />
          </div>

          <label className='flex cursor-pointer items-center gap-2 text-sm'>
            <Checkbox checked={benchmark} onCheckedChange={(v) => setBenchmark(!!v)} />
            参与 Benchmark 排行（实测轨数据源标记）
          </label>

          {benchmark && (
            <div className='grid gap-3 rounded-lg border bg-muted/30 p-3 sm:grid-cols-2'>
              <div className='flex flex-col gap-1.5'>
                <Label className='text-sm'>测试集标识</Label>
                <Input
                  placeholder='例如：车载基线集'
                  value={benchmarkSuite}
                  onChange={(e) => setBenchmarkSuite(e.target.value)}
                />
              </div>
              <div className='flex flex-col gap-1.5'>
                <Label className='text-sm'>被测类别</Label>
                <Select value={benchmarkCategory} onValueChange={(value) => setBenchmarkCategory(value ?? 'none')} items={BENCHMARK_CATEGORIES}>
                  <SelectTrigger size='sm' className='w-full' aria-label='被测类别'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent align='start'>
                    {BENCHMARK_CATEGORIES.map((c) => (
                      <SelectItem key={c.value} value={c.value}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' disabled={publishing} onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={submitTaskId == null || !name.trim() || publishing || blockedByStatus}
            onClick={() => void publish()}
          >
            {publishing ? '发布中...' : '发布'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
