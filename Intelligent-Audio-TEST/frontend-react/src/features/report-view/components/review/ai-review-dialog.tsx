/**
 * 发起 AI 复核弹窗（19 规范 §4.3，INT-793）：待发起→执行中→已完成（AI 结论卡）→已采纳/已驳回/待查。
 * 入口：具体用例行「AI 复核」ghost 钮（Sparkles）；仅评估状态为已完成/评估失败且存在 LLM 判分/评语可发起。
 * 端点已真实接线（INT-824 契约 POST /tasks/results/ai-review）；异步执行由后端 status 驱动
 * （pending/running → 轮询历史推进 → completed/failed），采纳落人工复核语义
 * （打开 §3.2 复核弹窗预填评估状态 + 备注），驳回保留原判定，忽略保留待查。
 */
import { Sparkles, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

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
import { Label } from '@/components/ui/label'
import { Progress } from '@/features/tasks/components/ui/progress'
import type { ReportCaseItem, ReportCaseMetrics } from '@/domain/models/report'
import {
  evaluationStatusLabel,
  executionStatusLabel,
} from '@/domain/models/review'
import {
  useAiReview,
  useCaseResults,
  aiVerdictToEvaluationStatus,
} from '@/application/report-view/useReportReviews'
import { cn } from '@/lib/utils'

import { AiReviewResultCard } from './ai-review-result-card'

interface AiReviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  taskId: number
  caseItem?: ReportCaseItem
  /** 当前评估状态（任务侧用例简报 evaluation_status，对比行「原评估判定」） */
  originalEvaluationStatus?: string | null
  /** 采纳 → 父层打开人工复核弹窗预填（AI 判定评估状态 + 理由） */
  onAdopt: (prefill: {
    evaluationStatus?: 'completed' | 'failed'
    comment?: string
  }) => void
}

/** 用例 metrics 双格式 → 维度选项（含平均分；低分维度默认选中） */
function extractCaseDimensions(
  metrics?: ReportCaseMetrics
): Array<{ name: string; score?: number }> {
  const dimMap: Record<string, { sum: number; count: number }> = {}
  const add = (key: string, value: unknown) => {
    if (typeof value !== 'number') return
    const name = key.replace(/@(round:\d+|overall)$/i, '')
    if (!name) return
    dimMap[name] ??= { sum: 0, count: 0 }
    dimMap[name].sum += value
    dimMap[name].count += 1
  }
  if (Array.isArray(metrics)) {
    for (const group of metrics) {
      for (const m of group.metrics ?? []) add(m.metric, m.value)
    }
  } else if (metrics && typeof metrics === 'object') {
    for (const res of Object.values(metrics)) {
      if (res && typeof res === 'object') {
        for (const [key, value] of Object.entries(res)) add(key, value)
      }
    }
  }
  return Object.entries(dimMap)
    .map(([name, { sum, count }]) => ({
      name,
      score: count > 0 ? sum / count : undefined,
    }))
    .sort((a, b) => (a.score ?? Infinity) - (b.score ?? Infinity))
}

export function AiReviewDialog({
  open,
  onOpenChange,
  taskId,
  caseItem,
  originalEvaluationStatus,
  onAdopt,
}: AiReviewDialogProps) {
  const ai = useAiReview(taskId, caseItem?.id ?? '')
  const resultsQuery = useCaseResults(taskId, caseItem?.id ?? '', open)
  const [selectedDims, setSelectedDims] = useState<string[]>([])

  const dimensions = useMemo(
    () => extractCaseDimensions(caseItem?.metrics),
    [caseItem?.metrics]
  )
  const lowScoreDim = dimensions.find((d) => d.score !== undefined && d.score < 0.6)?.name
    ?? dimensions[0]?.name

  // 打开时重置状态机 + 默认选中低分维度
  useEffect(() => {
    if (open) {
      ai.reset()
      setSelectedDims(lowScoreDim ? [lowScoreDim] : [])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, caseItem?.id])

  const toggleDim = (name: string) => {
    setSelectedDims((prev) =>
      prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name]
    )
  }

  const handleInitiate = () => {
    const resultIds = resultsQuery.data?.results.map((r) => r.id) ?? []
    if (resultIds.length === 0) return
    void ai.initiate({ resultIds })
  }

  const handleAdopt = async () => {
    if (!ai.record) return
    const ok = await ai.adopt()
    if (!ok) return
    onAdopt({
      evaluationStatus: aiVerdictToEvaluationStatus(ai.record.verdict),
      comment: ai.record.reasoning,
    })
    onOpenChange(false)
  }

  const close = () => {
    ai.reset()
    onOpenChange(false)
  }

  const resultLabel =
    resultsQuery.data?.results.map((r) => r.deviceName ?? r.apiName ?? '未知资源').join(' / ') ||
    (caseItem?.results ?? []).map((r) => r.resource).join(' / ')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle className='flex items-center gap-2'>
            <Sparkles aria-hidden='true' className='text-primary size-4' />
            AI 复核
          </DialogTitle>
          <DialogDescription className='text-muted-foreground'>
            由大模型对当前评估结果进行复检，产出复核结论供人工确认；不直接修改统计
          </DialogDescription>
        </DialogHeader>

        {ai.phase === 'idle' && (
          <div className='space-y-4'>
            {/* 复核对象摘要（§4.3：用例名 + 设备 + 维度 + 当前评估状态） */}
            <div className='rounded-lg border p-3 text-xs'>
              <div className='flex flex-wrap items-center gap-2'>
                <span className='min-w-0 flex-1 truncate font-medium'>{caseItem?.name ?? '用例'}</span>
                {caseItem && (
                  <Badge variant='outline' className='font-mono text-[10px]'>{caseItem.id}</Badge>
                )}
              </div>
              <div className='text-muted-foreground mt-2 space-y-1'>
                <p>关联资源：{resultLabel || '—'}</p>
                <p>
                  当前评估状态：
                  <span className='text-foreground font-medium'>
                    {evaluationStatusLabel(originalEvaluationStatus)}
                  </span>
                  <span className='ms-2 text-muted-foreground'>
                    执行：
                    {resultsQuery.data?.results
                      .map((r) => executionStatusLabel(r.executionStatus))
                      .join(' / ') || '—'}
                  </span>
                </p>
              </div>
            </div>

            {/* 复核维度（默认当前低分维度，多选） */}
            <div>
              <Label className='mb-1 block text-xs'>复核维度（默认当前低分维度）</Label>
              {dimensions.length === 0 ? (
                <p className='text-muted-foreground text-xs'>该用例暂无维度数据</p>
              ) : (
                <div className='flex flex-wrap gap-1.5'>
                  {dimensions.map((d) => (
                    <button
                      key={d.name}
                      type='button'
                      onClick={() => toggleDim(d.name)}
                      className={cn(
                        'rounded-lg border px-2.5 py-1 text-xs transition-colors',
                        selectedDims.includes(d.name)
                          ? 'border-primary bg-primary/10 text-primary font-medium'
                          : 'hover:bg-muted text-muted-foreground'
                      )}
                    >
                      {d.name}
                      {d.score !== undefined && (
                        <span className='ms-1 font-mono tabular-nums opacity-70'>
                          {d.score.toFixed(2)}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {ai.phase === 'running' && (
          <div className='space-y-3 py-6'>
            <p className='text-sm font-medium'>AI 复核中…</p>
            <Progress value={65} size='md' />
            <p className='text-muted-foreground text-xs'>
              大模型正在复检评估结果与语音特征一致性，请稍候
            </p>
          </div>
        )}

        {ai.phase === 'completed' && ai.record && (
          <AiReviewResultCard
            record={ai.record}
            originalEvaluationStatus={originalEvaluationStatus}
            onAdopt={() => void handleAdopt()}
            onReject={() => void ai.reject()}
            onIgnore={close}
          />
        )}

        {(ai.phase === 'adopted' || ai.phase === 'rejected' || ai.phase === 'ignored') && ai.record && (
          <AiReviewResultCard
            record={ai.record}
            originalEvaluationStatus={originalEvaluationStatus}
            disposition={ai.phase}
            disabled
          />
        )}

        {ai.error && (
          <p className='text-destructive rounded-lg border px-3 py-2 text-xs'>
            AI 复核失败：{ai.error}
            <Button variant='outline' size='sm' className='ms-2 h-6 px-2 text-xs' onClick={() => ai.reset()}>
              重试
            </Button>
          </p>
        )}

        <DialogFooter>
          {ai.phase === 'idle' && (
            <>
              <Button variant='ghost' size='sm' onClick={close}>
                <X data-icon='inline-start' />
                取消
              </Button>
              <Button
                size='sm'
                disabled={selectedDims.length === 0 || !resultsQuery.data?.results.length}
                onClick={handleInitiate}
              >
                <Sparkles data-icon='inline-start' />
                发起 AI 复核
              </Button>
            </>
          )}
          {ai.phase === 'running' && (
            <Button variant='ghost' size='sm' onClick={close}>
              取消
            </Button>
          )}
          {(ai.phase === 'adopted' || ai.phase === 'rejected' || ai.phase === 'ignored') && (
            <Button variant='outline' size='sm' onClick={close}>
              关闭
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
