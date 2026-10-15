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
'use client'

import {
  CheckCircle2,
  ChevronDown,
  Circle,
  Clock,
  Wrench,
  XCircle,
} from 'lucide-react'
import { type ComponentProps, type ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

import type { AgentToolStatus } from '@/domain/models/aiChat'

type ToolStatus = AgentToolStatus

const STATUS_META: Record<ToolStatus, { label: string; icon: ReactNode }> = {
  pending: {
    label: '等待中',
    icon: <Circle className='size-4' />,
  },
  running: {
    label: '执行中',
    icon: <Clock className='size-4 animate-pulse' />,
  },
  completed: {
    label: '已完成',
    icon: <CheckCircle2 className='text-success size-4' />,
  },
  error: {
    label: '失败',
    icon: <XCircle className='text-destructive size-4' />,
  },
}

export type ToolProps = ComponentProps<typeof Collapsible>

/** 工具执行卡（08_AI对话页.md §3.4 照 newAPI tool.tsx：Collapsible 卡 + 状态徽章） */
export const Tool = ({ className, children, ...props }: ToolProps) => (
  <Collapsible
    className={cn('not-prose mb-4 w-full rounded-md border', className)}
    {...props}
  >
    {children}
  </Collapsible>
)

export type ToolHeaderProps = ComponentProps<typeof CollapsibleTrigger> & {
  title?: ReactNode
  status: ToolStatus
}

export const ToolHeader = ({
  className,
  title,
  status,
  ...props
}: ToolHeaderProps) => {
  const meta = STATUS_META[status]

  return (
    <CollapsibleTrigger
      className={cn(
        'group flex w-full items-center justify-between gap-4 p-3',
        className
      )}
      {...props}
    >
      <div className='flex items-center gap-2'>
        <Wrench className='text-muted-foreground size-4' />
        <span className='text-sm font-medium'>{title}</span>
        <Badge className='gap-1.5 text-xs' variant='secondary'>
          {meta.icon}
          {meta.label}
        </Badge>
      </div>
      <ChevronDown className='text-muted-foreground size-4 transition-transform group-data-[panel-open]:rotate-180' />
    </CollapsibleTrigger>
  )
}

export type ToolContentProps = ComponentProps<typeof CollapsibleContent>

export const ToolContent = ({
  className,
  children,
  ...props
}: ToolContentProps) => (
  <CollapsibleContent
    className={cn(
      'text-popover-foreground outline-none data-open:animate-in data-closed:animate-out',
      className
    )}
    {...props}
  >
    {children}
  </CollapsibleContent>
)

export type ToolBodyProps = ComponentProps<'div'>

export const ToolBody = ({ className, children, ...props }: ToolBodyProps) => (
  <div className={cn('space-y-2 p-4', className)} {...props}>
    {children}
  </div>
)
