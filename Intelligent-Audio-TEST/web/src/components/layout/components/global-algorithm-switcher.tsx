/**
 * 全局算法切换器（导航栏右区第一项；02_导航栏.md §2.3）。
 * 红线④：选项为 mock 常量；TODO(API 接线): 换 GET /algorithms 并联动业务列表过滤。
 * Command（cmdk）检索件随后续卡移植，当前用 Input + 列表占位。
 */
import { useMemo, useState } from 'react'
import { Check, ChevronsUpDown, Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { MOCK_ALGORITHMS } from '@/domain/models/algorithm'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { cn } from '@/lib/utils'

export function GlobalAlgorithmSwitcher() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)
  const setAlgorithmId = useAlgorithmStore((s) => s.setAlgorithmId)

  const enabled = useMemo(
    () => MOCK_ALGORITHMS.filter((a) => a.enabled),
    []
  )
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return enabled
    return enabled.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q)
    )
  }, [enabled, query])

  const current = enabled.find((a) => a.id === algorithmId) ?? enabled[0]

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setQuery('')
      }}
    >
      <PopoverTrigger
        render={
          <Button
            variant='outline'
            size='sm'
            className='h-8 max-w-40 gap-1.5 px-2.5 font-normal'
            aria-label='切换全局算法'
          />
        }
      >
        <span className='text-muted-foreground hidden text-xs sm:inline'>
          算法
        </span>
        <span className='min-w-0 max-w-28 truncate'>
          {current?.name ?? '选择算法'}
        </span>
        <ChevronsUpDown aria-hidden='true' className='size-3.5 shrink-0' />
      </PopoverTrigger>
      <PopoverContent align='start' className='w-64 p-0'>
        <div className='border-b p-2'>
          <div className='relative'>
            <Search
              aria-hidden='true'
              className='text-muted-foreground absolute start-2 top-1/2 size-3.5 -translate-y-1/2'
            />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder='搜索算法…'
              className='h-8 ps-7'
            />
          </div>
        </div>
        <div className='max-h-64 overflow-auto p-1'>
          {filtered.length === 0 ? (
            <p className='text-muted-foreground px-3 py-6 text-center text-sm'>
              暂无匹配算法
            </p>
          ) : (
            filtered.map((algorithm) => (
              <button
                key={algorithm.id}
                type='button'
                className={cn(
                  'hover:bg-accent flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
                  algorithm.id === current?.id && 'bg-accent'
                )}
                onClick={() => {
                  setAlgorithmId(algorithm.id)
                  setOpen(false)
                }}
              >
                <span className='min-w-0'>
                  <span className='block truncate'>{algorithm.name}</span>
                  <span className='text-muted-foreground block truncate text-xs'>
                    {algorithm.description}
                  </span>
                </span>
                {algorithm.id === current?.id && (
                  <Check aria-hidden='true' className='size-4 shrink-0' />
                )}
              </button>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
