/**
 * 历史监控统计分析图表区（16_设备域.md §3.7：可用性/性能/错误/使用统计，VChart 2×2 网格）。
 * 深浅两套随主题：useChartTheme + useThemePresetKey（key 整图重建，照 dashboard task-charts 同款机制）。
 * 数据源：GET /test-devices/monitor-stats 真实聚合（契约 INT-1573，INT-2670 接线）——
 * 时间范围 / 实验室 / 设备沿用历史监控页签现有筛选条件；指标 null 是断点，不补 0；
 * 无采点 → 空态「暂无监控采点」（不用示例曲线充数，演示数据标注已移除）。
 */
import { VChart } from '@visactor/react-vchart'
import type { ISpec } from '@visactor/vchart'
import { Activity, AlertTriangle, BarChart3, LineChart, RefreshCw } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { IconBadge } from '@/components/ui/icon-badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useChartTheme,
  useThemePresetKey,
  VCHART_OPTION,
} from '@/features/dashboard/lib/vchart'
import {
  buildAvailabilitySpec,
  buildErrorSpec,
  buildPerformanceSpec,
  buildUsageSpec,
  hasMonitorStatsData,
  resolveStatsDateRange,
  type HistoryTimeRange,
} from '@/features/devices/lib/alarm-history-stats'
import { useDeviceMonitorStats } from '@/application/devices/use-devices'
import { ApiError } from '@/infrastructure/api/api-error'

function StatsChartCard({
  icon,
  title,
  spec,
}: {
  icon: ReactNode
  title: string
  spec: Record<string, unknown>
}) {
  const { themeReady, themeKey } = useChartTheme()
  const presetKey = useThemePresetKey()
  return (
    <div className='bg-card/50 overflow-hidden rounded-lg border'>
      <div className='flex items-center gap-1.5 border-b px-2.5 py-1.5 text-xs font-medium'>
        <IconBadge tone='neutral' size='xs'>{icon}</IconBadge>
        <span>{title}</span>
      </div>
      <div className='p-2'>
        {themeReady ? (
          <VChart
            key={[spec.type, themeKey, presetKey].join('-')}
            spec={{ ...spec, theme: themeKey, background: 'transparent' } as ISpec}
            options={VCHART_OPTION}
          />
        ) : (
          <div className='text-muted-foreground flex h-[168px] items-center justify-center text-xs'>
            图表加载中…
          </div>
        )}
      </div>
    </div>
  )
}

/** 图表区状态提示（缺条件 / 无设备 / 空采点） */
function StatsPlaceholder({ text, testId }: { text: string; testId: string }) {
  return (
    <div
      className='text-muted-foreground flex h-24 items-center justify-center rounded-lg border border-dashed px-3 text-xs'
      data-testid={testId}
    >
      {text}
    </div>
  )
}

export interface HistoryStatsChartsProps {
  /** 历史监控页签当前时间范围（今日/近7天/近30天/自定义） */
  timeRange: HistoryTimeRange
  customStart: string
  customEnd: string
  /** 页面设备筛选命中的测试设备 id（空数组 = 当前条件没有设备） */
  deviceIds: number[]
  /** 页面实验室筛选（null = 全部实验室） */
  labId: number | null
}

export function HistoryStatsCharts({
  timeRange,
  customStart,
  customEnd,
  deviceIds,
  labId,
}: HistoryStatsChartsProps) {
  const dateRange = useMemo(
    () => resolveStatsDateRange(timeRange, customStart, customEnd),
    [timeRange, customStart, customEnd]
  )
  // 页面列表排序会变（updatedAt/id），id 顺序稳定化后才不会让同一条件重复请求
  const sortedDeviceIds = useMemo(
    () => [...deviceIds].sort((a, b) => a - b),
    [deviceIds]
  )
  const hasDeviceScope = sortedDeviceIds.length > 0

  const statsQuery = useDeviceMonitorStats(
    {
      startDate: dateRange?.startDate ?? '',
      endDate: dateRange?.endDate ?? '',
      deviceIds: sortedDeviceIds,
      labId,
    },
    dateRange != null && hasDeviceScope
  )

  const stats = statsQuery.data
  const points = useMemo(() => stats?.points ?? [], [stats])
  const hasData = hasMonitorStatsData(points)
  const errorMessage =
    statsQuery.error instanceof ApiError
      ? statsQuery.error.userMessage
      : '监控统计加载失败，请稍后重试'

  let body: ReactNode
  if (dateRange == null) {
    body = <StatsPlaceholder testId='history-stats-placeholder' text='自定义时间范围请先选择开始与结束日期' />
  } else if (!hasDeviceScope) {
    body = <StatsPlaceholder testId='history-stats-placeholder' text='当前筛选没有测试设备，暂无监控统计' />
  } else if (statsQuery.isLoading) {
    body = (
      <div className='grid grid-cols-1 gap-2 sm:grid-cols-2' data-testid='history-stats-loading'>
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className='h-[210px] rounded-lg' />
        ))}
      </div>
    )
  } else if (statsQuery.isError) {
    body = (
      <div
        className='flex h-24 flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-3 text-xs'
        data-testid='history-stats-error'
      >
        <span className='text-muted-foreground'>{errorMessage}</span>
        <Button
          variant='outline'
          size='sm'
          className='h-7 gap-1 px-2 text-xs'
          onClick={() => void statsQuery.refetch()}
        >
          <RefreshCw aria-hidden='true' className='size-3' />
          重试
        </Button>
      </div>
    )
  } else if (!hasData) {
    body = (
      <StatsPlaceholder
        testId='history-stats-empty'
        text='暂无监控采点（性能统计依赖健康检查采点）'
      />
    )
  } else {
    body = (
      <div className='grid grid-cols-1 gap-2 sm:grid-cols-2' data-testid='history-stats-grid'>
        <StatsChartCard
          icon={<Activity aria-hidden='true' className='size-3.5' />}
          title='可用性统计'
          spec={buildAvailabilitySpec(points)}
        />
        <StatsChartCard
          icon={<LineChart aria-hidden='true' className='size-3.5' />}
          title='性能统计'
          spec={buildPerformanceSpec(points)}
        />
        <StatsChartCard
          icon={<AlertTriangle aria-hidden='true' className='size-3.5' />}
          title='错误统计'
          spec={buildErrorSpec(points)}
        />
        <StatsChartCard
          icon={<BarChart3 aria-hidden='true' className='size-3.5' />}
          title='使用统计'
          spec={buildUsageSpec(points)}
        />
      </div>
    )
  }

  return (
    <div className='flex flex-col gap-2' data-testid='history-stats-section'>
      <div className='flex flex-wrap items-center gap-1.5 text-xs'>
        <span className='font-medium'>统计分析</span>
        {stats && hasData && (
          <span className='text-muted-foreground' data-testid='history-stats-scope'>
            共 {stats.deviceCount} 台设备 · {stats.startDate} ~ {stats.endDate}
          </span>
        )}
      </div>
      {body}
    </div>
  )
}
