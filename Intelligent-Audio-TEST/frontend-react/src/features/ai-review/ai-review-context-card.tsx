/**
 * 复核上下文摘要卡（interfaces 层 features/ai-review；19 规范 §5.3）。
 * 首条 assistant 的复核上下文摘要卡（结构化渲染，非裸 JSON）：复核对象 +
 * 设备×结果 + 低分维度 + LLM 评语 + 已有 ai_reviews 结论——由 AiReviewContext
 * 装配（现有端点聚合，INT-1064）。
 */
import { FileSearch } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { AiReviewContext } from '@/domain/models/review'
import {
  AI_VERDICT_LABELS,
  AI_VERDICT_VARIANTS,
  evaluationStatusLabel,
} from '@/domain/models/review'
import { formatReviewTime } from '@/features/ai-review/constants'

export function AiReviewContextCard({ context }: { context: AiReviewContext }) {
  const devices = context.deviceResults
    .map((r) => r.deviceName ?? r.apiName ?? '—')
    .filter(Boolean)
  const lowDim =
    context.dimensionScores.find((d) => d.score !== null && d.score < 0.6) ??
    context.dimensionScores[0]
  const lastReview = context.existingReviews.at(-1)

  return (
    <div className='rounded-xl border bg-muted/20 px-3 py-2.5 text-xs'>
      <div className='flex flex-wrap items-center gap-2'>
        <FileSearch aria-hidden='true' className='text-primary size-3.5' />
        <span className='text-sm font-medium'>复核上下文</span>
        <Badge variant='outline' className='font-mono text-[10px]'>
          {context.caseId}
        </Badge>
        <span className='min-w-0 flex-1 truncate font-medium'>
          {context.caseName}
        </span>
        {context.evaluationStatus && (
          <StatusBadge
            label={evaluationStatusLabel(context.evaluationStatus)}
            variant={
              context.evaluationStatus === 'completed'
                ? 'success'
                : context.evaluationStatus === 'failed'
                  ? 'danger'
                  : 'neutral'
            }
          />
        )}
      </div>
      <div className='mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-muted-foreground'>
        <span>
          设备×结果：
          <span className='text-foreground font-medium'>
            {context.deviceResults.length} 条
          </span>
          {devices.length > 0 && <span className='ms-1'>{devices.join(' / ')}</span>}
        </span>
        <span>
          低分维度：
          <span className='font-mono tabular-nums'>
            {lowDim
              ? `${lowDim.name}（${lowDim.score?.toFixed(2) ?? '—'}）`
              : '—'}
          </span>
        </span>
        {lastReview && (
          <span className='inline-flex items-center gap-1'>
            已有 AI 复核结论：
            <StatusBadge
              label={AI_VERDICT_LABELS[lastReview.verdict]}
              variant={AI_VERDICT_VARIANTS[lastReview.verdict]}
            />
            <span className='font-mono'>{formatReviewTime(lastReview.createdAt)}</span>
          </span>
        )}
      </div>
      {context.reasoning && (
        <p className='text-muted-foreground mt-1.5 line-clamp-2 border-t pt-1.5'>
          <span className='text-muted-foreground/70'>现有复核/评语：</span>
          {context.reasoning}
        </p>
      )}
    </div>
  )
}
