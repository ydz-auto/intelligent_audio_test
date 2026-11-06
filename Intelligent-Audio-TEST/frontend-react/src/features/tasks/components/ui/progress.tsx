/**
 * Progress 进度条（features/tasks 页面级 UI 件；基座 components/ui/ 未提供，
 * 照 09_任务域.md §7 token 口径实现——指示 `bg-primary`、失败段 `bg-destructive` 叠加）。
 * 纯 token 驱动，深浅色/多主题自动成立，无硬编码品牌色。
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

export interface ProgressProps extends React.ComponentProps<'div'> {
  /** 进度 0-100 */
  value?: number
  /** 失败进度（0-100，可选；叠加 destructive 段，§4.3） */
  failedValue?: number
  /** 尺寸 h-1（列表）| h-2（详情总进度） */
  size?: 'xs' | 'sm' | 'md'
}

export function Progress({
  value = 0,
  failedValue = 0,
  size = 'sm',
  className,
  ...props
}: ProgressProps) {
  const clamped = Math.min(100, Math.max(0, value))
  const failed = Math.min(100, Math.max(0, failedValue))

  return (
    <div
      data-slot='progress'
      role='progressbar'
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      className={cn(
        'bg-muted/60 relative w-full overflow-hidden rounded-full',
        size === 'xs' && 'h-1',
        size === 'sm' && 'h-1.5',
        size === 'md' && 'h-2',
        className
      )}
      {...props}
    >
      {failed > 0 && (
        <div
          className='bg-destructive absolute inset-y-0 left-0 transition-all'
          style={{ width: `${failed}%` }}
        />
      )}
      <div
        className='bg-primary absolute inset-y-0 left-0 transition-all'
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}
