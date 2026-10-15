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

import { Check, Copy, RotateCcw, X } from 'lucide-react'
import { type ComponentProps, type ReactNode, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

type CodeBlockProps = ComponentProps<'div'> & {
  code: string
  collapsedLines?: number
  defaultCollapsed?: boolean
  enableCollapse?: boolean
  language?: string
  maxExpandedLines?: number
  showToolbar?: boolean
  title?: ReactNode
}

/**
 * 代码块（08_AI对话页.md §3.4 照 newAPI CodeBlock 版式；视觉稿无高亮引擎，
 * 用等宽 pre + 复制钮 + 折叠，无 shiki/CodeMirror 依赖）。
 */
export const CodeBlock = ({
  code,
  collapsedLines = 24,
  defaultCollapsed = false,
  enableCollapse = true,
  language,
  maxExpandedLines = 48,
  showToolbar = true,
  title,
  className,
  ...props
}: CodeBlockProps) => {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      toast.success('已复制')
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error('复制失败')
    }
  }

  const lineCount = code.split('\n').length
  const isCollapsible = enableCollapse && lineCount > collapsedLines

  return (
    <div
      className={cn(
        'bg-muted/50 border-border/70 my-2 w-full overflow-hidden rounded-lg border',
        className
      )}
      {...props}
    >
      {showToolbar && (
        <div className='border-border/70 flex items-center justify-between gap-2 border-b px-3 py-1.5'>
          <span className='text-muted-foreground truncate text-[11px]'>
            {title ?? (language ? language.toUpperCase() : '代码')}
          </span>
          <div className='flex items-center gap-1'>
            {isCollapsible && (
              <Button
                className='text-muted-foreground hover:text-foreground h-6 px-2 text-[11px]'
                onClick={() => setCollapsed((value) => !value)}
                size='sm'
                type='button'
                variant='ghost'
              >
                {collapsed ? '展开' : '折叠'}
              </Button>
            )}
            <Button
              className='text-muted-foreground hover:text-foreground h-6 w-6'
              onClick={handleCopy}
              size='icon'
              type='button'
              variant='ghost'
              aria-label='复制代码'
            >
              {copied ? (
                <Check className='text-success size-3.5' />
              ) : (
                <Copy className='size-3.5' />
              )}
            </Button>
          </div>
        </div>
      )}
      <pre
        className='overflow-x-auto px-3 py-2.5 text-xs leading-5'
        style={{
          maxHeight: collapsed
            ? `${Math.min(collapsedLines, maxExpandedLines) * 1.25}rem`
            : isCollapsible
              ? `${Math.min(lineCount, maxExpandedLines) * 1.25}rem`
              : undefined,
          overflowY: collapsed ? 'auto' : undefined,
        }}
      >
        <code className='font-mono text-foreground/90 whitespace-pre'>
          {collapsed ? `${code.slice(0, 2000)}…` : code}
        </code>
      </pre>
    </div>
  )
}

type CodeBlockEditorProps = Omit<
  ComponentProps<'div'>,
  'onChange' | 'title'
> & {
  title?: ReactNode
  value: string
  onChange: (value: string) => void
  onSave?: () => void
  onReset?: () => void
  onCancel?: () => void
  placeholder?: string
  rows?: number
  hasChanged?: boolean
  actions?: ReactNode
}

/**
 * Markdown 源码编辑器（08_AI对话页.md §3.4 照 newAPI playground-message-editor 版式：
 * 标题行「编辑」+ 未保存提示 + 保存并重发/保存/重置/取消钮组）。
 */
export const CodeBlockEditor = ({
  title,
  value,
  onChange,
  onSave,
  onReset,
  onCancel,
  placeholder,
  rows = 8,
  hasChanged,
  actions,
  className,
  ...props
}: CodeBlockEditorProps) => (
  <div className={cn('w-full', className)} {...props}>
    <div className='mb-1.5 flex items-center justify-between gap-2'>
      <span className='text-sm font-semibold'>{title ?? '编辑'}</span>
      <span className='text-muted-foreground text-xs'>
        {hasChanged ? '有未保存的更改' : '暂无更改'}
      </span>
    </div>
    <Textarea
      className='font-mono text-xs leading-5'
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      rows={rows}
      value={value}
    />
    <div className='mt-2 flex flex-wrap items-center gap-1.5'>
      {actions}
      {onSave && (
        <Button
          className='h-7 px-2.5 text-xs'
          onClick={onSave}
          size='sm'
          type='button'
        >
          保存
        </Button>
      )}
      {hasChanged && onReset && (
        <Button
          className='text-muted-foreground h-7 px-2.5 text-xs'
          onClick={onReset}
          size='sm'
          type='button'
          variant='ghost'
        >
          <RotateCcw className='size-3.5' />
          重置
        </Button>
      )}
      {onCancel && (
        <Button
          className='text-muted-foreground h-7 px-2.5 text-xs'
          onClick={onCancel}
          size='sm'
          type='button'
          variant='ghost'
        >
          <X className='size-3.5' />
          取消
        </Button>
      )}
    </div>
  </div>
)
