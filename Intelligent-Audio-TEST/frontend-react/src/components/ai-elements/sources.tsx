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

import { BookOpen, ChevronDown } from 'lucide-react'
import type { ComponentProps, ReactNode } from 'react'

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

export type SourcesProps = ComponentProps<typeof Collapsible>

/**
 * 数据来源折叠（08_AI对话页.md §3.4 照 newAPI sources.tsx）：
 * 「已使用 {n} 处数据来源」+ sourceRef 列表；无法证明来源的数值标「待核实」（页面级处理）。
 */
export const Sources = ({ className, children, ...props }: SourcesProps) => (
  <Collapsible
    className={cn('text-primary not-prose mb-4 text-xs', className)}
    {...props}
  >
    {children}
  </Collapsible>
)

export type SourcesTriggerProps = ComponentProps<typeof CollapsibleTrigger> & {
  count: number
}

export const SourcesTrigger = ({
  className,
  count,
  children,
  ...props
}: SourcesTriggerProps) => (
  <CollapsibleTrigger className={cn('flex items-center gap-2', className)} {...props}>
    {children ?? (
      <>
        <p className='font-medium'>已使用 {count} 处数据来源</p>
        <ChevronDown className='size-4 transition-transform duration-200 group-data-[panel-open]:rotate-180' />
      </>
    )}
  </CollapsibleTrigger>
)

export type SourcesContentProps = ComponentProps<typeof CollapsibleContent>

export const SourcesContent = ({
  className,
  children,
  ...props
}: SourcesContentProps) => (
  <CollapsibleContent
    className={cn(
      'border-border/70 mt-3 ml-2 flex w-fit flex-col gap-2 border-l pl-4 outline-none',
      className
    )}
    {...props}
  >
    {children}
  </CollapsibleContent>
)

export type SourceProps = ComponentProps<'a'> & {
  title?: ReactNode
}

export const Source = ({ href, title, children, ...props }: SourceProps) => (
  <a
    className='flex items-center gap-2'
    href={href}
    rel='noreferrer'
    target='_blank'
    {...props}
  >
    {children ?? (
      <>
        <BookOpen className='size-4' />
        <span className='block font-medium'>{title}</span>
      </>
    )}
  </a>
)
