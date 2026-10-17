/**
 * 全局算法切换器（导航栏右区；02_导航栏.md §2.3/§3.4）。
 * 接线壳 INT-607：数据源换 GET /algorithm/options（algorithm:read，仅在线算法）；
 * 无 algorithm:read（device_admin/guest）整钮隐藏（隐藏而非置灰，基座卡 §9.2）。
 * 切换写回 useAlgorithmStore（localStorage iatp:algorithm:v1），一次切换全局生效。
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
import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { cn } from '@/lib/utils'

export function GlobalAlgorithmSwitcher() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)
  const setAlgorithmId = useAlgorithmStore((s) => s.setAlgorithmId)
  const { options, isLoading, isError, refetch, canRead } = useAlgorithmOptions()

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter((option) => option.name.toLowerCase().includes(q))
  }, [options, query])

  const current = options.find((option) => option.value === algorithmId)
  const isAll = !algorithmId

  // 无 algorithm:read（device_admin/guest）：整钮不渲染（隐藏而非置灰）
  if (!canRead) return null

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
          {isAll ? '全部算法' : (current?.name ?? '选择算法')}
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
          {isError ? (
            <div className='px-3 py-6 text-center'>
              <p className='text-muted-foreground text-sm'>加载失败</p>
              <Button
                variant='ghost'
                size='sm'
                className='mt-2'
                onClick={() => void refetch()}
              >
                重试
              </Button>
            </div>
          ) : isLoading ? (
            <p className='text-muted-foreground px-3 py-6 text-center text-sm'>
              加载中…
            </p>
          ) : filtered.length === 0 ? (
            <p className='text-muted-foreground px-3 py-6 text-center text-sm'>
              暂无匹配算法
            </p>
          ) : (
            <>
              <button
                type='button'
                className={cn(
                  'hover:bg-accent flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
                  isAll && 'bg-accent'
                )}
                onClick={() => {
                  setAlgorithmId('')
                  setOpen(false)
                }}
              >
                <span className='min-w-0 truncate'>全部算法</span>
                {isAll && (
                  <Check aria-hidden='true' className='size-4 shrink-0' />
                )}
              </button>
              {filtered.map((option) => (
                <button
                  key={option.value}
                  type='button'
                  className={cn(
                    'hover:bg-accent flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
                    option.value === algorithmId && 'bg-accent'
                  )}
                  onClick={() => {
                    setAlgorithmId(option.value)
                    setOpen(false)
                  }}
                >
                  <span className='min-w-0 truncate'>{option.name}</span>
                  {option.value === algorithmId && (
                    <Check aria-hidden='true' className='size-4 shrink-0' />
                  )}
                </button>
              ))}
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
