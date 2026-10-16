/**
 * 双栏主体榜单（对位 newAPI model-leaderboard.tsx，14_benchmark排行.md §4.4）。
 * 行数均分左右（half = ceil(n/2)）；榜单行：名次 + 主体（SubjectLink）+ 徽章组 +
 * 右值列（主值 + DeltaText/score100）+ 实测轨行尾「查看报告」。
 */
import { Trophy } from 'lucide-react'

import type {
  BenchmarkDirection,
  RankingRow,
} from '@/domain/models/benchmark'
import { formatMetricValue, formatScore100 } from '@/features/rankings/lib/format'
import { SubjectLink, ReportLink } from '@/features/rankings/components/entity-links'
import { DeltaText } from '@/features/rankings/components/delta-text'
import { SourceBadgeGroup } from '@/features/rankings/components/source-badge'
import { cn } from '@/lib/utils'

export function SubjectLeaderboard(props: {
  rows: RankingRow[]
  direction: BenchmarkDirection
  unit: string
  className?: string
}) {
  const rows = props.rows
  if (rows.length === 0) return null

  const half = Math.ceil(rows.length / 2)
  const left = rows.slice(0, half)
  const right = rows.slice(half)

  return (
    <div
      className={cn('grid grid-cols-1 gap-x-8 md:grid-cols-2', props.className)}
    >
      <LeaderboardColumn
        rows={left}
        direction={props.direction}
        unit={props.unit}
      />
      <LeaderboardColumn
        rows={right}
        direction={props.direction}
        unit={props.unit}
      />
    </div>
  )
}

export function LeaderboardBlockHead(props: {
  children?: React.ReactNode
}) {
  return (
    <div className='flex items-start justify-between gap-2'>
      <div className='flex flex-col'>
        <div className='flex items-center gap-1.5'>
          <Trophy aria-hidden='true' className='text-amber-500 size-3.5' />
          <span className='text-sm font-semibold'>榜单</span>
        </div>
        <p className='text-muted-foreground/80 mt-0.5 text-xs'>
          按名次排列，实测轨取最新版本参与对比。
        </p>
      </div>
      {props.children}
    </div>
  )
}

function LeaderboardColumn(props: {
  rows: RankingRow[]
  direction: BenchmarkDirection
  unit: string
}) {
  return (
    <ul className='flex flex-col'>
      {props.rows.map((row) => (
        <li
          key={row.id}
          className='flex items-center gap-3 py-2.5'
        >
          <span className='text-muted-foreground/80 w-6 shrink-0 text-right font-mono text-xs tabular-nums'>
            {row.rank}.
          </span>
          <div className='min-w-0 flex-1'>
            <div className='font-mono text-sm font-medium'>
              <SubjectLink subjectName={row.subjectName} />
            </div>
            <SourceBadgeGroup
              row={row}
              className='text-muted-foreground/80 mt-0.5 text-xs italic'
            />
          </div>
          <div className='shrink-0 text-right'>
            <div className='font-mono text-sm font-semibold tabular-nums'>
              {formatMetricValue(row.metricValue, props.unit)}
            </div>
            <div className='text-[11px]'>
              {row.source === 'platform_test' && row.deltaExternal !== null ? (
                <DeltaText
                  value={row.deltaExternal}
                  unit={props.unit}
                  direction={props.direction}
                />
              ) : (
                <span className='text-muted-foreground tabular-nums'>
                  {formatScore100(row.score100)}
                </span>
              )}
            </div>
          </div>
          {row.source === 'platform_test' && row.reportId !== null ? (
            <ReportLink reportId={row.reportId} className='shrink-0' />
          ) : null}
        </li>
      ))}
    </ul>
  )
}
