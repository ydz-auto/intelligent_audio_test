/**
 * 统计徽章行（features/logs；17_配置运维.md §4.3）。
 * StatBadge ×4：总日志/错误/警告/信息（色条 neutral/destructive/warning/info）。
 * 数据 GET /logs/stats（LogStatsData：total/debug/info/warning/error/critical，
 * critical 并入「错误日志」计数，debug 不入展示）；加载失败静默隐藏统计行。
 */
import { Skeleton } from '@/components/ui/skeleton'
import { StatBadge } from '@/features/tasks/components/ui/stat-badge'
import type { LogStatsData } from '@/domain/models/log'

export type LogsStatsRowProps = {
  stats: LogStatsData | undefined
  loading: boolean
  /** 统计与列表共享短 TTL 扫描缓存（现状 LOG_BUSINESS_SCAN_CACHE_TTL_SECONDS 3s 语义） */
  hasError?: boolean
}

export function LogsStatsRow({ stats, loading, hasError = false }: LogsStatsRowProps) {
  if (hasError || (!stats && !loading)) return null
  if (loading || !stats) {
    return (
      <div className='flex flex-wrap items-center gap-2'>
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className='h-7 w-24 rounded-md' />
        ))}
      </div>
    )
  }
  return (
    <div className='flex flex-wrap items-center gap-2' title='统计与列表共享短 TTL 扫描缓存，至多一个 TTL 窗口时延'>
      <StatBadge label='总日志条数' value={stats.total.toLocaleString()} colorClass='bg-neutral' />
      <StatBadge label='错误日志' value={(stats.error + stats.critical).toLocaleString()} colorClass='bg-destructive' />
      <StatBadge label='警告日志' value={stats.warning.toLocaleString()} colorClass='bg-warning' />
      <StatBadge label='信息日志' value={stats.info.toLocaleString()} colorClass='bg-info' />
    </div>
  )
}
