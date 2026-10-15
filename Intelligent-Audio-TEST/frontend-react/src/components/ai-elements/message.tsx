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
import { cva, type VariantProps } from 'class-variance-authority'
import type { ComponentProps, HTMLAttributes } from 'react'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'

type MessageRole = 'user' | 'assistant' | 'system'

export type MessageProps = HTMLAttributes<HTMLDivElement> & {
  from: MessageRole
}

/**
 * 消息行（08_AI对话页.md §1.1 消息对齐照搬）：
 * 组类 is-user / is-assistant 供 MessageContent 用 group-[.is-user:*] 取样式；
 * 交替对齐由调用方加 flex-row-reverse（user 右 / assistant 左）。
 */
export const Message = ({ className, from, ...props }: MessageProps) => (
  <div
    className={cn(
      'group flex w-full items-end justify-end gap-2',
      from === 'user' ? 'is-user' : 'is-assistant flex-row-reverse justify-end',
      className
    )}
    {...props}
  />
)

/**
 * 消息内容（§1.1 双宽语言照 message-styles 逐值）：
 * - user 右气泡紧凑：rounded-2xl rounded-br-md border border-border/70 bg-muted/70 px-4 py-2.5 shadow-sm max-w-[85%] sm:max-w-[62ch]
 * - assistant 左平铺文档面：bg-transparent p-0 w-full max-w-[78ch] [font-family:var(--font-body)] text-foreground/90
 * - 全局 text-[0.95rem] leading-6 break-words whitespace-pre-wrap sm:text-[0.975rem] sm:leading-7
 */
const messageContentVariants = cva('flex flex-col gap-2 text-sm', {
  variants: {
    variant: {
      contained: [
        'max-w-[100%] px-3 py-1',
        'group-[.is-user]:bg-primary group-[.is-user]:text-primary-foreground',
        'group-[.is-assistant]:bg-secondary group-[.is-assistant]:text-foreground',
      ],
      flat: [
        'text-[0.95rem] leading-6 break-words whitespace-pre-wrap sm:text-[0.975rem] sm:leading-7',
        '[font-family:var(--font-body)] text-foreground/90',
        'group-[.is-user]:max-w-[85%] group-[.is-user]:sm:max-w-[62ch]',
        'group-[.is-user]:rounded-2xl group-[.is-user]:rounded-br-md',
        'group-[.is-user]:border group-[.is-user]:border-border/70',
        'group-[.is-user]:bg-muted/70 group-[.is-user]:px-4 group-[.is-user]:py-2.5',
        'group-[.is-user]:shadow-sm',
        'group-[.is-assistant]:w-full group-[.is-assistant]:max-w-[78ch]',
        'group-[.is-assistant]:bg-transparent group-[.is-assistant]:p-0',
      ],
    },
  },
  defaultVariants: {
    variant: 'contained',
  },
})

export type MessageContentProps = HTMLAttributes<HTMLDivElement> &
  VariantProps<typeof messageContentVariants>

export const MessageContent = ({
  children,
  className,
  variant,
  ...props
}: MessageContentProps) => (
  <div
    className={cn(messageContentVariants({ variant, className }))}
    {...props}
  >
    {children}
  </div>
)

export type MessageAvatarProps = ComponentProps<typeof Avatar> & {
  src: string
  name?: string
}

export const MessageAvatar = ({
  src,
  name,
  className,
  ...props
}: MessageAvatarProps) => (
  <Avatar className={cn('ring-border size-8 ring-1', className)} {...props}>
    <AvatarImage alt='' className='mt-0 mb-0' src={src} />
    <AvatarFallback>{name?.slice(0, 2) || 'AI'}</AvatarFallback>
  </Avatar>
)
