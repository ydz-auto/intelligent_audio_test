/**
 * 统计徽章行（interfaces 层；17_配置运维.md §4.3 StatBadge ×4）。
 * 数据 GET /logs/stats（LogStatsData），前端收敛展示四枚：
 * 总日志条数（total, neutral）/ 错误日志（error + critical 并入, destructive）/
 * 警告日志（warning, warning）/ 信息日志（info, info）；debug 不入展示。
 * 加载失败静默隐藏（§4.3 现状行为）。
 */
import type { LogStats } from '@/domain/models/log'
import { StatBadge } from '@/features/tasks/components/ui/stat-badge'

export function LogsStatsRow({
  stats,
  isLoading,
}: {
  stats?: LogStats
  isLoading: boolean
}) {
  if (isLoading || !stats) return null

  return (
    <div className='flex flex-wrap items-center gap-2'>
      <StatBadge label='总日志条数' value={stats.total.toLocaleString()} colorClass='bg-neutral' />
      <StatBadge
        label='错误日志'
        value={(stats.error + stats.critical).toLocaleString()}
        colorClass='bg-destructive'
      />
      <StatBadge
        label='警告日志'
        value={stats.warning.toLocaleString()}
        colorClass='bg-warning'
      />
      <StatBadge
        label='信息日志'
        value={stats.info.toLocaleString()}
        colorClass='bg-info'
      />
    </div>
  )
}
