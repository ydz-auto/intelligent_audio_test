/**
 * 排行榜页「算法卡片网格」（14_benchmark排行.md §4.5，INT-442 口径修正：
 * 每算法一张大卡 + 全部算法首卡；**页内独立**——写回页内 store
 * useRankingAlgorithmStore，不写回全局算法 store，避免公开页污染全局）。
 * 数据源 GET /algorithm/definitions（algorithm:read）；无权限/未登录只读降级条；
 * 离线算法卡置灰不可选；榜单按算法过滤待后端立项（ReadModel 暂无算法维度）。
 */
import { AlertTriangle, Check, Cpu, Layers } from 'lucide-react'

import {
  buildParamSummary,
  useRankingAlgorithm,
} from '@/application/rankings/useRankingAlgorithm'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useRankingAlgorithmStore } from '@/infrastructure/stores/ranking-algorithm-store'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

/** 全部算法 sentinel（页内 store 为 null = 「全部算法」态） */
const ALL_ALGORITHMS_SENTINEL = null

export function RankingAlgorithmCardGrid(props: { className?: string }) {
  const {
    algorithmType,
    definitions,
    isLoading,
    isReadonly,
    isFailed,
    isAllAlgorithms,
  } = useRankingAlgorithm()
  const setAlgorithm = useRankingAlgorithmStore((s) => s.setAlgorithm)
  const clear = useRankingAlgorithmStore((s) => s.clear)

  const handleSelect = (type: string | null) => {
    if (type === ALL_ALGORITHMS_SENTINEL) {
      clear()
      toast.success('已恢复全部算法')
      return
    }
    const definition = definitions.find((d) => d.type === type)
    setAlgorithm(type)
    toast.success(`已切换榜单算法为 ${definition?.name ?? type}`)
  }

  return (
    <section
      aria-label='算法切换'
      className={cn('flex flex-col gap-2', props.className)}
    >
      <div className='flex flex-wrap items-baseline gap-x-2 gap-y-1'>
        <span className='text-muted-foreground text-xs font-medium tracking-wider uppercase'>
          算法切换
        </span>
        <span className='text-muted-foreground text-xs'>
          仅影响本页榜单，不改变全局算法。
        </span>
      </div>

      {isReadonly ? (
        <ReadonlyAlgorithmBar
          algorithmType={algorithmType}
          isAllAlgorithms={isAllAlgorithms}
        />
      ) : isLoading ? (
        <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
          {Array.from({ length: 4 }).map((_, index) => (
            <div
              key={index}
              className='border-border flex flex-col gap-2 rounded-xl border p-4'
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
          <AlertTriangle
            aria-hidden='true'
            className='text-warning size-4 shrink-0'
          />
          <span className='text-sm'>算法详情暂不可用</span>
          <span className='text-muted-foreground text-xs'>--</span>
        </div>
      ) : (
        <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
          {/* 全部算法首卡（value=null） */}
          <button
            type='button'
            aria-pressed={isAllAlgorithms}
            className={cn(
              'flex flex-col gap-2 rounded-xl border p-4 text-start transition-colors',
              isAllAlgorithms
                ? 'border-primary ring-primary/20 bg-primary/5 ring-2'
                : 'border-border hover:border-primary/40 hover:shadow-sm'
            )}
            onClick={() => handleSelect(ALL_ALGORITHMS_SENTINEL)}
          >
            <div className='flex items-start justify-between gap-2'>
              <span className='bg-muted text-muted-foreground flex size-10 shrink-0 items-center justify-center rounded-lg'>
                <Layers aria-hidden='true' className='size-5' />
              </span>
              {isAllAlgorithms && (
                <span className='flex items-center gap-1'>
                  <Check aria-hidden='true' className='text-primary size-4' />
                  <Badge variant='secondary' className='text-[11px]'>
                    当前
                  </Badge>
                </span>
              )}
            </div>
            <h3 className='text-sm font-semibold tracking-tight'>全部算法</h3>
            <p className='text-muted-foreground text-xs leading-5'>
              不按算法筛选，展示全部算法数据。
            </p>
          </button>

          {definitions.map((definition) => {
            const selected = algorithmType === definition.type
            const offline = definition.status === 'offline'
            const summary = buildParamSummary(definition)
            return (
              <button
                key={definition.type}
                type='button'
                aria-pressed={selected}
                disabled={offline}
                className={cn(
                  'flex flex-col gap-2 rounded-xl border p-4 text-start transition-colors',
                  selected
                    ? 'border-primary ring-primary/20 bg-primary/5 ring-2'
                    : 'border-border hover:border-primary/40 hover:shadow-sm',
                  offline && 'opacity-60 pointer-events-none'
                )}
                onClick={() => handleSelect(definition.type)}
              >
                <div className='flex items-start justify-between gap-2'>
                  <span className='bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-lg'>
                    <Cpu aria-hidden='true' className='size-5' />
                  </span>
                  {selected && (
                    <span className='flex items-center gap-1'>
                      <Check aria-hidden='true' className='text-primary size-4' />
                      <Badge variant='secondary' className='text-[11px]'>
                        当前
                      </Badge>
                    </span>
                  )}
                </div>
                <h3 className='text-sm font-semibold tracking-tight'>
                  {definition.name}
                </h3>
                <span className='flex flex-wrap items-center gap-1'>
                  {definition.groupName ? (
                    <Badge variant='outline'>{definition.groupName}</Badge>
                  ) : null}
                  <Badge
                    variant='outline'
                    className={cn(
                      definition.status === 'online' && 'text-success'
                    )}
                  >
                    {definition.status === 'online' ? '在线' : '离线'}
                  </Badge>
                </span>
                {summary ? (
                  <span className='text-muted-foreground text-xs'>
                    {summary}
                  </span>
                ) : null}
                <p className='text-muted-foreground text-sm leading-5 line-clamp-2'>
                  {definition.description}
                </p>
              </button>
            )
          })}
        </div>
      )}

      <p className='text-muted-foreground/70 text-xs'>
        按算法过滤待后端立项（排行数据暂无算法维度），当前榜单全量展示。
      </p>
    </section>
  )
}

/** 无 algorithm:read（device_admin/guest/未登录）只读降级条：首屏不空、榜单浏览不受影响 */
function ReadonlyAlgorithmBar(props: {
  algorithmType: string | null
  isAllAlgorithms: boolean
}) {
  return (
    <TooltipProvider delay={100}>
      <div className='bg-card rounded-2xl border shadow-xs flex items-center justify-between gap-2 px-4 py-3 sm:px-5'>
        <div className='flex items-center gap-2'>
          <span className='text-muted-foreground text-xs font-medium'>
            当前算法
          </span>
          <Tooltip>
            <TooltipTrigger className='cursor-default'>
              <span className='text-sm font-medium'>
                {props.isAllAlgorithms ? '全部算法' : props.algorithmType}
              </span>
            </TooltipTrigger>
            <TooltipContent side='top'>
              切换算法需登录并具备算法查看权限
            </TooltipContent>
          </Tooltip>
        </div>
        <span className='text-muted-foreground text-xs'>
          {props.isAllAlgorithms ? '全部算法' : '只读'}
        </span>
      </div>
    </TooltipProvider>
  )
}
