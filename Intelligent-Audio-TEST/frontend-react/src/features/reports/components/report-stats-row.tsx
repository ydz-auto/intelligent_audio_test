/**
 * 统计徽章行（移植自 newAPI usage-logs common-logs-stats StatBadge 形态，规范 §3.4）：
 * 全部/已发布/草稿/对比报告 ×4，数据 GET /reports/tab-counts，点击=快速筛选（写状态/类型筛选，不切页签）。
 */
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { ReportCounts } from '@/domain/models/report'

type BadgeKind = 'all' | 'published' | 'draft' | 'comparison'

const STAT_BADGES: {
  kind: BadgeKind
  label: string
  accent: string
  active?: (counts: ReportCounts) => boolean
}[] = [
  { kind: 'all', label: '全部报告', accent: 'bg-neutral' },
  { kind: 'published', label: '已发布', accent: 'bg-success' },
  { kind: 'draft', label: '草稿', accent: 'bg-warning' },
  { kind: 'comparison', label: '对比报告', accent: 'bg-info' },
]

interface ReportStatsRowProps {
  counts?: ReportCounts
  isLoading?: boolean
  /** 当前生效的快速筛选（决定选中态；无筛选时不选中任何徽章） */
  activeFilter?: Partial<{ status: string; type: string }>
  onQuickFilter: (kind: BadgeKind) => void
}

export type { BadgeKind }

export function ReportStatsRow({
  counts,
  isLoading,
  activeFilter,
  onQuickFilter,
}: ReportStatsRowProps) {
  if (isLoading && !counts) {
    return (
      <div className='flex flex-wrap items-center gap-2' aria-busy='true'>
        <Skeleton className='h-7 w-[150px] rounded-md' />
        <Skeleton className='h-7 w-[100px] rounded-md' />
        <Skeleton className='h-7 w-[120px] rounded-md' />
        <Skeleton className='h-7 w-[120px] rounded-md' />
      </div>
    )
  }

  const valueOf = (kind: BadgeKind): number => {
    if (!counts) return 0
    switch (kind) {
      case 'all':
        return counts.all
      case 'published':
        return counts.published
      case 'draft':
        return counts.draft
      case 'comparison':
        return counts.comparison
    }
  }

  const isActive = (kind: BadgeKind): boolean => {
    if (!activeFilter) return false
    if (kind === 'all') return !activeFilter.status && !activeFilter.type
    if (kind === 'published' || kind === 'draft') {
      return activeFilter.status === kind
    }
    if (kind === 'comparison') {
      return (
        activeFilter.type === 'comparison' ||
        activeFilter.type === 'secondary_comparison'
      )
    }
    return false
  }

  return (
    <div className='flex flex-wrap items-center gap-2'>
      {STAT_BADGES.map((badge) => {
        const active = isActive(badge.kind)
        return (
          <button
            key={badge.kind}
            type='button'
            onClick={() => onQuickFilter(badge.kind)}
            aria-pressed={active}
            title='统计为全量报告计数，点击徽章快速筛选'
            className={cn(
              'border-border/60 bg-muted/25 hover:bg-muted/50 inline-flex h-7 items-center gap-2 rounded-md border px-2.5 text-xs shadow-xs transition-colors',
              active && 'bg-accent text-foreground'
            )}
          >
            <span
              aria-hidden='true'
              className={cn('h-3.5 w-0.5 rounded-full', badge.accent)}
            />
            <span className='text-muted-foreground'>{badge.label}</span>
            <span className='text-foreground/85 font-mono font-semibold tabular-nums'>
              {valueOf(badge.kind)}
            </span>
          </button>
        )
      })}
    </div>
  )
}
