/**
 * 算法卡片网格（INT-486 负责人口径 2026-10-16：每算法一张大卡片，点击选中切换全局算法——
 * 非单张「当前算法」卡；用于工作台概览/排行榜/报告展示页算法选择区）。
 * 写回同一全局 store（localStorage iatp:algorithm:v1），一次切换全局生效；
 * 含「全部算法」sentinel 卡（store 空串=全部算法态，列表不附 algorithm_type 过滤）。
 * 无 algorithm:read（device_admin/guest）只读降级：仅显示当前存储值，卡片不可点。
 */
import { AlertTriangle, Check, Cpu, Layers } from 'lucide-react'
import { useMemo } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { IconBadge } from '@/components/ui/icon-badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useCurrentAlgorithm } from '@/application/reports-showcase/use-current-algorithm'
import { MOCK_ALGORITHM_DEFINITIONS } from '@/infrastructure/mock/reports-mock'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { cn } from '@/lib/utils'

/** 全部算法 sentinel（store 为字符串；空串=「全部算法」态，列表不附 algorithm_type） */
export const ALL_ALGORITHMS_SENTINEL = ''

interface AlgorithmCardGridProps {
  /** 标题（INT-486：工作台/排行榜/报告展示页算法选择区） */
  title?: string
  className?: string
}

export function AlgorithmCardGrid({
  title = '选择算法',
  className,
}: AlgorithmCardGridProps) {
  const { algorithmType, isLoading, isReadonly, isFailed, isAllAlgorithms } =
    useCurrentAlgorithm()
  const setAlgorithmId = useAlgorithmStore((s) => s.setAlgorithmId)

  const selectedType = isAllAlgorithms ? null : algorithmType

  const handleSelect = (value: string | null) => {
    if (value === null) {
      setAlgorithmId(ALL_ALGORITHMS_SENTINEL)
      toast.success('已恢复全部算法')
    } else {
      const option = MOCK_ALGORITHM_DEFINITIONS.find((o) => o.type === value)
      setAlgorithmId(value)
      toast.success(`已切换全局算法为 ${option?.name ?? value}`)
    }
  }

  const groups = useMemo(() => {
    const map = new Map<string, typeof MOCK_ALGORITHM_DEFINITIONS>()
    for (const option of MOCK_ALGORITHM_DEFINITIONS) {
      const key = option.group_name ?? '其他'
      const list = map.get(key) ?? []
      list.push(option)
      map.set(key, list)
    }
    return [...map.entries()]
  }, [])

  return (
    <section
      aria-label={title}
      className={cn('flex flex-col gap-2', className)}
    >
      <div className='flex items-center gap-2'>
        <IconBadge tone='primary' size='sm'>
          <Cpu aria-hidden='true' className='size-3.5' />
        </IconBadge>
        <span className='text-muted-foreground text-xs font-medium tracking-wider uppercase'>
          {title}
        </span>
        <span className='text-muted-foreground text-xs'>
          {isReadonly ? '（只读）' : '点击卡片切换全局算法，任务/用例/设备/报告/日志列表将按此算法过滤'}
        </span>
      </div>

      {isReadonly ? (
        <div className='bg-card rounded-2xl border shadow-xs flex items-center justify-between gap-2 px-4 py-3'>
          <span className='text-muted-foreground text-sm font-medium'>
            当前算法：{isAllAlgorithms ? '全部算法' : algorithmType}
          </span>
          <span className='text-muted-foreground text-xs'>无算法查看权限，仅显示存储值</span>
        </div>
      ) : isLoading ? (
        <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'>
          {Array.from({ length: 4 }).map((_, index) => (
            <div
              key={index}
              className='border-border flex flex-col gap-2 rounded-2xl border p-4'
            >
              <Skeleton className='size-10 rounded-lg' />
              <Skeleton className='h-4 w-24 rounded-md' />
              <Skeleton className='h-3 w-36 rounded-md' />
              <Skeleton className='h-3 w-full rounded-md' />
            </div>
          ))}
        </div>
      ) : isFailed ? (
        <div className='bg-card rounded-2xl border shadow-xs flex items-center gap-2 px-4 py-3'>
          <AlertTriangle aria-hidden='true' className='text-warning size-4 shrink-0' />
          <span className='text-sm'>算法详情暂不可用</span>
          <span className='text-muted-foreground text-xs'>
            当前算法：{isAllAlgorithms ? '全部算法' : algorithmType}
          </span>
        </div>
      ) : (
        <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'>
          {/* 全部算法卡 */}
          <button
            type='button'
            aria-pressed={isAllAlgorithms}
            className={cn(
              'flex flex-col gap-2 rounded-2xl border p-4 text-start transition-colors',
              isAllAlgorithms
                ? 'border-primary ring-primary/20 ring-2'
                : 'border-border hover:bg-muted/40'
            )}
            onClick={() => handleSelect(null)}
          >
            <div className='flex items-start justify-between gap-2'>
              <span className='bg-muted text-muted-foreground flex size-10 shrink-0 items-center justify-center rounded-lg'>
                <Layers aria-hidden='true' className='size-5' />
              </span>
              {isAllAlgorithms && (
                <Check aria-hidden='true' className='text-primary mt-1 size-4' />
              )}
            </div>
            <span className='font-medium'>全部算法</span>
            <span className='text-muted-foreground text-xs leading-5'>
              当前未按算法筛选，任务、用例、设备、报告、日志列表展示全部算法数据。
            </span>
          </button>

          {groups.map(([group, options]) => (
            <div key={group} className='contents'>
              {options.map((option) => {
                const selected = selectedType === option.type
                return (
                  <button
                    key={option.type}
                    type='button'
                    aria-pressed={selected}
                    className={cn(
                      'flex flex-col gap-2 rounded-2xl border p-4 text-start transition-colors',
                      selected
                        ? 'border-primary ring-primary/20 ring-2'
                        : 'border-border hover:bg-muted/40'
                    )}
                    onClick={() => handleSelect(option.type)}
                  >
                    <div className='flex items-start justify-between gap-2'>
                      <IconBadge tone='primary' size='lg'>
                        <Cpu aria-hidden='true' className='size-5' />
                      </IconBadge>
                      {selected && (
                        <Check aria-hidden='true' className='text-primary mt-1 size-4' />
                      )}
                    </div>
                    <span className='mt-1 font-medium'>{option.name}</span>
                    <span className='flex flex-wrap items-center gap-1'>
                      <Badge variant='outline'>{group}</Badge>
                      <Badge
                        variant={option.status === 'online' ? 'secondary' : 'outline'}
                        className='text-[11px]'
                      >
                        {option.status === 'online' ? '在线' : '离线'}
                      </Badge>
                    </span>
                    <span className='text-muted-foreground text-xs leading-5 line-clamp-2'>
                      {option.description}
                    </span>
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
