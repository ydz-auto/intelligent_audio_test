/**
 * 指标组卡（对位 newAPI models-section.tsx，14_benchmark排行.md §4.4）：
 * 卡头（category 图标 + 指标名·场景 + 方向徽章 + 说明）+ 指标值横向对比条形图 +
 * border-t 榜单块（视图切换 列表/表格，视图选择存 localStorage 不入 URL）。
 */
import { AudioLines, Languages, MessagesSquare, Volume2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { RankingGroup } from '@/domain/models/benchmark'
import { formatComputedAtShort } from '@/features/rankings/lib/format'
import { MetricBarChart } from '@/features/rankings/components/metric-bar-chart'
import {
  LeaderboardBlockHead,
  SubjectLeaderboard,
} from '@/features/rankings/components/subject-leaderboard'
import { SubjectTable } from '@/features/rankings/components/subject-table'

const CATEGORY_ICONS = {
  asr: AudioLines,
  voice_llm: MessagesSquare,
  tts: Volume2,
  translation: Languages,
} as const

export type RankingViewMode = 'list' | 'table'

export function MetricGroupCard(props: {
  group: RankingGroup
  view: RankingViewMode
  onViewChange: (view: RankingViewMode) => void
}) {
  const { group, view, onViewChange } = props
  const Icon = CATEGORY_ICONS[group.category] ?? AudioLines
  const directionLabel =
    group.direction === 'lower_is_better' ? '越低越好' : '越高越好'
  const description = `平台实测与外部基线按${directionLabel}排名，共 ${group.total} 个主体参与。`

  return (
    <section className='bg-card ring-foreground/10 overflow-hidden rounded-xl border ring-1'>
      {/* 卡头 */}
      <div className='flex items-start justify-between gap-4 px-5 py-4'>
        <div className='flex flex-col gap-1.5'>
          <div className='flex flex-wrap items-center gap-2'>
            <Icon aria-hidden='true' className='text-primary size-4' />
            <h2 className='text-base font-semibold'>
              {group.metricName} · {group.scenarioKey}
            </h2>
            <Badge
              variant='outline'
              className={
                group.direction === 'lower_is_better'
                  ? 'border-transparent bg-muted text-muted-foreground'
                  : 'border-transparent bg-primary/10 text-primary'
              }
            >
              {directionLabel}
            </Badge>
          </div>
          <p className='text-muted-foreground mt-1 text-sm leading-5'>
            {description}
          </p>
        </div>
        <div className='shrink-0 text-right'>
          <div className='font-mono text-2xl font-semibold tabular-nums'>
            {group.total}
          </div>
          <div className='text-muted-foreground/80 text-[10px] tracking-widest uppercase'>
            个主体 · 计算于 {formatComputedAtShort(group.computedAt)}
          </div>
        </div>
      </div>

      {/* 图表区 */}
      <div className='px-5 pb-5'>
        <MetricBarChart group={group} />
      </div>

      {/* 榜单块 */}
      <div className='border-t'>
        <div className='px-5 pt-4 pb-2'>
          <LeaderboardBlockHead>
            <Tabs
              value={view}
              onValueChange={(value) =>
                onViewChange(value as RankingViewMode)
              }
            >
              <TabsList variant='line' className='h-8'>
                <TabsTrigger value='list'>列表</TabsTrigger>
                <TabsTrigger value='table'>表格</TabsTrigger>
              </TabsList>
            </Tabs>
          </LeaderboardBlockHead>
        </div>
        {view === 'list' ? (
          <SubjectLeaderboard
            rows={group.rows}
            direction={group.direction}
            unit={group.unit}
            className='px-5 pb-5'
          />
        ) : (
          <SubjectTable
            rows={group.rows}
            direction={group.direction}
            unit={group.unit}
            className='border-t'
          />
        )}
      </div>
    </section>
  )
}
