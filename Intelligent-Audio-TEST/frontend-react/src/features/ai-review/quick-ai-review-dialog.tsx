/**
 * 快速复核弹窗（interfaces 层 features/ai-review；19 规范 §5.1，INT-1064）。
 * 原 `features/tasks/components/ai-review-dialog.tsx` 迁移——一次性状态机（发起→执行中→
 * 结论卡，不可追问）降级为「快速复核」次要入口：批量/低分初筛等无需追问的快速复检场景
 * （入口文案「快速复核」，ghost 次要钮）。主形态为灵犀Agent 对话式复核
 * （ai-review-session-dialog，§5.2）。两模式共用同一 ai_reviews 落位契约（§5.5）。
 * 采纳=单次调 POST /tasks/results/ai-review/{id}/adopt 落人工复核语义（**前端不补调
 * /tasks/results/review，会双写留痕**——审核注记 1）；驳回=POST /ai-review/{id}/reject 标记备查。
 */
import { Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import type {
  AiReviewPhase,
  AiReviewRecord,
  AiReviewVerdict,
  CaseResultForReview,
} from '@/domain/models/review'
import {
  aiConfidenceLabel,
  AI_VERDICT_LABELS,
  AI_VERDICT_VARIANTS,
  aiReviewStatusLabel,
  EVALUATION_STATUS_LABELS,
} from '@/domain/models/review'
import {
  adoptAiReview,
  fetchAiReviewHistory,
  rejectAiReview,
  requestAiReview,
} from '@/infrastructure/api/reviewApi'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'

/** AI 结论 → 评估状态预填（§2.1：通过→已完成，不通过→评估失败，存疑→留给人工） */
function verdictToEvaluationStatus(verdict: AiReviewVerdict): string | undefined {
  if (verdict === 'passed') return 'completed'
  if (verdict === 'failed') return 'failed'
  return undefined
}

export function QuickAiReviewDialog({
  open,
  onOpenChange,
  taskId,
  caseId,
  caseName,
  results,
  evaluationStatus,
  dimensionIds,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  taskId: number
  caseId: string
  caseName?: string
  /** 发起对象（用例执行结果行；§5.2 可发起对象 = 评估已完成/评估失败） */
  results: CaseResultForReview[]
  /** 用例当前评估状态（AI 判定 vs 原评估判定对比行） */
  evaluationStatus?: string | null
  /** INT-1279：用例评估维度 id（真实库结果无 LLM 判分维度时显式传 dimension_ids，避免发起 400） */
  dimensionIds?: number[]
}) {
  const [phase, setPhase] = useState<AiReviewPhase>('idle')
  const [record, setRecord] = useState<AiReviewRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  /** 本次发起的记录 id（执行中按它从历史定位推进状态） */
  const [recordId, setRecordId] = useState<number | null>(null)

  // 弹窗关闭（忽略/待查）后重置状态机
  useEffect(() => {
    if (!open) {
      setPhase('idle')
      setRecord(null)
      setError(null)
      setRecordId(null)
    }
  }, [open])

  // 真实后端异步执行：发起返回 pending/running → 每 3s 轮询历史推进到 completed/failed
  useEffect(() => {
    if (!recordId || !open) return
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const history = await fetchAiReviewHistory(taskId)
          const current = history.find((r) => r.id === recordId)
          if (!current) return
          if (current.status === 'completed') {
            setRecord(current)
            setPhase('completed')
            setRecordId(null)
          } else if (current.status === 'failed' || current.status === 'canceled') {
            setError(
              current.status === 'failed'
                ? 'AI 复核执行失败，请稍后重试'
                : 'AI 复核已取消'
            )
            setPhase('idle')
            setRecordId(null)
          }
          // pending/running/未知值：保持执行中，下次轮询继续（§5.7 注记 2 容错）
        } catch {
          // 轮询失败保持执行中，下次继续
        }
      })()
    }, 3000)
    return () => window.clearInterval(timer)
  }, [recordId, open, taskId])

  const handleLaunch = async () => {
    setPhase('running')
    setError(null)
    try {
      const created = await requestAiReview(taskId, caseId, {
        resultIds: results.map((r) => r.id),
        dimensionIds: dimensionIds?.length ? dimensionIds : undefined,
      })
      setRecord(created)
      if (created.status === 'completed') {
        setPhase('completed')
      } else if (created.status === 'failed' || created.status === 'canceled') {
        setError(
          created.status === 'failed'
            ? 'AI 复核执行失败，请稍后重试'
            : 'AI 复核已取消'
        )
        setPhase('idle')
      } else {
        // pending/running：异步执行中，轮询 effect 推进
        setRecordId(created.id)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 复核发起失败，请稍后重试')
      setPhase('idle')
    }
  }

  /** 采纳：单次调 POST /ai-review/{id}/adopt 落人工复核语义（不补调 /tasks/results/review，
   * 避免双写留痕——审核注记 1；存疑无明确判定不开放，兜底避免空载荷 400） */
  const handleAdopt = async () => {
    if (!record || record.verdict === 'uncertain') return
    setPhase('adopted')
    try {
      await adoptAiReview(record.id, {
        evaluationStatus: verdictToEvaluationStatus(record.verdict),
        comment: record.reasoning,
      })
      toast.success('已采纳 AI 复核结论，复核已提交')
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 复核采纳失败，请稍后重试')
      setPhase('completed')
    }
  }

  const handleReject = async () => {
    if (!record) return
    try {
      await rejectAiReview(record.id)
      setPhase('rejected')
      toast.success('已驳回 AI 复核结论')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 复核驳回失败，请稍后重试')
    }
  }

  const devices = results.map((r) => r.deviceName ?? r.apiName ?? '—').filter(Boolean)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg' data-slot='quick-ai-review-dialog'>
        <DialogHeader className='text-start'>
          <DialogTitle className='flex items-center gap-1.5 text-base font-semibold'>
            <Sparkles aria-hidden='true' className='text-muted-foreground size-4' />
            快速复核
          </DialogTitle>
          <DialogDescription className='text-muted-foreground text-xs'>
            一次性状态机快速复检（批量/低分初筛场景，不可追问）；正式复核请用 AI 复核会话（灵犀Agent 可追问）
          </DialogDescription>
        </DialogHeader>

        {/* 复核对象摘要 */}
        {phase === 'idle' || phase === 'running' ? (
          <div className='space-y-2'>
            <div className='flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs'>
              <span className='max-w-56 truncate font-medium'>{caseName ?? `用例`}</span>
              <StatusBadge
                label={
                  evaluationStatus
                    ? EVALUATION_STATUS_LABELS[evaluationStatus] ?? evaluationStatus
                    : '—'
                }
                variant={
                  evaluationStatus === 'completed'
                    ? 'success'
                    : evaluationStatus === 'failed'
                      ? 'danger'
                      : 'neutral'
                }
              />
              <span className='text-muted-foreground'>
                {results.length} 条结果 · {devices.join(' / ')}
              </span>
            </div>
            {results[0]?.lastReviewComment && (
              <p className='bg-muted/40 rounded-md px-3 py-2 text-xs'>
                <span className='text-muted-foreground'>现有复核/评语：</span>
                {results[0].lastReviewComment}
              </p>
            )}
          </div>
        ) : null}

        {error && (
          <Alert variant='destructive'>
            <AlertDescription className='text-sm'>{error}</AlertDescription>
          </Alert>
        )}

        {/* 状态机主体 */}
        {phase === 'idle' && (
          <p className='text-muted-foreground text-sm'>
            将对选中的 {results.length} 条结果执行大模型复检，完成后展示 AI 结论，可采纳为人工复核结果或驳回。
          </p>
        )}

        {phase === 'running' && (
          <div aria-busy='true' className='space-y-3 py-2'>
            <Skeleton className='h-5 w-40 rounded-md' />
            <Skeleton className='h-24 w-full rounded-lg' />
            <p className='text-muted-foreground animate-pulse text-sm'>AI 复核中…</p>
          </div>
        )}

        {phase === 'completed' && record && (
          <div className='space-y-3'>
            {/* AI 结论卡（§5.7 注记 2：status 未知值容错——completed 才展示结论字段） */}
            <div className='rounded-lg border px-3 py-2.5'>
              <div className='flex flex-wrap items-center gap-2'>
                <span className='text-sm font-medium'>AI 复核结论</span>
                <StatusBadge
                  label={aiReviewStatusLabel(record.status)}
                  variant={
                    record.status === 'completed'
                      ? 'success'
                      : record.status === 'failed'
                        ? 'danger'
                        : 'neutral'
                  }
                />
                {record.status === 'completed' && (
                  <>
                    <StatusBadge
                      label={AI_VERDICT_LABELS[record.verdict]}
                      variant={AI_VERDICT_VARIANTS[record.verdict]}
                    />
                    <Badge variant='outline' className='font-mono text-[11px] tabular-nums'>
                      置信度 {aiConfidenceLabel(record.confidence)}
                    </Badge>
                  </>
                )}
              </div>
              {/* 对比行：AI 判定 vs 原评估判定 */}
              <div className='mt-2 flex flex-wrap items-center gap-2 text-xs'>
                <span className='text-muted-foreground'>AI 判定</span>
                <StatusBadge
                  label={record.status === 'completed' ? AI_VERDICT_LABELS[record.verdict] : '—'}
                  variant={
                    record.status === 'completed' ? AI_VERDICT_VARIANTS[record.verdict] : 'neutral'
                  }
                />
                <span className='text-muted-foreground'>vs 原评估判定</span>
                <StatusBadge
                  label={
                    evaluationStatus
                      ? EVALUATION_STATUS_LABELS[evaluationStatus] ?? evaluationStatus
                      : '—'
                  }
                  variant={
                    evaluationStatus === 'completed'
                      ? 'success'
                      : evaluationStatus === 'failed'
                        ? 'danger'
                        : 'neutral'
                  }
                />
              </div>
              {record.status === 'completed' && record.reasoning && (
                <p className='text-muted-foreground mt-2 text-xs leading-5'>{record.reasoning}</p>
              )}
            </div>
            {record.verdict === 'uncertain' && (
              <p className='text-muted-foreground text-xs'>
                存疑结论无明确判定可采纳，可驳回或忽略，或经人工复核确定结果
              </p>
            )}
          </div>
        )}

        {phase === 'adopted' && (
          <p className='text-muted-foreground animate-pulse text-sm'>已采纳 AI 结论，正在转人工复核…</p>
        )}

        {phase === 'rejected' && (
          <p className='text-muted-foreground py-2 text-sm'>
            已驳回 AI 复核结论，原评估判定保持不变，AI 结论标记「已驳回」备查。
          </p>
        )}

        <DialogFooter>
          {phase === 'idle' && (
            <>
              <Button variant='ghost' onClick={() => onOpenChange(false)}>
                取消
              </Button>
              <Button onClick={handleLaunch}>
                <Sparkles aria-hidden='true' className='size-3.5' />
                发起快速复核
              </Button>
            </>
          )}
          {phase === 'running' && (
            <Button variant='ghost' disabled>
              执行中…
            </Button>
          )}
          {phase === 'completed' && record && (
            <>
              <Button variant='ghost' onClick={handleReject}>
                驳回
              </Button>
              {/* 存疑无明确判定可采纳（§5.5「uncertain→不预填留人工」）：隐藏采纳钮，兜底走驳回/人工复核 */}
              {record.verdict !== 'uncertain' && (
                <Button onClick={handleAdopt}>采纳为复核结果</Button>
              )}
            </>
          )}
          {(phase === 'rejected' || phase === 'adopted') && (
            <Button variant='ghost' onClick={() => onOpenChange(false)}>
              关闭
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
