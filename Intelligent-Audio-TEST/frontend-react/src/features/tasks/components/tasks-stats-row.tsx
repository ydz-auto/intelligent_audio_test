/**
 * 统计徽章行（09_任务域.md §3.5：7 枚 StatBadge，数据 GET /tasks/stats?granularity=day）。
 * 色条语义：总任务=neutral、待执行+排队中=warning、执行中=info、已完成=success、
 * 执行失败=destructive、已删除=neutral；数值 mono tabular-nums；加载中 Skeleton；失败整行隐藏。
 */
import { useQuery } from '@tanstack/react-query'

import { Skeleton } from '@/components/ui/skeleton'
import { usePermissions } from '@/application/hooks/use-permissions'
import { fetchTaskDomainStats } from '@/infrastructure/api/tasks-api'
import { STATS_BADGES } from '@/features/tasks/constants'
import { StatBadge } from '@/features/tasks/components/ui/stat-badge'

export function TasksStatsRow() {
  const { hasPermission } = usePermissions()
  /** INT-1289：无 task:read 不发起 /tasks/stats（先于 query 判定，杜绝 403 SEVERE） */
  const canRead = hasPermission('task:read')
  const statsQuery = useQuery({
    queryKey: ['tasks', 'stats', 'day'],
    queryFn: () => fetchTaskDomainStats('day'),
    staleTime: 30_000,
    enabled: canRead,
  })

  if (!canRead) return null

  if (statsQuery.isError) return null // 接口失败整行隐藏不报错

  const statusCounts = statsQuery.data?.status_counts ?? {}

  const values: Record<string, number> = {
    total: statsQuery.data?.total ?? 0,
    pending: statusCounts.pending ?? 0,
    queued: statusCounts.queued ?? 0,
    running: statusCounts.running ?? 0,
    completed: statusCounts.completed ?? 0,
    failed: statusCounts.failed ?? 0,
    deleted: statsQuery.data?.deleted_total ?? 0,
  }

  return (
    <div className='flex flex-wrap items-center gap-2'>
      {statsQuery.isLoading
        ? STATS_BADGES.map((badge) => (
            <Skeleton key={badge.key} className='h-7 w-28 rounded-md' />
          ))
        : STATS_BADGES.map((badge) => (
            <StatBadge
              key={badge.key}
              label={badge.label}
              value={values[badge.key] ?? 0}
              colorClass={badge.colorClass}
            />
          ))}
    </div>
  )
}
