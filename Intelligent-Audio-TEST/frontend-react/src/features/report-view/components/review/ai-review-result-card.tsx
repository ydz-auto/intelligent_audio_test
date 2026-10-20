/**
 * AI 结论卡（19 规范 §4.3/§4.4，INT-793）：结论 StatusBadge（通过=success/不通过=warning/存疑=info）
 * + 置信度 + 理由摘要（LongText 可展开）+ 对比行（AI 判定 vs 原评估判定）+ 处置钮（采纳/驳回）。
 */
import { Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { AiReviewRecord, AiReviewVerdict } from '@/domain/models/review'
import {
  AI_VERDICT_LABELS,
  AI_VERDICT_VARIANTS,
  aiConfidenceLabel,
  evaluationStatusLabel,
} from '@/domain/models/review'

interface AiReviewResultCardProps {
  record: AiReviewRecord
  /** 原评估判定（当前任务/报告快照评估状态；缺省显示「未知」） */
  originalEvaluationStatus?: string | null
  /** 采纳回调（打开人工复核弹窗预填） */
  onAdopt?: () => void
  /** 驳回回调 */
  onReject?: () => void
  /** 忽略（关闭暂不处理） */
  onIgnore?: () => void
  /** 处置后状态展示（adopted/rejected/ignored） */
  disposition?: 'adopted' | 'rejected' | 'ignored'
  disabled?: boolean
}

function verdictLabel(verdict: AiReviewVerdict): string {
  return AI_VERDICT_LABELS[verdict]
}

export function AiReviewResultCard({
  record,
  originalEvaluationStatus,
  onAdopt,
  onReject,
  onIgnore,
  disposition,
  disabled,
}: AiReviewResultCardProps) {
  const variant = AI_VERDICT_VARIANTS[record.verdict]

  return (
    <div className='rounded-xl border p-3'>
      <div className='flex items-center justify-between gap-2'>
        <div className='flex flex-wrap items-center gap-2'>
          <StatusBadge label={verdictLabel(record.verdict)} variant={variant} />
          <span className='text-muted-foreground font-mono text-xs tabular-nums'>
            置信度 {aiConfidenceLabel(record.confidence)}
          </span>
        </div>
        <Sparkles aria-hidden='true' className='text-primary size-4 shrink-0' />
      </div>

      <p className='text-muted-foreground mt-2 text-xs leading-relaxed'>
        {record.reasoning || '暂无理由'}
      </p>

      <div className='mt-2 flex flex-wrap items-center gap-2 text-xs'>
        <span className='text-muted-foreground'>对比：</span>
        <span className='font-medium'>
          AI 判定 <span className='text-primary'>{verdictLabel(record.verdict)}</span>
        </span>
        <span className='text-muted-foreground'>vs</span>
        <span className='font-medium'>
          原评估判定{' '}
          <span className='text-muted-foreground'>
            {evaluationStatusLabel(originalEvaluationStatus)}
          </span>
        </span>
      </div>

      {disposition ? (
        <div className='mt-3'>
          {disposition === 'adopted' && (
            <p className='bg-success/10 text-success rounded-lg px-3 py-2 text-xs'>
              已采纳 AI 复核结论，复核已提交（落人工复核留痕 + 统计按复核后判定重算）
            </p>
          )}
          {disposition === 'rejected' && (
            <p className='bg-muted rounded-lg px-3 py-2 text-xs text-muted-foreground'>
              已驳回 AI 复核结论，原判定不变（AI 记录标记已驳回备查）
            </p>
          )}
          {disposition === 'ignored' && (
            <p className='bg-muted rounded-lg px-3 py-2 text-xs text-muted-foreground'>
              已忽略，AI 结论保留待查
            </p>
          )}
        </div>
      ) : (
        <>
          <div className='mt-3 flex flex-wrap items-center gap-2'>
            {/* 存疑无明确判定可采纳（§5.5「uncertain→不预填留人工」）：隐藏采纳钮，处置走驳回/忽略/人工复核 */}
            {record.verdict !== 'uncertain' && (
              <Button size='sm' onClick={onAdopt} disabled={disabled}>
                采纳为复核结果
              </Button>
            )}
            <Button variant='ghost' size='sm' onClick={onReject} disabled={disabled}>
              驳回
            </Button>
            <Button variant='ghost' size='sm' onClick={onIgnore} disabled={disabled}>
              忽略
            </Button>
          </div>
          {record.verdict === 'uncertain' && (
            <p className='text-muted-foreground mt-2 text-xs'>
              存疑结论无明确判定可采纳，可驳回或忽略，或经人工复核确定结果
            </p>
          )}
        </>
      )}
    </div>
  )
}
