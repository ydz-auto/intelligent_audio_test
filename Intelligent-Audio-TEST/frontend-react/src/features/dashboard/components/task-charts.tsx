/**
 * ④ 任务统计图表区（#task-charts 锚点；04_控制台.md §3.7，自 /tasks 移交三图卡）：
 * 任务完成趋势（柱状/面积 + 粒度页签）+ 任务类型分布（饼图）+ 任务状态分布（饼图）。
 * 图表机制照 newAPI ModelCharts 全套：ThemeManager 门控 + key 整图重建 + 色板分档。
 */
import { VChart } from '@visactor/react-vchart'
import type { ISpec } from '@visactor/vchart'
import { Activity, ChartNoAxesCombined, PieChart } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'

import { useTaskDomainStats } from '@/application/dashboard/use-task-domain-stats'
import type { TrendGranularity } from '@/application/dashboard/use-task-domain-stats'
import { IconBadge } from '@/components/ui/icon-badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  getTaskStatusLabel,
  getTaskTypeLabel,
} from '@/features/dashboard/constants'
import {
  buildDistributionPieSpec,
  buildTrendSpec,
} from '@/features/dashboard/lib/charts'
import {
  useChartTheme,
  useThemePresetKey,
  useThemeRadiusPx,
  VCHART_OPTION,
} from '@/features/dashboard/lib/vchart'
import {
  GRANULARITY_OPTIONS,
  TREND_VARIANT_OPTIONS,
} from '@/features/dashboard/constants'

type TrendVariant = (typeof TREND_VARIANT_OPTIONS)[number]['value']

function SegmentedButtonGroup<T extends string>(props: {
  options: ReadonlyArray<{ value: T; label: string }>
  value: T
  onChange: (value: T) => void
  ariaLabel: string
}) {
  return (
    <div
      className='bg-muted/60 inline-flex h-7 w-full overflow-x-auto rounded-lg border p-0.5 sm:h-8 sm:w-auto'
      role='group'
      aria-label={props.ariaLabel}
    >
      {props.options.map((option) => (
        <button
          key={option.value}
          type='button'
          onClick={() => props.onChange(option.value)}
          className={`shrink-0 rounded-md px-3 text-xs font-medium transition-colors ${
            props.value === option.value
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

function ChartCardShell(props: {
  tone: 'chart-1' | 'chart-2' | 'chart-4'
  icon: ReactNode
  title: string
  actions?: ReactNode
  loading: boolean
  children: ReactNode
}) {
  return (
    <div className='overflow-hidden rounded-lg border'>
      <div className='flex w-full flex-col gap-1.5 border-b px-3 py-2 sm:gap-3 sm:px-5 sm:py-3 lg:flex-row lg:items-center lg:justify-between'>
        <div className='flex items-center gap-2'>
          <IconBadge tone={props.tone} size='sm'>
            {props.icon}
          </IconBadge>
          <div className='text-sm font-semibold'>{props.title}</div>
        </div>
        {props.actions && (
          <div className='flex flex-wrap items-center gap-2'>{props.actions}</div>
        )}
      </div>
      {props.loading ? (
        <div className='p-3 sm:p-5'>
          <Skeleton className='h-[300px] w-full sm:h-96' />
        </div>
      ) : (
        props.children
      )}
    </div>
  )
}

function ChartCanvas(props: { spec: Record<string, unknown> }) {
  const { themeReady, themeKey } = useChartTheme()
  const presetKey = useThemePresetKey()

  if (!themeReady) return null

  return (
    <VChart
      // 主题/预设/数据变化整图重建（key 含 themeKey/presetKey —— newAPI 同款机制）
      key={[props.spec.type, themeKey, presetKey].join('-')}
      spec={
        {
          ...props.spec,
          theme: themeKey,
          background: 'transparent',
        } as ISpec
      }
      options={VCHART_OPTION}
    />
  )
}

export function TaskCharts() {
  const [trendVariant, setTrendVariant] = useState<TrendVariant>('bar')
  const [granularity, setGranularity] = useState<TrendGranularity>('day')
  const statsQuery = useTaskDomainStats(granularity)
  const chartRadius = useThemeRadiusPx()

  const trendSpec = useMemo(
    () =>
      buildTrendSpec(statsQuery.data?.trend ?? [], {
        variant: trendVariant,
        chartRadius,
      }),
    [statsQuery.data?.trend, trendVariant, chartRadius, statsQuery.isLoading]
  )

  const typePieSpec = useMemo(() => {
    const values = Object.entries(statsQuery.data?.type_counts ?? {}).map(
      ([type, value]) => ({ type: getTaskTypeLabel(type), value })
    )
    return buildDistributionPieSpec(values, { chartRadius })
  }, [statsQuery.data?.type_counts, chartRadius])

  const statusPieSpec = useMemo(() => {
    const values = Object.entries(statsQuery.data?.status_counts ?? {}).map(
      ([status, value]) => ({ type: getTaskStatusLabel(status), value })
    )
    return buildDistributionPieSpec(values, { chartRadius })
  }, [statsQuery.data?.status_counts, chartRadius])

  return (
    <section className='flex flex-col gap-4'>
      <div id='task-charts' className='scroll-mt-20'>
        <h3 className='text-sm font-semibold'>任务统计</h3>
        <p className='text-muted-foreground text-xs'>
          任务类型、完成趋势与状态分布的全域视图
        </p>
      </div>

      <ChartCardShell
        tone='chart-4'
        icon={<ChartNoAxesCombined />}
        title='任务完成趋势'
        loading={statsQuery.isLoading}
        actions={
          <>
            <SegmentedButtonGroup
              ariaLabel='图表形态'
              options={TREND_VARIANT_OPTIONS}
              value={trendVariant}
              onChange={setTrendVariant}
            />
            <SegmentedButtonGroup
              ariaLabel='统计粒度'
              options={GRANULARITY_OPTIONS}
              value={granularity}
              onChange={setGranularity}
            />
          </>
        }
      >
        <div className='h-[300px] p-1.5 sm:h-96 sm:p-2'>
          <ChartCanvas spec={trendSpec} />
        </div>
      </ChartCardShell>

      <ChartCardShell
        tone='chart-1'
        icon={<PieChart />}
        title='任务类型分布'
        loading={statsQuery.isLoading}
      >
        <div className='h-[300px] p-1.5 sm:h-96 sm:p-2'>
          <ChartCanvas spec={typePieSpec} />
        </div>
      </ChartCardShell>

      <ChartCardShell
        tone='chart-2'
        icon={<Activity />}
        title='任务状态分布'
        loading={statsQuery.isLoading}
      >
        <div className='h-[300px] p-1.5 sm:h-96 sm:p-2'>
          <ChartCanvas spec={statusPieSpec} />
        </div>
      </ChartCardShell>
    </section>
  )
}
