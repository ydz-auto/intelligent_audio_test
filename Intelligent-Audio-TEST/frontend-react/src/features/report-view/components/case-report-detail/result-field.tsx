/**
 * kv 字段渲染（15_报告域.md §3.5.5/3.5.6/3.5.4：JSON 格式化 / >200 字折叠 / 原样；
 * param_type==='audio_file' → 播放音频按钮）。
 */
import { ChevronDown, Play } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface ResultFieldValue {
  label?: string
  value: unknown
  type?: string
}

function formatValueText(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  }
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

export function ResultField({
  label,
  value,
  type,
  onPlayAudio,
}: ResultFieldValue & { onPlayAudio?: (value: unknown) => void }) {
  const isObject = typeof value === 'object' && value !== null
  const text = formatValueText(value)
  const needsCollapse = text.length > 200

  if (type === 'audio_file' && onPlayAudio) {
    return (
      <div className='flex items-center justify-between gap-2 border-b px-3 py-1.5 text-xs last:border-0'>
        {/* INT-2090 P3：音频字段名（label）超长时截断，不撑破行宽；title 悬停显完整名 */}
        <span className='text-muted-foreground min-w-0 flex-1 truncate' title={label}>
          {label}
        </span>
        <Button
          variant='outline'
          size='sm'
          className='h-6 shrink-0 gap-1 px-2 text-xs'
          onClick={() => onPlayAudio(value)}
        >
          <Play aria-hidden='true' className='size-3' />
          播放音频
        </Button>
      </div>
    )
  }

  return (
    <div className='flex flex-wrap items-start justify-between gap-2 border-b px-3 py-1.5 text-xs last:border-0'>
      <span className='text-muted-foreground shrink-0'>{label}</span>
      {isObject || needsCollapse ? (
        <CollapsibleValue text={text} />
      ) : (
        <span className='font-mono break-all text-right tabular-nums'>{text}</span>
      )}
    </div>
  )
}

function CollapsibleValue({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className='min-w-0 flex-1 text-right'>
      <pre
        className={cn(
          'text-muted-foreground overflow-x-auto font-mono text-xs whitespace-pre-wrap break-all text-left',
          open ? 'max-h-64 overflow-y-auto' : 'line-clamp-2'
        )}
      >
        {text}
      </pre>
      {text.length > 200 && (
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground h-5 gap-1 px-1 text-xs'
          onClick={() => setOpen((v) => !v)}
        >
          {open ? '收起' : '展开'}
          <ChevronDown aria-hidden='true' className={cn('size-3 transition-transform', open && 'rotate-180')} />
        </Button>
      )}
    </div>
  )
}
