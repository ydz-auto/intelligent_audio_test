/**
 * 「当前算法」大卡（INT-436 组件契约复用，INT-442 报告展示页落位）。
 * 工作台概览卡形态（bg-card rounded-2xl border shadow-xs + hero 详情 + 切换钮）；
 * 数据读全局算法 store（localStorage iatp:algorithm:v1）× GET /algorithm/definitions；
 * 切换入口=算法选择 Dialog（Command 搜索 + 卡片网格双通道），写回同一全局 store——
 * 一次切换全局生效，列表请求自动附 algorithm_type（15_报告域.md §2.1）。
 * 无 algorithm:read（device_admin/guest）只读降级条：仅显示当前算法名，隐藏切换钮与描述。
 */
import { Check, ChevronsUpDown, Cpu, Layers, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { IconBadge } from '@/components/ui/icon-badge'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useCurrentAlgorithm } from '@/application/reports-showcase/use-current-algorithm'
import { MOCK_ALGORITHM_OPTIONS } from '@/infrastructure/mock/reports-mock'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { cn } from '@/lib/utils'

/** 全部算法 sentinel（store 为字符串；空串=「全部算法」态，列表不附 algorithm_type） */
export const ALL_ALGORITHMS_SENTINEL = ''

interface CurrentAlgorithmCardProps {
  /** 只读态 Tooltip 文案（无 algorithm:read 降级说明） */
  className?: string
}

export function CurrentAlgorithmCard({ className }: CurrentAlgorithmCardProps) {
  const { algorithmType, definition, isLoading, isReadonly, isFailed, isAllAlgorithms } =
    useCurrentAlgorithm()
  const setAlgorithmId = useAlgorithmStore((s) => s.setAlgorithmId)

  const [selectorOpen, setSelectorOpen] = useState(false)

  if (isReadonly) {
    return (
      <div
        className={cn(
          'bg-card rounded-2xl border shadow-xs flex items-center justify-between gap-2 px-4 py-3 sm:px-5',
          className
        )}
      >
        <span className='text-muted-foreground text-xs font-medium'>当前算法</span>
        <Tooltip>
          <TooltipTrigger render={<span className='text-sm font-medium' />}>
            {isAllAlgorithms ? '全部算法' : (definition?.name ?? algorithmType ?? '全部算法')}
          </TooltipTrigger>
          <TooltipContent>无算法查看权限，仅显示存储值</TooltipContent>
        </Tooltip>
      </div>
    )
  }

  const handleSelect = (value: string | null) => {
    if (value === null) {
      setAlgorithmId(ALL_ALGORITHMS_SENTINEL)
      toast.success('已恢复全部算法')
    } else {
      const option = MOCK_ALGORITHM_OPTIONS.find((o) => o.value === value)
      setAlgorithmId(value)
      toast.success(`已切换全局算法为 ${option?.name ?? value}`)
    }
    setSelectorOpen(false)
  }

  return (
    <div
      className={cn(
        'bg-card overflow-hidden rounded-2xl border shadow-xs',
        className
      )}
    >
      <div className='relative overflow-hidden p-4 sm:p-5'>
        <div className='grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]'>
          <div className='flex min-w-0 flex-col gap-1.5'>
            <div className='flex items-center gap-2'>
              <span className='text-muted-foreground text-xs font-medium tracking-wider uppercase'>
                当前算法
              </span>
              <IconBadge tone='primary' size='sm'>
                <Cpu aria-hidden='true' className='size-3.5' />
              </IconBadge>
            </div>

            {isLoading ? (
              <div className='space-y-2'>
                <Skeleton className='h-6 w-44' />
                <Skeleton className='h-4 w-full max-w-72' />
              </div>
            ) : isFailed ? (
              <>
                <h3 className='text-xl font-semibold tracking-tight'>
                  {isAllAlgorithms ? '全部算法' : algorithmType}
                </h3>
                <p className='text-muted-foreground text-sm'>
                  算法详情暂不可用
                </p>
              </>
            ) : (
              <>
                <h3 className='text-xl font-semibold tracking-tight'>
                  {isAllAlgorithms ? '全部算法' : definition?.name}
                </h3>
                <div className='flex flex-wrap items-center gap-1.5'>
                  {!isAllAlgorithms && definition?.group_name && (
                    <Badge variant='outline'>{definition.group_name}</Badge>
                  )}
                  {!isAllAlgorithms && (
                    <Badge variant='outline'>{definition?.status === 'online' ? '在线' : '离线'}</Badge>
                  )}
                </div>
                <p className='text-muted-foreground text-sm leading-5 line-clamp-2'>
                  {isAllAlgorithms
                    ? '当前未按算法筛选，任务、用例、设备、报告、日志列表展示全部算法数据。'
                    : definition?.description}
                </p>
              </>
            )}
          </div>

          <div className='flex flex-col items-start gap-2 lg:items-end lg:justify-center'>
            <Button
              size='sm'
              className='h-9 rounded-lg px-3 font-medium shadow-sm'
              aria-haspopup='dialog'
              onClick={() => setSelectorOpen(true)}
            >
              <Cpu aria-hidden='true' className='size-4' />
              切换算法
              <ChevronsUpDown aria-hidden='true' className='size-4 opacity-60' />
            </Button>
            <span className='text-muted-foreground text-xs'>
              切换后全局生效：任务、用例、设备、报告、日志列表将按此算法过滤
            </span>
          </div>
        </div>
      </div>

      <AlgorithmSelectorDialog
        open={selectorOpen}
        onOpenChange={setSelectorOpen}
        currentValue={isAllAlgorithms ? null : algorithmType}
        onSelect={handleSelect}
      />
    </div>
  )
}

/** 算法选择 Dialog（INT-355 §3.4 双通道选择器：Command 搜索 + 卡片网格，写回全局 store） */
function AlgorithmSelectorDialog({
  open,
  onOpenChange,
  currentValue,
  onSelect,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentValue: string | null
  onSelect: (value: string | null) => void
}) {
  const [query, setQuery] = useState('')
  const [browseAll, setBrowseAll] = useState(false)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return MOCK_ALGORITHM_OPTIONS
    return MOCK_ALGORITHM_OPTIONS.filter(
      (a) => a.name.toLowerCase().includes(q) || (a.group_name ?? '').toLowerCase().includes(q)
    )
  }, [query])

  const groups = useMemo(() => {
    const map = new Map<string, typeof MOCK_ALGORITHM_OPTIONS>()
    for (const option of MOCK_ALGORITHM_OPTIONS) {
      const key = option.group_name ?? '其他'
      const list = map.get(key) ?? []
      list.push(option)
      map.set(key, list)
    }
    return [...map.entries()]
  }, [])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>选择算法</DialogTitle>
        </DialogHeader>

        <div className='relative'>
          <Search
            aria-hidden='true'
            className='text-muted-foreground absolute start-2 top-1/2 size-4 -translate-y-1/2'
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder='搜索算法名称…'
            className='h-9 ps-8'
          />
        </div>

        {!browseAll ? (
          <div className='max-h-72 overflow-auto'>
            <button
              type='button'
              className={cn(
                'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-2 text-start text-sm transition-colors',
                currentValue === null && 'bg-accent'
              )}
              onClick={() => onSelect(null)}
            >
              <Layers aria-hidden='true' className='size-4 shrink-0 text-muted-foreground' />
              <span className='flex-1'>全部算法</span>
              {currentValue === null && <Check aria-hidden='true' className='size-4' />}
            </button>
            {groups.map(([group, options]) => (
              <div key={group}>
                <p className='text-muted-foreground px-2 pt-3 pb-1 text-xs font-medium'>
                  {group}
                </p>
                {options.map((option) => (
                  <button
                    key={option.value}
                    type='button'
                    className={cn(
                      'hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-2 text-start text-sm transition-colors',
                      currentValue === option.value && 'bg-accent'
                    )}
                    onClick={() => onSelect(option.value)}
                  >
                    <span className='flex-1'>
                      {option.name}
                      <Badge variant='secondary' className='ms-2 align-middle'>
                        {option.group_name}
                      </Badge>
                    </span>
                    {currentValue === option.value && (
                      <Check aria-hidden='true' className='size-4' />
                    )}
                  </button>
                ))}
              </div>
            ))}
            {filtered.length === 0 && query && (
              <p className='text-muted-foreground px-3 py-6 text-center text-sm'>
                未找到匹配算法
              </p>
            )}
          </div>
        ) : (
          <div className='grid max-h-80 gap-3 overflow-auto sm:grid-cols-2 lg:grid-cols-3'>
            {filtered.map((option) => (
              <button
                key={option.value}
                type='button'
                className={cn(
                  'rounded-xl border p-4 text-start transition-colors',
                  currentValue === option.value
                    ? 'border-primary ring-primary/20 ring-2'
                    : 'hover:bg-accent'
                )}
                onClick={() => onSelect(option.value)}
              >
                <IconBadge tone='primary' size='lg'>
                  <Cpu aria-hidden='true' className='size-5' />
                </IconBadge>
                <p className='mt-2 font-medium'>{option.name}</p>
                <Badge variant='outline' className='mt-1'>
                  {option.group_name}
                </Badge>
              </button>
            ))}
            {filtered.length === 0 && (
              <p className='text-muted-foreground col-span-full px-3 py-6 text-center text-sm'>
                未找到匹配算法
              </p>
            )}
          </div>
        )}

        <div className='flex items-center justify-between'>
          <Button
            variant='ghost'
            size='sm'
            onClick={() => setBrowseAll((v) => !v)}
          >
            {browseAll ? '收起' : '浏览全部'}
          </Button>
          <Button variant='ghost' size='sm' onClick={() => setQuery('')}>
            清空搜索
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
