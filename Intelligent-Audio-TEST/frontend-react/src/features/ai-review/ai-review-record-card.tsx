/**
 * AI 复核记录卡（interfaces 层 features/ai-review；19 规范 §5.5）。
 * 保存复核结论后，后端复检链路落位 ai_reviews 记录（status=completed + verdict/confidence/
 * reasoning）→ 会话内嵌本卡展示后端落位结果 + 人工处置（采纳/驳回/稍后处理）。
 * 采纳=单次调 POST /ai-review/{id}/adopt 落人工复核语义（**前端不补调 /tasks/results/review，
 * 会双写留痕**——审核注记 1）；驳回=POST /ai-review/{id}/reject 标记已驳回备查。
 */
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { AiReviewRecord } from '@/domain/models/review'
import {
  aiConfidenceLabel,
  aiReviewStatusLabel,
  AI_VERDICT_LABELS,
  AI_VERDICT_VARIANTS,
  evaluationStatusLabel,
} from '@/domain/models/review'
import { formatReviewTime } from '@/features/ai-review/constants'

export function AiReviewRecordCard({
  record,
  originalEvaluationStatus,
  onAdopt,
  onReject,
  disposition,
  disabled = false,
}: {
  record: AiReviewRecord
  /** 原评估判定（§5.4「AI 判定 vs 原评估判定」对比行） */
  originalEvaluationStatus?: string | null
  onAdopt: () => void
  onReject: () => void
  /** 处置后展示态（adopted/rejected）；无=待处置可操作 */
  disposition?: 'adopted' | 'rejected'
  disabled?: boolean
}) {
  const hasVerdict = record.status === 'completed'

  return (
    <div className='rounded-xl border px-3 py-2.5'>
      <div className='flex flex-wrap items-center gap-2'>
        <span className='text-sm font-medium'>AI 复核记录</span>
        {/* §5.7 注记 2：status 未知值容错回退原值展示（aiReviewStatusLabel） */}
        <StatusBadge
          label={aiReviewStatusLabel(record.status)}
          variant={
            record.status === 'completed'
              ? 'success'
              : record.status === 'failed'
                ? 'danger'
                : record.status === 'running'
                  ? 'info'
                  : 'neutral'
          }
        />
        {hasVerdict && (
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
        {record.createdAt && (
          <span className='text-muted-foreground ml-auto font-mono text-[11px]'>
            {formatReviewTime(record.createdAt)}
          </span>
        )}
      </div>

      {hasVerdict && record.reasoning && (
        <p className='text-muted-foreground mt-2 text-xs leading-5'>
          {record.reasoning}
        </p>
      )}

      {hasVerdict && (
        <div className='mt-2 flex flex-wrap items-center gap-2 text-xs'>
          <span className='text-muted-foreground'>对比：</span>
          <span className='font-medium'>
            AI 判定 <span className='text-primary'>{AI_VERDICT_LABELS[record.verdict]}</span>
          </span>
          <span className='text-muted-foreground'>vs</span>
          <span className='font-medium'>
            原评估判定{' '}
            <span className='text-muted-foreground'>
              {evaluationStatusLabel(originalEvaluationStatus)}
            </span>
          </span>
        </div>
      )}

      {disposition ? (
        <div className='mt-3'>
          {disposition === 'adopted' && (
            <p className='bg-success/10 text-success rounded-lg px-3 py-2 text-xs'>
              已采纳 AI 复核结论，复核已提交（落人工复核语义，统计按复核后判定重算）
            </p>
          )}
          {disposition === 'rejected' && (
            <p className='bg-muted rounded-lg px-3 py-2 text-xs text-muted-foreground'>
              已驳回 AI 复核结论，原判定不变（AI 记录标记已驳回备查）
            </p>
          )}
        </div>
      ) : (
        hasVerdict && (
          <div className='mt-3 flex flex-wrap items-center gap-2'>
            {/* 存疑无明确判定可采纳（§5.5「uncertain→不预填留人工」）：隐藏采纳钮，处置走驳回/人工复核 */}
            {record.verdict !== 'uncertain' && (
              <Button size='sm' onClick={onAdopt} disabled={disabled}>
                采纳为复核结果
              </Button>
            )}
            <Button variant='ghost' size='sm' onClick={onReject} disabled={disabled}>
              驳回
            </Button>
            {record.verdict === 'uncertain' && (
              <span className='text-muted-foreground text-xs'>
                存疑结论无明确判定可采纳，可驳回或经人工复核确定结果
              </span>
            )}
          </div>
        )
      )}
    </div>
  )
}
