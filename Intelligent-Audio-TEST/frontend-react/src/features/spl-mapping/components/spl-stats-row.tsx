/**
 * 声压级映射统计徽章行（§4.1.2 StatBadge ×4，色条 neutral/success/warning/info）。
 * 形态照 newAPI common-logs-stats（`border-border/60 bg-muted/25 inline-flex h-7 items-center
 * gap-2 rounded-md border px-2.5 text-xs shadow-xs` + 色条 `h-3.5 w-0.5 rounded-full`）。
 * 设备页签=映射总数/已校准/未校准/关联设备数（GET /spl/stats SplStatsData）；
 * 数字页签=RMS-SPL 映射数/已校准/未校准/关联 API 数（前端 computed，§4.1.2）。
 * 加载中 Skeleton h-7；接口失败整行隐藏不报错。
 */
import { Skeleton } from '@/components/ui/skeleton'
import type { SplDomain } from '@/features/spl-mapping/types'

export interface SplStatsView {
  total: number
  calibrated: number
  uncalibrated: number
  associated: number
}

function StatBadge({
  label,
  value,
  dotClass,
}: {
  label: string
  value: string | number
  dotClass: string
}) {
  return (
    <span className='border-border/60 bg-muted/25 inline-flex h-7 items-center gap-2 rounded-md border px-2.5 text-xs shadow-xs'>
      <span aria-hidden='true' className={`h-3.5 w-0.5 rounded-full ${dotClass}`} />
      <span className='text-muted-foreground'>{label}</span>
      <span className='font-mono font-medium tabular-nums'>{value}</span>
    </span>
  )
}

export function SplStatsRow({
  domain,
  stats,
}: {
  domain: SplDomain
  stats: SplStatsView | undefined
}) {
  if (!stats) {
    return (
      <div className='flex flex-wrap items-center gap-2' aria-label='统计加载中'>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className='h-7 w-36 rounded-md' />
        ))}
      </div>
    )
  }

  const isDevice = domain === 'device'
  return (
    <div className='flex flex-wrap items-center gap-2'>
      <StatBadge
        label={isDevice ? '映射总数' : 'RMS-SPL 映射数'}
        value={stats.total}
        dotClass='bg-neutral-400'
      />
      <StatBadge label='已校准' value={stats.calibrated} dotClass='bg-[var(--success)]' />
      <StatBadge label='未校准' value={stats.uncalibrated} dotClass='bg-[var(--warning)]' />
      <StatBadge
        label={isDevice ? '关联设备数' : '关联 API 数'}
        value={stats.associated}
        dotClass='bg-[var(--info)]'
      />
    </div>
  )
}
