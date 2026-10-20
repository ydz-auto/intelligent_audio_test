/**
 * AI 复核弹窗（19 规范 §5.2 + §2.1 AI 复核状态机：待发起→执行中→已完成→已采纳/已驳回/待查）。
 * 定位：建议层，不直接改统计；只有人工「采纳」才落入人工复核语义（开 §3.2 复核弹窗预填
 * AI 判定的评估状态 + 备注=AI 理由 → 人工确认提交 → test_result_reviews 留痕 + 统计重算）。
 * 端点已真实接线（INT-824 契约）；异步执行（ai_reviews.status=pending/running）由轮询历史推进
 * （completed/failed 收敛），采纳走 POST /tasks/results/ai-review/{id}/adopt 落人工复核语义。
 */
import { Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'

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
  EVALUATION_STATUS_LABELS,
} from '@/domain/models/review'
import {
  adoptAiReview,
  fetchAiReviewHistory,
  rejectAiReview,
  requestAiReview,
} from '@/infrastructure/api/reviewApi'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'

/** AI 结论 → 人工复核弹窗预填的评估状态（§2.1：通过→已完成，不通过→评估失败，存疑→留给人工） */
function verdictToEvaluationStatus(verdict: AiReviewVerdict): string | undefined {
  if (verdict === 'passed') return 'completed'
  if (verdict === 'failed') return 'failed'
  return undefined
}

export function AiReviewDialog({
  open,
  onOpenChange,
  taskId,
  caseId,
  caseName,
  results,
  evaluationStatus,
  onAdopt,
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
  /** 人工采纳 → 打开 §3.2 复核弹窗预填（评估状态 + 备注=AI 理由） */
  onAdopt: (preset: { evaluationStatus?: string; comment: string }) => void
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
          // pending/running：保持执行中，下次轮询继续
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
      const created = await requestAiReview(
        taskId,
        caseId,
        { resultIds: results.map((r) => r.id) }
      )
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

  const handleAdopt = async () => {
    if (!record) return
    // 存疑无明确判定可采纳（§5.5「uncertain→不预填留人工」）：入口已隐藏，兜底避免空改判载荷触发后端 400
    if (record.verdict === 'uncertain') return
    setPhase('adopted')
    try {
      await adoptAiReview(record.id, {
        evaluationStatus: verdictToEvaluationStatus(record.verdict),
        comment: record.reasoning,
      })
      onAdopt({
        evaluationStatus: verdictToEvaluationStatus(record.verdict),
        comment: record.reasoning,
      })
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 复核驳回失败，请稍后重试')
    }
  }

  const devices = results.map((r) => r.deviceName ?? r.apiName ?? '—').filter(Boolean)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg' data-slot='ai-review-dialog'>
        <DialogHeader className='text-start'>
          <DialogTitle className='flex items-center gap-1.5 text-base font-semibold'>
            <Sparkles aria-hidden='true' className='text-muted-foreground size-4' />
            AI 复核
          </DialogTitle>
          <DialogDescription className='text-muted-foreground text-xs'>
            由大模型对当前评估结果进行复检，产出复核结论供人工确认；不直接修改统计
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
            {/* AI 结论卡 */}
            <div className='rounded-lg border px-3 py-2.5'>
              <div className='flex flex-wrap items-center gap-2'>
                <span className='text-sm font-medium'>AI 复核结论</span>
                <StatusBadge
                  label={AI_VERDICT_LABELS[record.verdict]}
                  variant={AI_VERDICT_VARIANTS[record.verdict]}
                />
                <Badge variant='outline' className='font-mono text-[11px] tabular-nums'>
                  置信度 {aiConfidenceLabel(record.confidence)}
                </Badge>
              </div>
              {/* 对比行：AI 判定 vs 原评估判定 */}
              <div className='mt-2 flex flex-wrap items-center gap-2 text-xs'>
                <span className='text-muted-foreground'>AI 判定</span>
                <StatusBadge label={AI_VERDICT_LABELS[record.verdict]} variant={AI_VERDICT_VARIANTS[record.verdict]} />
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
              <p className='text-muted-foreground mt-2 text-xs leading-5'>{record.reasoning}</p>
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
                发起 AI 复核
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
