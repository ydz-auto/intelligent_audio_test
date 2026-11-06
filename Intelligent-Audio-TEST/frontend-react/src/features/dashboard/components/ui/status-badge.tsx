/*
Copyright (C) 2023-2026 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/
/**
 * StatusBadge 状态徽章（移植自 newAPI web/src/components/status-badge.tsx 工作台所需子集；
 * 完整版含 copyable/autoColor/StatusBadgeList——随 INT-354 任务域卡通用化移植，
 * 配色映射同源：09_任务域.md §3.6.1 执行状态徽章走本件 variant）。
 */
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'

import { cn } from '@/lib/utils'

export const textColorMap = {
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-destructive',
  info: 'text-info',
  neutral: 'text-muted-foreground',
  purple: 'text-chart-4',
} as const

export const dotColorMap = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-destructive',
  info: 'bg-info',
  neutral: 'bg-neutral',
  purple: 'bg-chart-4',
} as const

export type StatusVariant = keyof typeof textColorMap

export type StatusBadgeType = 'badge' | 'text' | 'underline'

const sizeMap = {
  sm: 'h-5 gap-1 px-1.5 text-sm leading-none',
  md: 'h-5 gap-1 px-1.5 text-sm leading-none',
  lg: 'h-6 gap-1.5 px-2 text-sm leading-none',
} as const

const textSizeMap = {
  sm: 'gap-1 text-sm leading-none',
  md: 'gap-1 text-sm leading-none',
  lg: 'gap-1.5 text-sm leading-none',
} as const

export interface StatusBadgeProps
  extends Omit<React.HTMLAttributes<HTMLSpanElement>, 'children'> {
  label?: string
  children?: React.ReactNode
  icon?: LucideIcon
  pulse?: boolean
  variant?: StatusVariant | null
  size?: 'sm' | 'md' | 'lg' | null
  type?: StatusBadgeType
}

export function StatusBadge({
  label,
  children,
  icon: Icon,
  variant,
  size = 'sm',
  pulse = false,
  type = 'badge',
  className,
  ...props
}: StatusBadgeProps) {
  const computedVariant: StatusVariant = variant ?? 'neutral'

  const content =
    children ??
    (label ? (
      <span className='min-w-0 truncate leading-normal'>{label}</span>
    ) : null)

  const isBadge = type === 'badge'

  return (
    <span
      data-slot='status-badge'
      className={cn(
        'inline-flex w-fit max-w-full min-w-0 shrink items-center font-medium tracking-normal whitespace-nowrap transition-colors',
        isBadge
          ? cn('rounded-4xl', sizeMap[size ?? 'sm'])
          : cn(
              textSizeMap[size ?? 'sm'],
              type === 'underline' && 'border-b border-current pb-px'
            ),
        textColorMap[computedVariant],
        pulse && 'animate-pulse',
        className
      )}
      title={label || undefined}
      {...props}
    >
      {Icon && <Icon className='size-3.5 shrink-0' />}
      {content}
    </span>
  )
}
