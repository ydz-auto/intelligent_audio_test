/**
 * 复核历史抽屉（19 规范 §3.4/§4.3，INT-793）：人工复核 / AI 复核 两 Tab。
 * 人工 Tab：GET /tasks/results/{task_id}/review-history（服务端时间正序，展示倒序），
 * 行 = 时间 + 操作人 + 用例名 + 字段徽章 + 改判 {原值} → {新值} + 备注（LongText 截断）。
 * AI Tab：AI 复核记录（GET /tasks/results/{task_id}/ai-review-history，INT-824），空态「暂无 AI 复核记录」。
 * 用例卡片入口按 caseId 过滤；任务级入口不过滤。
 */
import { ShieldCheck, Sparkles } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { fetchAiReviewHistory, fetchReviewHistory } from '@/infrastructure/api/reviewApi'
import type { ReviewHistoryItem } from '@/domain/models/review'
import {
  AI_VERDICT_LABELS,
  aiConfidenceLabel,
  executionStatusLabel,
  evaluationStatusLabel,
} from '@/domain/models/review'

interface ReviewHistoryDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  taskId: number
  /** 用例级入口按 caseId 过滤；缺省任务级全量 */
  caseId?: string
  /** 标题用例名（用例卡片入口「复核历史 — {用例名}」；缺省任务名由消费侧传入） */
  title?: string
}

function formatTime(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function fieldBadge(field: ReviewHistoryItem['fieldName']) {
  return field === 'execution_status' ? '执行状态' : '评估状态'
}

export function ReviewHistoryDrawer({
  open,
  onOpenChange,
  taskId,
  caseId,
  title = '任务',
}: ReviewHistoryDrawerProps) {
  const manualQuery = useQuery({
    queryKey: ['tasks', 'reviews', 'history', taskId],
    queryFn: () => fetchReviewHistory(taskId),
    enabled: open,
    staleTime: 15_000,
  })
  const aiQuery = useQuery({
    queryKey: ['tasks', 'ai-reviews', 'history', taskId],
    queryFn: () => fetchAiReviewHistory(taskId),
    enabled: open,
    staleTime: 15_000,
  })

  const manualItems = (manualQuery.data ?? []).filter(
    (item) => !caseId || item.testCaseId === caseId
  )
  const aiItems = (aiQuery.data ?? []).filter(
    (rec) => !caseId || rec.testCaseId === caseId
  )

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className='flex min-h-0 flex-col sm:max-w-lg'>
        <SheetHeader>
          <SheetTitle className='flex items-center gap-2'>
            <ShieldCheck aria-hidden='true' className='text-primary size-4' />
            复核历史 — {title}
          </SheetTitle>
          <SheetDescription className='text-muted-foreground'>
            共 {manualItems.length + aiItems.length} 条
          </SheetDescription>
        </SheetHeader>

        <Tabs defaultValue='manual' className='flex min-h-0 flex-1 flex-col'>
          <TabsList className='w-full'>
            <TabsTrigger value='manual' className='flex-1'>
              人工复核
            </TabsTrigger>
            <TabsTrigger value='ai' className='flex-1'>
              AI 复核
            </TabsTrigger>
          </TabsList>

          <TabsContent value='manual' className='min-h-0 flex-1 overflow-y-auto'>
            {manualQuery.isLoading ? (
              <div className='space-y-2 p-2'>
                <Skeleton className='h-14 w-full' />
                <Skeleton className='h-14 w-full' />
              </div>
            ) : manualItems.length === 0 ? (
              <p className='text-muted-foreground flex h-24 items-center justify-center text-xs'>
                暂无复核记录
              </p>
            ) : (
              <div className='space-y-2 p-2'>
                {manualItems.map((item) => (
                  <div key={item.id} className='rounded-lg border p-2.5 text-xs'>
                    <div className='flex flex-wrap items-center gap-2'>
                      <span className='font-mono tabular-nums'>{formatTime(item.createdAt)}</span>
                      <span className='text-muted-foreground'>
                        操作人 {item.createdByUserId ? `用户 #${item.createdByUserId}` : '—'}
                      </span>
                      <Badge variant='outline' className='text-[10px]'>
                        {fieldBadge(item.fieldName)}
                      </Badge>
                      <span className='font-mono'>
                        {item.fieldName === 'execution_status'
                          ? executionStatusLabel(item.oldValue)
                          : evaluationStatusLabel(item.oldValue)}
                        <span className='text-destructive'> → </span>
                        {item.fieldName === 'execution_status'
                          ? executionStatusLabel(item.newValue)
                          : evaluationStatusLabel(item.newValue)}
                      </span>
                    </div>
                    {item.comment && (
                      <p className='text-muted-foreground mt-1 line-clamp-2'>{item.comment}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value='ai' className='min-h-0 flex-1 overflow-y-auto'>
            {aiQuery.isLoading ? (
              <div className='space-y-2 p-2'>
                <Skeleton className='h-14 w-full' />
              </div>
            ) : aiItems.length === 0 ? (
              <div className='text-muted-foreground flex h-24 flex-col items-center justify-center gap-1 text-xs'>
                <Sparkles aria-hidden='true' className='size-4' />
                暂无 AI 复核记录
              </div>
            ) : (
              <div className='space-y-2 p-2'>
                {aiItems.map((rec) => (
                  <div key={rec.id} className='rounded-lg border p-2.5 text-xs'>
                    <div className='flex flex-wrap items-center gap-2'>
                      <Badge variant='outline' className='gap-1 text-[10px]'>
                        <Sparkles aria-hidden='true' className='size-3' />
                        {AI_VERDICT_LABELS[rec.verdict]}
                      </Badge>
                      <span className='font-mono tabular-nums'>置信度 {aiConfidenceLabel(rec.confidence)}</span>
                      <span className='font-mono tabular-nums'>{formatTime(rec.createdAt)}</span>
                      {rec.adopted && (
                        <Badge variant='secondary' className='text-[10px]'>已采纳</Badge>
                      )}
                      {rec.rejected && (
                        <Badge variant='outline' className='text-[10px]'>已驳回</Badge>
                      )}
                    </div>
                    {rec.reasoning && (
                      <p className='text-muted-foreground mt-1 line-clamp-2'>{rec.reasoning}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>

        <div className='border-t pt-2'>
          <Button variant='ghost' size='sm' className='w-full' onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
