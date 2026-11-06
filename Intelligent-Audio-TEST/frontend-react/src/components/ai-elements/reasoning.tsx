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

import { Brain, ChevronDown } from 'lucide-react'
import type { ComponentProps } from 'react'

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

import { Response } from './response'
import { Shimmer } from './shimmer'

export type ReasoningProps = ComponentProps<typeof Collapsible> & {
  isStreaming?: boolean
  duration?: number
}

/**
 * 思考过程折叠（08_AI对话页.md §3.4 照 newAPI reasoning.tsx）：
 * 流式中 Shimmer「思考中...」，完成后「思考了 {n} 秒」；ChevronDown 200ms 旋转。
 */
export const Reasoning = ({
  className,
  isStreaming = false,
  duration = 0,
  children,
  ...props
}: ReasoningProps) => (
  <Collapsible className={cn('not-prose mb-4', className)} {...props}>
    {children}
  </Collapsible>
)

export type ReasoningTriggerProps = ComponentProps<typeof CollapsibleTrigger> & {
  isStreaming?: boolean
  duration?: number
}

export const ReasoningTrigger = ({
  className,
  isStreaming = false,
  duration = 0,
  children,
  ...props
}: ReasoningTriggerProps) => (
  <CollapsibleTrigger
    className={cn(
      'text-muted-foreground hover:text-foreground inline-grid w-fit max-w-full grid-cols-[0.875rem_minmax(0,auto)_0.875rem] items-center gap-1.5 text-sm leading-none transition-colors [&_p]:m-0',
      className
    )}
    {...props}
  >
    {children ?? (
      <>
        <span className='grid size-3.5 place-items-center'>
          <Brain className='size-3.5' />
        </span>
        <span className='min-w-0 truncate leading-none'>
          {isStreaming ? (
            <Shimmer duration={1}>思考中...</Shimmer>
          ) : (
            `思考了 ${duration} 秒`
          )}
        </span>
        <span className='grid size-3.5 place-items-center'>
          <ChevronDown className='size-3.5 transition-transform duration-200 ease-out group-data-[panel-open]:rotate-180' />
        </span>
      </>
    )}
  </CollapsibleTrigger>
)

export type ReasoningContentProps = ComponentProps<typeof CollapsibleContent> & {
  children: string
}

export const ReasoningContent = ({
  className,
  children,
  ...props
}: ReasoningContentProps) => (
  <CollapsibleContent
    className={cn(
      'border-border/70 text-muted-foreground mt-2 ml-1.5 border-l pl-3 text-sm leading-5 outline-none',
      className
    )}
    {...props}
  >
    <Response className='grid gap-1.5 [&_li]:my-0.5 [&_ol]:my-1.5 [&_p]:my-1.5 [&_p]:leading-5 [&_ul]:my-1.5'>
      {children}
    </Response>
  </CollapsibleContent>
)
