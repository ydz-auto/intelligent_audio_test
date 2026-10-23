/**
 * 用例列表查询错误态（INT-1605，与 INT-1560 标签页 / INT-1583 音频页同型）。
 * 背景：`useTestCasesList` 失败时 items 为空，分组/标签卡片流一律走「没有找到符合条件的测试用例」
 * 空态，用户无法区分「库里没有用例」与「接口挂了」，会重复新建或误判数据丢失。
 * 口径：
 * - 失败且无任何可展示数据 → 整块错误态 + 重试（不复用「没有找到」空态）；
 * - 失败但保留着上一次成功结果（翻页 / 筛选失败）→ 保留旧列表 + 行内提示条（role=alert）+ 重试。
 * 样式取 ErrorState / Button 既有件与 INT-1583 提示条同款类名，不新增样式值。
 */
import { AlertTriangle, RotateCw } from 'lucide-react'

import { ErrorState } from '@/components/error-state'
import { Button } from '@/components/ui/button'

/** 整块错误态（首屏失败、无旧数据可回显） */
export function CaseListErrorState({
  title,
  description,
  onRetry,
}: {
  title: string
  description: string
  onRetry?: () => void
}) {
  return (
    <div className='bg-card ring-foreground/10 rounded-xl ring-1'>
      <ErrorState
        className='min-h-96'
        title={title}
        description={description}
        onRetry={onRetry}
      />
    </div>
  )
}

/** 行内提示条（失败但保留旧数据：不清空列表，提示「看到的是上一次的数据」） */
export function CaseListErrorBanner({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div
      role='alert'
      data-testid='case-list-error-banner'
      className='border-destructive/30 bg-destructive/5 text-destructive flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs'
    >
      <AlertTriangle aria-hidden='true' className='size-3.5 shrink-0' />
      <span className='min-w-0 flex-1'>{message}</span>
      {onRetry != null && (
        <Button variant='outline' size='sm' className='h-7 gap-1' onClick={onRetry}>
          <RotateCw aria-hidden='true' className='size-3' />
          重试
        </Button>
      )}
    </div>
  )
}
