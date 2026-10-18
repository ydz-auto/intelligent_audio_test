/**
 * 全局算法切换器（导航栏右区第一项；02_导航栏.md §2.3）。
 * 数据源：真实 GET /algorithm/options（application/hooks/use-algorithm-options.ts，
 * 与工作台算法大卡同源）；无 algorithm:read 权限整钮隐藏（隐藏而非置灰）；
 * 持久化值不在当前 options（算法下线/删除）→ 静默回落「全部算法」；
 * 选中写全局 store（业务列表 algorithm_type 过滤参数同源）。
 */
import { useMemo, useState } from 'react'
import { Check, ChevronsUpDown, Search } from 'lucide-react'

import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { cn } from '@/lib/utils'

const ALL_LABEL = '全部算法'

export function GlobalAlgorithmSwitcher() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)
  const setAlgorithmId = useAlgorithmStore((s) => s.setAlgorithmId)
  const { options, isReadonly } = useAlgorithmOptions()

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q)
    )
  }, [options, query])

  // 无 algorithm:read 权限：整钮隐藏
  if (isReadonly) return null

  // 持久化值不在当前 options → 静默回落「全部算法」
  const current = options.find((a) => a.id === algorithmId)
  const isAll = !algorithmId || !current

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
          {isAll ? ALL_LABEL : current.name}
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
          {/* 全部算法（清空全局过滤） */}
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
            <span className='min-w-0'>
              <span className='block truncate'>{ALL_LABEL}</span>
              <span className='text-muted-foreground block truncate text-xs'>
                不过滤业务列表
              </span>
            </span>
            {isAll && <Check aria-hidden='true' className='size-4 shrink-0' />}
          </button>
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
