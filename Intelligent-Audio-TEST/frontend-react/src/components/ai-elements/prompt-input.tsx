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

import type { ComponentProps, ReactNode } from 'react'

import { Button, buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type PromptInputProps = ComponentProps<'form'>

/**
 * 输入卡壳（08_AI对话页.md §3.5 照 playground-input.tsx）：
 * form 承载卡壳样式（focus-within 主色描边 + 大阴影语言），提交逻辑由页面持有文本态。
 */
export const PromptInput = ({
  className,
  children,
  ...props
}: PromptInputProps) => (
  <form className={cn('relative', className)} {...props}>
    {children}
  </form>
)

export type PromptInputTextareaProps = ComponentProps<'textarea'>

export const PromptInputTextarea = ({
  className,
  ...props
}: PromptInputTextareaProps) => (
  <textarea
    data-slot='prompt-input-textarea'
    className={cn(
      'bg-transparent w-full resize-none outline-none placeholder:text-muted-foreground',
      className
    )}
    {...props}
  />
)

export type PromptInputFooterProps = ComponentProps<'div'>

export const PromptInputFooter = ({
  className,
  children,
  ...props
}: PromptInputFooterProps) => (
  <div className={cn('w-full', className)} {...props}>
    {children}
  </div>
)

export type PromptInputToolsProps = ComponentProps<'div'>

export const PromptInputTools = ({
  className,
  children,
  ...props
}: PromptInputToolsProps) => (
  <div className={cn('flex items-center gap-1', className)} {...props}>
    {children}
  </div>
)

export type PromptInputButtonProps = ComponentProps<typeof Button> & {
  children?: ReactNode
}

/** 输入区图标钮（ghost + icon 默认，页面级 className 覆盖尺寸/色彩） */
export const PromptInputButton = ({
  className,
  variant = 'ghost',
  size = 'icon',
  type = 'button',
  children,
  ...props
}: PromptInputButtonProps) => (
  <Button
    className={cn('shrink-0', className)}
    size={size}
    type={type}
    variant={variant}
    {...props}
  >
    {children}
  </Button>
)

export const promptInputButtonVariants = buttonVariants
