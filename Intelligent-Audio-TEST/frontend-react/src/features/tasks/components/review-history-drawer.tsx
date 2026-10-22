/**
 * 任务复核历史抽屉（19 规范 §3.4，Sheet sm:max-w-lg）。
 * 数据源 GET /tasks/results/{task_id}/review-history（task:read；多次复核追加不覆盖）。
 * 行 = 时间（mono）+ 操作人（用户 #id，AUTH_MODE=off 显「—」）+ 用例名 + 字段徽章
 *   + 改判 {原值} → {新值}（mono，destructive 箭头）+ 备注（截断 Tooltip）。
 * 空态「暂无复核记录」；加载 Skeleton。单条复核弹窗「查看复核历史」link 复用（按 resultId 过滤）。
 */
import { useQueryClient } from '@tanstack/react-query'
import { History } from 'lucide-react'

import { useReviewHistory } from '@/application/tasks/useReview'
import { Badge } from '@/components/ui/badge'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { ReviewFieldName } from '@/domain/models/review'
import { cn } from '@/lib/utils'

function fieldLabel(field: ReviewFieldName): string {
  return field === 'execution_status' ? '执行状态' : '评估状态'
}

function formatDateTime(value: string | null): string {
  if (!value) return '—'
  // 2026-10-09T20:21:28 → 2026-10-09 20:21:28（mono 展示口径）
  return value.replace('T', ' ').slice(0, 19)
}

export function ReviewHistoryDrawer({
  open,
  onOpenChange,
  taskId,
  taskName,
  caseNameMap,
  resultId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  taskId: number
  taskName?: string
  /** 用例名映射（testCaseId → 名称；缺省显示 testCaseId） */
  caseNameMap?: Record<string, string>
  /** 按结果过滤（单条复核弹窗「查看复核历史」link 入口） */
  resultId?: number
}) {
  const queryClient = useQueryClient()
  // 抽屉未打开或 taskId<=0（test-execution 挂载即渲染的 taskId ?? 0）时不发 /review-history 无效请求
  const { data, isLoading, isError } = useReviewHistory(taskId, open && taskId > 0)
  // 后端按时间正序返回 → 展示侧倒序（最新在前，§3.4「服务端按时间倒序」口径）
  const items = (data ?? [])
    .filter((item) => (resultId ? item.resultId === resultId : true))
    .slice()
    .reverse()

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side='right' className='sm:max-w-lg'>
        <SheetHeader>
          <SheetTitle className='flex flex-wrap items-center gap-2 text-base font-semibold'>
            <History aria-hidden='true' className='text-muted-foreground size-4' />
            复核历史 — {taskName || `任务 ${taskId}`}
          </SheetTitle>
          {!isLoading && !isError && (
            <span className='text-muted-foreground text-xs tabular-nums'>共 {items.length} 条</span>
          )}
        </SheetHeader>

        <div className='flex-1 overflow-y-auto px-4 pb-4'>
          {isLoading ? (
            <div aria-busy='true' className='space-y-3'>
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className='h-16 w-full rounded-lg' />
              ))}
            </div>
          ) : isError ? (
            <div className='flex flex-col items-center gap-2 py-10 text-sm'>
              <span className='text-destructive'>复核历史加载失败</span>
              <button
                type='button'
                className='text-muted-foreground hover:text-foreground text-xs underline'
                onClick={() => queryClient.invalidateQueries({ queryKey: ['tasks', 'review'] })}
              >
                重试
              </button>
            </div>
          ) : items.length === 0 ? (
            <p className='text-muted-foreground py-10 text-center text-sm'>暂无复核记录</p>
          ) : (
            <ul className='flex flex-col gap-2'>
              {items.map((item) => {
                const caseName = caseNameMap?.[item.testCaseId] ?? item.testCaseId
                return (
                  <li
                    key={item.id}
                    className='bg-muted/30 rounded-lg border px-3 py-2 text-xs'
                  >
                    <div className='flex flex-wrap items-center gap-x-2 gap-y-1'>
                      <span className='font-mono text-[11px] tabular-nums'>
                        {formatDateTime(item.createdAt)}
                      </span>
                      <span className='text-muted-foreground'>
                        操作人 {item.createdByUserId != null ? `用户 #${item.createdByUserId}` : '—'}
                      </span>
                      <Badge variant='outline' className='rounded-sm px-1.5 text-[10px] font-normal'>
                        {caseName}
                      </Badge>
                    </div>
                    <div className='mt-1 flex flex-wrap items-center gap-1.5'>
                      <Badge variant='secondary' className='rounded-sm px-1.5 text-[10px]'>
                        {fieldLabel(item.fieldName)}
                      </Badge>
                      <span className='font-mono tabular-nums'>
                        <span>{item.oldValue ?? '—'}</span>
                        <span className='text-destructive'> → </span>
                        <span>{item.newValue ?? '—'}</span>
                      </span>
                      {item.comment && (
                        <Tooltip>
                          <TooltipTrigger render={<div />}>
                            <span className={cn('text-muted-foreground max-w-56 truncate')}>
                              {item.comment}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent className='max-w-xs whitespace-normal'>
                            {item.comment}
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

/** 复核历史抽屉的用例名映射构造（从任务详情 cases 构建 testCaseId → name） */
export function buildCaseNameMap(
  cases: Array<{ case_id: string; name: string }> | undefined
): Record<string, string> {
  return (cases ?? []).reduce<Record<string, string>>((acc, c) => {
    acc[c.case_id] = c.name
    return acc
  }, {})
}
