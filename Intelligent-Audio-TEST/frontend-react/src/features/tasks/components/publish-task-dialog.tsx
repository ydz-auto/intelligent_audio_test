/**
 * 发布任务弹窗（09_任务域.md §5.2，Dialog sm:max-w-lg）。
 * 字段：来源任务*（Select，仅可发布状态）/已发布任务名称*（选源后自动带出）/说明/
 * 发布说明；「参与 Benchmark 排行」Checkbox + 展开 测试集标识 + 被测类别。
 * 主钮「发布」（提交中「发布中...」）。mock 态提交 toast 演示。
 */
import { useState } from 'react'
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
import { MOCK_TASKS } from '@/infrastructure/mock/tasks-mock'
import {
  getExecutionStatusMeta,
} from '@/features/tasks/constants'

const BENCHMARK_CATEGORIES = [
  { value: 'none', label: '不指定' },
  { value: 'asr', label: '语音识别（ASR）' },
  { value: 'voice_llm', label: '语音大模型（Voice LLM）' },
  { value: 'tts', label: '语音合成（TTS）' },
  { value: 'translation', label: '翻译（Translation）' },
]

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
  const [publishing, setPublishing] = useState(false)
  const [benchmark, setBenchmark] = useState(false)

  if (!hasPermission('task:publish')) return null

  const source = MOCK_TASKS.find((t) => String(t.id) === sourceTaskId)

  const publish = () => {
    setPublishing(true)
    setTimeout(() => {
      setPublishing(false)
      onOpenChange(false)
      toast.success('已发布任务创建成功')
    }, 800)
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
              onValueChange={setSourceTaskId}
            >
              <SelectTrigger className='w-full' aria-label='选择来源任务'>
                <SelectValue placeholder='选择要发布的任务' />
              </SelectTrigger>
              <SelectContent align='start'>
                {MOCK_TASKS.filter((t) =>
                  ['completed', 'failed', 'stopped', 'pending'].includes(
                    t.execution_status ?? ''
                  )
                ).map((t) => (
                  <SelectItem key={t.id} value={String(t.id)}>
                    {t.name}（{getExecutionStatusMeta(t.execution_status).label} · 用例 {t.total_cases ?? 0}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {source && (
              <div className='bg-muted/50 mt-1 flex items-center gap-2 rounded-lg border p-2 text-xs'>
                <Badge variant='outline' className='rounded-md px-1.5'>
                  {source.name}
                </Badge>
                <span className='text-muted-foreground'>
                  {getExecutionStatusMeta(source.execution_status).label} · 用例 {source.total_cases ?? 0} ·{' '}
                  {source.device_count ?? 0} 设备
                </span>
              </div>
            )}
          </div>

          <div className='flex flex-col gap-1.5'>
            <Label className='text-sm'>
              已发布任务名称 <span className='text-destructive'>*</span>
            </Label>
            <Input
              defaultValue={source?.name ?? ''}
              maxLength={255}
              placeholder='发布后展示的任务名称（选源后自动带出）'
            />
          </div>

          <div className='flex flex-col gap-1.5'>
            <Label className='text-sm'>说明</Label>
            <Textarea rows={2} placeholder='任务说明（可选）' />
          </div>

          <div className='flex flex-col gap-1.5'>
            <Label className='text-sm'>发布说明</Label>
            <Input placeholder='例如：完成基线验证（可选）' />
          </div>

          <label className='flex cursor-pointer items-center gap-2 text-sm'>
            <Checkbox checked={benchmark} onCheckedChange={(v) => setBenchmark(!!v)} />
            参与 Benchmark 排行（实测轨数据源标记）
          </label>

          {benchmark && (
            <div className='grid gap-3 rounded-lg border bg-muted/30 p-3 sm:grid-cols-2'>
              <div className='flex flex-col gap-1.5'>
                <Label className='text-sm'>测试集标识</Label>
                <Input placeholder='例如：车载基线集' />
              </div>
              <div className='flex flex-col gap-1.5'>
                <Label className='text-sm'>被测类别</Label>
                <Select defaultValue='none'>
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
          <Button disabled={!source} onClick={publish}>
            {publishing ? '发布中...' : '发布'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
