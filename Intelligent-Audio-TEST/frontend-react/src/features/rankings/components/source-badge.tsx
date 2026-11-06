/**
 * 榜单行徽章组（来源/主体类型/设备类型/版本；14_benchmark排行.md §4.4/§7 文案）。
 * neutral 软底 = 主体/设备类型；来源徽章「平台实测」info 软底、「外部基线」secondary 软底。
 */
import { Badge } from '@/components/ui/badge'
import type { RankingRow } from '@/domain/models/benchmark'
import { cn } from '@/lib/utils'

const SUBJECT_TYPE_LABELS: Record<RankingRow['subjectType'], string> = {
  open_source: '开源',
  closed_source: '闭源',
  app: 'App',
}

const DEVICE_TYPE_LABELS: Record<NonNullable<RankingRow['deviceType']>, string> = {
  physical: '实体设备',
  http_api: 'HTTP API',
  websocket_api: 'WebSocket API',
}

export function SourceBadgeGroup(props: { row: RankingRow; className?: string }) {
  const { row } = props

  return (
    <span
      className={cn('flex flex-wrap items-center gap-1', props.className)}
      aria-label={`${SUBJECT_TYPE_LABELS[row.subjectType]}${row.deviceType ? `·${DEVICE_TYPE_LABELS[row.deviceType]}` : ''}·${row.source === 'platform_test' ? '平台实测' : '外部基线'}`}
    >
      <Badge
        variant='outline'
        className='border-transparent bg-muted text-muted-foreground'
      >
        {SUBJECT_TYPE_LABELS[row.subjectType]}
      </Badge>
      {row.deviceType ? (
        <Badge
          variant='outline'
          className='border-transparent bg-muted/60 text-muted-foreground'
        >
          {DEVICE_TYPE_LABELS[row.deviceType]}
        </Badge>
      ) : null}
      {row.source === 'platform_test' && row.publishedTaskVersion !== null ? (
        <Badge variant='outline' className='border-border text-muted-foreground'>
          v{row.publishedTaskVersion}
        </Badge>
      ) : null}
      <Badge
        variant='secondary'
        className={cn(
          row.source === 'platform_test' && 'bg-info/10 text-info border-transparent'
        )}
      >
        {row.source === 'platform_test' ? '平台实测' : '外部基线'}
      </Badge>
    </span>
  )
}
