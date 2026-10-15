/**
 * StatBadge 统计徽章（features/tasks 页面级 UI 件；移植 newAPI common-logs-stats
 * 形态：`border-border/60 bg-muted/25 inline-flex h-7 items-center gap-2 rounded-md
 * border px-2.5 text-xs shadow-xs` + 色条 `h-3.5 w-0.5 rounded-full` + mono 数值）。
 * 色条语义由调用方传入（09_任务域.md §3.5：neutral/warning/info/success/destructive）。
 */
import * as React from 'react'

import { cn } from '@/lib/utils'

export interface StatBadgeProps extends React.ComponentProps<'span'> {
  label: string
  value: number | string
  /** 色条类（bg-success / bg-warning / bg-info / bg-destructive / bg-neutral） */
  colorClass?: string
}

export function StatBadge({
  label,
  value,
  colorClass = 'bg-neutral',
  className,
  ...props
}: StatBadgeProps) {
  return (
    <span
      data-slot='stat-badge'
      className={cn(
        'border-border/60 bg-muted/25 inline-flex h-7 items-center gap-2 rounded-md border px-2.5 text-xs shadow-xs',
        className
      )}
      {...props}
    >
      <span aria-hidden='true' className={cn('h-3.5 w-0.5 rounded-full', colorClass)} />
      <span className='text-muted-foreground'>{label}</span>
      <span className='font-mono tabular-nums font-medium'>{value}</span>
    </span>
  )
}
