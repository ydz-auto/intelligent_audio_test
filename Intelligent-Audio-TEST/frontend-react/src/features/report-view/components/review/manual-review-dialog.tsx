/**
 * 人工复核弹窗（19 规范 §3.2/§3.3 单条=resultIds[1]、批量=resultIds[n]；§4.2 路径 A 报告侧复用，INT-793）。
 * 形态：Dialog，头「人工复核 — {用例名}」；结果摘要（设备/API + 执行状态 + 复核标注，勾选批量）+ 同一改判 UI
 * （执行/评估状态 Select + 备注必填）+ 说明行「状态可人工设置、评估分数默认不改」+「至少设置一项执行/评估状态」。
 * 数据源：GET /tasks/{task_id}/cases/{case_id}/results（result_id 溯源 + 复核标注）。
 * 提交：POST /tasks/results/review（result_ids + execution_status? + evaluation_status? + comment）。
 */
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { History, ShieldCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { useCaseResults } from '@/application/report-view/useReportReviews'
import { submitReview } from '@/infrastructure/api/reviewApi'
import type { ReportCaseItem } from '@/domain/models/report'
import {
  REVIEWABLE_EVALUATION_STATUSES,
  REVIEWABLE_EXECUTION_STATUSES,
  executionStatusLabel,
  evaluationStatusLabel,
} from '@/domain/models/review'

interface ManualReviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 报告源任务（§4.2 路径 A：报告携带 task_id + result_id 溯源） */
  taskId: number
  caseItem?: ReportCaseItem
  /** AI 采纳预填（§4.3：AI 判定评估状态 + 理由） */
  prefill?: { evaluationStatus?: 'completed' | 'failed'; comment?: string }
  /** 提交成功后回调（invalidate 源任务复核计数/标记） */
  onSubmitted?: () => void
  /** 「查看复核历史」link → 打开复核历史抽屉 */
  onViewHistory?: () => void
}

export function ManualReviewDialog({
  open,
  onOpenChange,
  taskId,
  caseItem,
  prefill,
  onSubmitted,
  onViewHistory,
}: ManualReviewDialogProps) {
  const resultsQuery = useCaseResults(taskId, caseItem?.id ?? '', open)
  const results = resultsQuery.data?.results ?? []

  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [executionStatus, setExecutionStatus] = useState<string>()
  const [evaluationStatus, setEvaluationStatus] = useState<string>()
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // 打开时重置表单（AI 采纳预填仅覆盖评估状态/备注；不随结果 refetch 重置，防填好后又清空）
  useEffect(() => {
    if (!open) return
    setSelectedIds([])
    setExecutionStatus(undefined)
    setEvaluationStatus(prefill?.evaluationStatus)
    setComment(prefill?.comment ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // 结果加载后默认勾选全部（打开会话内仅首次；用户手动取消后不重勾）
  useEffect(() => {
    if (!open) return
    setSelectedIds((prev) => (prev.length > 0 ? prev : results.map((r) => r.id)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultsQuery.data?.results])

  const canSubmit =
    comment.trim().length > 0 &&
    Boolean(executionStatus || evaluationStatus) &&
    selectedIds.length > 0 &&
    !submitting

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    try {
      const result = await submitReview({
        resultIds: selectedIds,
        executionStatus,
        evaluationStatus,
        comment: comment.trim(),
      })
      if (result.failed.length > 0) {
        toast.warning(
          `已复核 ${result.reviewedCount} 条结果（${result.failed.length} 条未生效：${result.failed[0].message}）`
        )
      } else {
        toast.success('复核已提交，结果已按复核后判定计入统计')
      }
      onSubmitted?.()
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '复核失败')
    } finally {
      setSubmitting(false)
    }
  }

  const toggleResult = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const resourceLabel = useMemo(
    () => (r: { deviceName: string | null; apiName: string | null }) =>
      r.deviceName ?? r.apiName ?? '未知资源',
    []
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle className='flex items-center gap-2'>
            <ShieldCheck aria-hidden='true' className='text-primary size-4' />
            人工复核 — {caseItem?.name ?? '用例'}
          </DialogTitle>
        </DialogHeader>

        <div className='space-y-4'>
          {/* 结果摘要（设备/API + 执行状态 + 复核标注；勾选批量逐条留痕） */}
          <div className='max-h-48 space-y-1.5 overflow-y-auto'>
            {resultsQuery.isLoading ? (
              <Skeleton className='h-16 w-full' />
            ) : resultsQuery.isError ? (
              <p className='text-muted-foreground rounded-lg border p-3 text-xs'>
                用例执行结果加载失败（源任务结果不可用）
              </p>
            ) : results.length === 0 ? (
              <p className='text-muted-foreground rounded-lg border p-3 text-xs'>
                该用例无执行结果，暂不可复核
              </p>
            ) : (
              results.map((r) => (
                <label
                  key={r.id}
                  className='hover:bg-muted/40 flex items-center gap-2 rounded-lg border px-2.5 py-2 text-xs'
                >
                  <Checkbox
                    checked={selectedIds.includes(r.id)}
                    onCheckedChange={() => toggleResult(r.id)}
                    aria-label={`选择 ${resourceLabel(r)} 结果`}
                  />
                  <span className='min-w-0 flex-1 truncate font-medium'>
                    {resourceLabel(r)}
                  </span>
                  <Badge variant='outline' className='shrink-0 font-mono text-[10px]'>
                    #{r.id}
                  </Badge>
                  <Badge
                    variant={r.executionStatus === 'completed' ? 'secondary' : 'outline'}
                    className='shrink-0'
                  >
                    {executionStatusLabel(r.executionStatus)}
                  </Badge>
                  {r.reviewed && (
                    <Badge variant='secondary' className='shrink-0 gap-1'>
                      <ShieldCheck aria-hidden='true' className='size-3' />
                      人工复核
                    </Badge>
                  )}
                </label>
              ))
            )}
          </div>

          {/* 改判 UI（§3.2：执行/评估状态 Select + 备注必填） */}
          <div className='grid gap-3 sm:grid-cols-2'>
            <div>
              <Label htmlFor='manual-review-exec' className='mb-1 block text-xs'>
                用例执行状态
              </Label>
              <Select
                value={executionStatus ?? ''}
                onValueChange={(v) => setExecutionStatus(v && v !== 'none' ? v : undefined)}
              >
                <SelectTrigger id='manual-review-exec' className='h-8 text-xs'>
                  <SelectValue placeholder='不修改'>
                    {executionStatus ? executionStatusLabel(executionStatus) : undefined}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='none'>不修改</SelectItem>
                  {REVIEWABLE_EXECUTION_STATUSES.map((s) => (
                    <SelectItem key={s} value={s} label={executionStatusLabel(s)}>
                      {executionStatusLabel(s)}
                      {s === 'completed' && <span className='text-muted-foreground'>（通过）</span>}
                      {s !== 'completed' && <span className='text-muted-foreground'>（驳回）</span>}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor='manual-review-eval' className='mb-1 block text-xs'>
                用例评估状态
              </Label>
              <Select
                value={evaluationStatus ?? ''}
                onValueChange={(v) => setEvaluationStatus(v && v !== 'none' ? v : undefined)}
              >
                <SelectTrigger id='manual-review-eval' className='h-8 text-xs'>
                  <SelectValue placeholder='不修改'>
                    {evaluationStatus ? evaluationStatusLabel(evaluationStatus) : undefined}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='none'>不修改</SelectItem>
                  {REVIEWABLE_EVALUATION_STATUSES.map((s) => (
                    <SelectItem key={s} value={s} label={evaluationStatusLabel(s)}>
                      {evaluationStatusLabel(s)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label htmlFor='manual-review-comment' className='mb-1 block text-xs'>
              复核备注<span className='text-destructive'>*</span>
            </Label>
            <Textarea
              id='manual-review-comment'
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder='填写改判依据或复核意见'
              rows={3}
              className='text-xs'
            />
          </div>

          <p className='text-muted-foreground text-xs'>
            状态可人工设置、评估分数默认不改；至少设置一项执行/评估状态。
            <Button
              variant='link'
              size='sm'
              className='text-muted-foreground h-auto px-0 text-xs underline'
              onClick={onViewHistory}
              type='button'
            >
              <History aria-hidden='true' className='me-0.5 size-3' />
              查看复核历史
            </Button>
          </p>
        </div>

        <DialogFooter>
          <Button variant='ghost' size='sm' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' disabled={!canSubmit} onClick={() => void handleSubmit()}>
            {submitting ? (
              <>
                <Spinner aria-hidden='true' className='size-3.5' />
                提交中…
              </>
            ) : (
              '提交复核'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

