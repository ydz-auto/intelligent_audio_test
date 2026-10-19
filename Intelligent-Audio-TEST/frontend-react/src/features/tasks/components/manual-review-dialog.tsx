/**
 * 人工复核弹窗（19 规范 §3.2/§3.3；单条=resultIds 长度 1，批量=resultIds[n]，共用组件）。
 * 形态：Dialog sm:max-w-xl；头「人工复核 — {用例名}」/「批量复核 — 已选 {n} 条结果」；
 * 结果摘要（执行/评估徽章 + 设备）+ 改判 UI（执行/评估 Select + 备注必填）+ 说明行
 * + 已有复核时「查看复核历史」link（开 §3.4 抽屉）。
 * 提交 POST /tasks/results/review（逐条留痕）；成功 toast 后 invalidate 任务统计。
 * AI 采纳入口：preset 预填 AI 判定的评估状态 + 备注（AI 理由），人工确认后提交。
 * 共享领域模型/API 由报告侧 INT-793 卡与任务侧 INT-795 卡共同落位（domain/dto/adapter/api/review*）。
 */
import { useMemo, useState } from 'react'
import { ClipboardCheck, History } from 'lucide-react'
import { toast } from 'sonner'

import { useSubmitReview } from '@/application/tasks/useReview'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type {
  CaseResultForReview,
} from '@/domain/models/review'
import {
  EVALUATION_STATUS_LABELS,
  EXECUTION_STATUS_LABELS,
  REVIEWABLE_EVALUATION_STATUSES,
  REVIEWABLE_EXECUTION_STATUSES,
} from '@/domain/models/review'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { ReviewBadge } from '@/features/tasks/components/review-badge'
import { ReviewHistoryDrawer } from '@/features/tasks/components/review-history-drawer'

/** Select 不改判哨兵值 */
const NO_CHANGE = '__none__'

/** 执行状态改判选项（REVIEWABLE_EXECUTION_STATUSES 中文映射，§2.1 驳回态） */
const EXECUTION_OPTIONS = REVIEWABLE_EXECUTION_STATUSES.map((value) => ({
  value,
  label: EXECUTION_STATUS_LABELS[value] ?? value,
}))

/** 评估状态改判选项（REVIEWABLE_EVALUATION_STATUSES 双状态口径） */
const EVALUATION_OPTIONS = REVIEWABLE_EVALUATION_STATUSES.map((value) => ({
  value,
  label: EVALUATION_STATUS_LABELS[value] ?? value,
}))

/** 结果行执行状态徽章（completed=success / failed=danger / 其余 neutral） */
function ResultStatusBadge({ status }: { status: string | null }) {
  const variant =
    status === 'completed'
      ? 'success'
      : status === 'failed'
        ? 'danger'
        : 'neutral'
  const label = EXECUTION_STATUS_LABELS[status ?? ''] ?? status ?? '—'
  return <StatusBadge label={label} variant={variant} />
}

export function ManualReviewDialog({
  open,
  onOpenChange,
  taskId,
  taskName,
  caseName,
  caseNameByResultId,
  results,
  evaluationStatus,
  preset,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  taskId: number
  taskName?: string
  /** 单条复核标题用（批量标题按「已选 {n} 条结果」） */
  caseName?: string
  /** 批量模式下每条结果所属用例名（resultId → 用例名；缺省用 caseName） */
  caseNameByResultId?: Record<number, string>
  /** 结果摘要（单条=1 → 单条复核；多条 → 批量复核） */
  results: CaseResultForReview[]
  /** 用例评估状态（结果行评估徽章展示；来自 TaskCaseBrief.evaluation_status） */
  evaluationStatus?: string | null
  /** AI 采纳预填（AI 判定的评估状态 + 备注=AI 理由） */
  preset?: { evaluationStatus?: string; comment?: string } | null
}) {
  const isBatch = results.length > 1
  const singleResult = isBatch ? null : results[0]

  const [executionStatus, setExecutionStatus] = useState<string>(NO_CHANGE)
  const [evaluationStatusValue, setEvaluationStatusValue] = useState<string>(NO_CHANGE)
  const [comment, setComment] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const mutation = useSubmitReview()

  // AI 采纳预填：preset 变化时填充评估状态 + 备注（弹窗每次打开以最新 preset 为准）
  const [appliedPreset, setAppliedPreset] = useState<{ evaluationStatus?: string; comment?: string } | null>(null)
  if (preset && preset !== appliedPreset) {
    setAppliedPreset(preset)
    setEvaluationStatusValue(preset.evaluationStatus ?? NO_CHANGE)
    setComment(preset.comment ?? '')
  }

  // 结果摘要展示的评估状态（结果行共享用例级评估状态）
  const summaryEvaluation = evaluationStatus ?? singleResult?.executionStatus ?? null

  /** 单条已有复核时「查看复核历史」抽屉的用例名映射（历史行 testCaseId → 当前用例名） */
  const historyCaseNameMap = useMemo(() => {
    if (!singleResult || !caseName) return undefined
    const map: Record<string, string> = {}
    for (const item of singleResult.reviewHistory) {
      map[item.testCaseId] = caseName
    }
    return Object.keys(map).length > 0 ? map : undefined
  }, [singleResult, caseName])

  const hasAnyHistory = results.some((r) => r.reviewHistory.length > 0)

  const submitDisabled =
    mutation.isPending ||
    comment.trim().length === 0 ||
    (executionStatus === NO_CHANGE && evaluationStatusValue === NO_CHANGE)

  const handleSubmit = () => {
    if (comment.trim().length === 0) {
      toast.error('复核备注必填')
      return
    }
    if (executionStatus === NO_CHANGE && evaluationStatusValue === NO_CHANGE) {
      toast.error('执行状态/评估状态至少设置一项')
      return
    }
    mutation.mutate(
      {
        resultIds: results.map((r) => r.id),
        executionStatus: executionStatus === NO_CHANGE ? undefined : executionStatus,
        evaluationStatus:
          evaluationStatusValue === NO_CHANGE ? undefined : evaluationStatusValue,
        comment: comment.trim(),
      },
      {
        onSuccess: (result) => {
          const failedCount = result.failed.length
          if (failedCount > 0) {
            toast.success(
              `已复核 ${result.reviewedCount} 条结果（${failedCount} 条未生效：${result.failed[0].message}）`
            )
          } else {
            toast.success('复核已提交，结果已按复核后判定计入统计')
          }
          onOpenChange(false)
        },
        onError: (err) => {
          toast.error(
            err instanceof Error && err.message ? `复核失败：${err.message}` : '复核失败，请稍后重试'
          )
        },
      }
    )
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className='sm:max-w-xl' data-slot='manual-review-dialog'>
          <DialogHeader className='text-start'>
            <DialogTitle className='flex items-center gap-1.5 text-base font-semibold'>
              <ClipboardCheck aria-hidden='true' className='text-muted-foreground size-4' />
              {isBatch ? `批量复核 — 已选 ${results.length} 条结果` : `人工复核 — ${caseName ?? `用例`}`}
            </DialogTitle>
            <DialogDescription className='text-muted-foreground text-xs'>
              对 {results.length} 条结果进行人工复核（逐条留痕，历史不覆盖）
            </DialogDescription>
          </DialogHeader>

          {/* 结果摘要 */}
          <div className='space-y-2'>
            {isBatch ? (
              <div className='max-h-44 space-y-1.5 overflow-y-auto rounded-lg border px-3 py-2'>
                {results.map((r, index) => (
                  <div key={r.id} className='flex flex-wrap items-center gap-2 text-xs'>
                    <span className='font-mono text-[11px] text-muted-foreground'>
                      {index + 1}.
                    </span>
                    <span className='max-w-48 truncate font-medium'>
                      {caseNameByResultId?.[r.id] ?? caseName ?? `用例`}
                    </span>
                    <ResultStatusBadge status={r.executionStatus} />
                    <span className='text-muted-foreground'>{r.deviceName ?? r.apiName ?? '—'}</span>
                    {r.reviewed && <ReviewBadge className='h-4 px-1 text-[10px]' />}
                  </div>
                ))}
              </div>
            ) : (
              singleResult && (
                <div className='flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs'>
                  <span className='max-w-56 truncate font-medium'>{caseName ?? `用例`}</span>
                  <ResultStatusBadge status={singleResult.executionStatus} />
                  <StatusBadge
                    label={
                      summaryEvaluation
                        ? EVALUATION_STATUS_LABELS[summaryEvaluation] ?? summaryEvaluation
                        : '—'
                    }
                    variant={
                      summaryEvaluation === 'completed'
                        ? 'success'
                        : summaryEvaluation === 'failed'
                          ? 'danger'
                          : 'neutral'
                    }
                  />
                  <span className='text-muted-foreground'>
                    {singleResult.deviceName ?? singleResult.apiName ?? '—'}
                  </span>
                  {singleResult.reviewed && (
                    <ReviewBadge
                      className='h-4 px-1 text-[10px]'
                      detail={
                        singleResult.lastReviewAction
                          ? `已复核 · 改判：${singleResult.lastReviewAction}`
                          : undefined
                      }
                    />
                  )}
                </div>
              )
            )}
          </div>

          {/* 改判 UI */}
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='space-y-1.5'>
              <label className='text-sm font-medium'>用例执行状态</label>
              <Select
                value={executionStatus}
                onValueChange={(v) => setExecutionStatus(v ?? NO_CHANGE)}
              >
                <SelectTrigger size='sm' className='w-full' aria-label='用例执行状态'>
                  <SelectValue>
                    {executionStatus === NO_CHANGE
                      ? '— 不改判 —'
                      : EXECUTION_STATUS_LABELS[executionStatus] ?? executionStatus}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_CHANGE}>— 不改判 —</SelectItem>
                  {EXECUTION_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='space-y-1.5'>
              <label className='text-sm font-medium'>用例评估状态</label>
              <Select
                value={evaluationStatusValue}
                onValueChange={(v) => setEvaluationStatusValue(v ?? NO_CHANGE)}
              >
                <SelectTrigger size='sm' className='w-full' aria-label='用例评估状态'>
                  <SelectValue>
                    {evaluationStatusValue === NO_CHANGE
                      ? '— 不改判 —'
                      : EVALUATION_STATUS_LABELS[evaluationStatusValue] ?? evaluationStatusValue}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_CHANGE}>— 不改判 —</SelectItem>
                  {EVALUATION_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className='space-y-1.5'>
            <label className='text-sm font-medium'>
              复核备注 <span className='text-destructive'>*</span>
            </label>
            <Textarea
              rows={3}
              placeholder='填写改判依据或复核意见'
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className='resize-none'
              data-slot='review-comment'
            />
            <p className='text-muted-foreground text-xs'>
              状态可人工设置、评估分数默认不改；至少设置一项执行/评估状态
            </p>
          </div>

          {mutation.isError && (
            <Alert variant='destructive'>
              <AlertDescription className='text-sm'>
                {mutation.error instanceof Error
                  ? mutation.error.message
                  : '复核提交失败，请稍后重试'}
              </AlertDescription>
            </Alert>
          )}

          {!isBatch && singleResult?.reviewHistory.length ? (
            <button
              type='button'
              className='text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-xs underline'
              onClick={() => setHistoryOpen(true)}
            >
              <History aria-hidden='true' className='size-3' />
              查看复核历史（{singleResult.reviewHistory.length}）
            </button>
          ) : hasAnyHistory ? (
            <button
              type='button'
              className='text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-xs underline'
              onClick={() => setHistoryOpen(true)}
            >
              <History aria-hidden='true' className='size-3' />
              查看复核历史
            </button>
          ) : null}

          <DialogFooter>
            <Button variant='ghost' onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
              取消
            </Button>
            <Button onClick={handleSubmit} disabled={submitDisabled}>
              {mutation.isPending ? '提交中…' : '提交复核'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 复核历史抽屉（复用 §3.4） */}
      <ReviewHistoryDrawer
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        taskId={taskId}
        taskName={taskName}
        caseNameMap={historyCaseNameMap}
        resultId={singleResult?.id}
      />
    </>
  )
}
