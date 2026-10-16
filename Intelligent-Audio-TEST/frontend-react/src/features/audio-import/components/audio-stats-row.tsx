/**
 * 音频统计徽章行（§5.1 StatBadge ×4：总文件数/总大小/总时长/今日上传）。
 * 形态照 newAPI common-logs-stats（`border-border/60 bg-muted/25 inline-flex h-7 items-center
 * gap-2 rounded-md border px-2.5 text-xs shadow-xs` + 色条 `h-3.5 w-0.5 rounded-full`）。
 * 数据 GET /audios 响应内 data.stats（AudioListStats 实测）；加载中 Skeleton h-7。
 */
import { Skeleton } from '@/components/ui/skeleton'
import type { AudioListStats } from '@/domain/models/audio'

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

export function AudioStatsRow({ stats }: { stats: AudioListStats | undefined }) {
  if (!stats) {
    return (
      <div className='flex flex-wrap items-center gap-2' aria-label='统计加载中'>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className='h-7 w-36 rounded-md' />
        ))}
      </div>
    )
  }

  return (
    <div className='flex flex-wrap items-center gap-2'>
      <StatBadge label='总文件数' value={stats.totalFiles} dotClass='bg-neutral-400' />
      <StatBadge label='总大小' value={stats.totalSize} dotClass='bg-[var(--success)]' />
      <StatBadge label='总时长' value={stats.totalDuration} dotClass='bg-muted' />
      <StatBadge label='今日上传' value={stats.todayUploads} dotClass='bg-[var(--info)]' />
    </div>
  )
}
