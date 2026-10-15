/**
 * 搜索框（移植自 newAPI pricing components/search-bar.tsx，规范 §3.5 引用）：
 * h-10 圆角输入 + 聚焦 ring-primary/20 + ⌘K 聚焦 / X 清除。placeholder 走本卡文案。
 */
import { Search, X } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface SearchBarProps {
  value: string
  onChange: (value: string) => void
  onClear: () => void
  placeholder?: string
  className?: string
}

export function SearchBar({
  value,
  onChange,
  onClear,
  placeholder = '搜索...',
  className,
}: SearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        inputRef.current?.focus()
      }
      if (event.key === 'Escape') inputRef.current?.blur()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <div className={cn('relative', className)}>
      <Search
        className='text-muted-foreground/60 pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2'
        aria-hidden='true'
      />
      <input
        ref={inputRef}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className='border-border/60 bg-background placeholder:text-muted-foreground/50 hover:border-border focus:border-primary/50 focus:ring-primary/20 h-10 w-full rounded-lg border pr-16 pl-10 text-sm transition-all outline-none focus:ring-2'
      />
      {value ? (
        <Button
          variant='ghost'
          size='icon'
          aria-label='清除搜索'
          className='text-muted-foreground/60 hover:text-foreground absolute top-1/2 right-2 size-7 -translate-y-1/2'
          onClick={onClear}
        >
          <X className='size-4' />
        </Button>
      ) : (
        <kbd className='bg-muted text-muted-foreground pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 rounded border px-1.5 py-0.5 font-mono text-[10px] sm:inline-block'>
          ⌘K
        </kbd>
      )}
    </div>
  )
}
