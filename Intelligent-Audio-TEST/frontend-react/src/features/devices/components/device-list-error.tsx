/**
 * 设备列表查询错误态（INT-2330，与 INT-1583 音频页 / INT-1605 用例页同型）。
 * 背景：三页签列表查询失败时 rows 为空，表格直接走「暂无设备」空态，
 * 把「接口挂了」伪装成「库里没有设备」，还引导用户去添加设备。
 * 口径：
 * - 失败且无任何可展示数据 → 整块错误态 + 重试（不复用「暂无设备」空态）；
 * - 失败但保留着上一次成功结果（刷新 / 切页签失败）→ 保留旧列表 + 行内提示条（role=alert）+ 重试。
 * 样式取 ErrorState / Button 既有件与 INT-1583 提示条同款类名，不新增样式值。
 */
import { AlertTriangle, RotateCw } from 'lucide-react'

import { ErrorState } from '@/components/error-state'
import { Button } from '@/components/ui/button'

/** 整块错误态（首屏失败、无旧数据可回显） */
export function DeviceListErrorState({
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
      <ErrorState className='min-h-80' title={title} description={description} onRetry={onRetry} />
    </div>
  )
}

/** 行内提示条（失败但保留旧数据：不清空列表，提示「看到的是上一次的数据」） */
export function DeviceListErrorBanner({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div
      role='alert'
      data-testid='device-list-error-banner'
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
