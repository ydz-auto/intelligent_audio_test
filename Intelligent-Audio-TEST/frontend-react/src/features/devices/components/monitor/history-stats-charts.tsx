/**
 * 历史监控统计分析图表区（16_设备域.md §3.7：可用性/性能/错误/使用统计，VChart 2×2 网格）。
 * 深浅两套随主题：useChartTheme + useThemePresetKey（key 整图重建，照 dashboard task-charts 同款机制）。
 * P2-4：后端暂无历史监控指标端点，图表用示例采点渲染——图表区显式标注「演示数据」，不得静默充真；
 * 真实端点待 INT-1573 立项后接线（devices-mock MOCK_DEVICE_STATS 届时删除）。
 */
import { VChart } from '@visactor/react-vchart'
import type { ISpec } from '@visactor/vchart'
import { Activity, AlertTriangle, BarChart3, LineChart } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { IconBadge } from '@/components/ui/icon-badge'
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
} from '@/features/devices/lib/alarm-history-stats'
import { MOCK_DEVICE_STATS } from '@/infrastructure/mock/devices-mock'

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

export function HistoryStatsCharts() {
  const points = useMemo(() => MOCK_DEVICE_STATS, [])
  return (
    <div className='flex flex-col gap-2'>
      {/* P2-4：示例数据显式标注，避免静默展示假数据 */}
      <div
        className='flex flex-wrap items-center gap-1.5 text-xs'
        data-testid='history-stats-demo-notice'
      >
        <span className='font-medium'>统计分析</span>
        <Badge variant='outline' className='rounded-sm px-1.5 py-0 text-[11px] font-normal'>
          演示数据
        </Badge>
        <span className='text-muted-foreground'>
          后端暂无历史监控指标端点，图表为示例数据（待 INT-1573 接线）
        </span>
      </div>
      <div className='grid grid-cols-1 gap-2 sm:grid-cols-2'>
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
    </div>
  )
}
