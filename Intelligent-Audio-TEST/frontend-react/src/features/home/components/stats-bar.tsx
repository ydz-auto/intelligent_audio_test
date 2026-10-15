import { Link } from '@tanstack/react-router'

import { RollingNumber, RollingNumberGroup } from '@/components/rolling-number'
import { Skeleton } from '@/components/ui/skeleton'
import { useHomeStats } from '@/application/hooks/use-home-stats'
import { usePermissions } from '@/application/hooks/use-permissions'
import { STATS_BAR } from '../constants'

/**
 * 平台规模条（03_首页.md §3.2 尾部，对位 Vue QuickStats）：
 * 六项指标数字滚动；未登录（home:read 403 口径）整条替换为登录引导——
 * 不渲染骨架假数。mock 态数据恒有，登录态即渲染。
 */
export function StatsBar() {
  const { stats } = useHomeStats()
  const { user, hasPermission } = usePermissions()
  const canRead = hasPermission('home:read')

  if (!user || !canRead || !stats) {
    return (
      <div className='border-border/70 flex flex-wrap items-center gap-x-6 gap-y-3 border-t pt-6'>
        <span className='text-muted-foreground text-xs'>
          {STATS_BAR.anonymousText}
        </span>
        <Link
          to='/login'
          className='text-primary text-xs font-medium underline underline-offset-4'
        >
          {STATS_BAR.anonymousAction}
        </Link>
      </div>
    )
  }

  const items = [
    {
      label: '测试用例',
      value: stats.test_cases.total,
      sub: `${stats.test_cases.groups} 个分组`,
    },
    {
      label: '测试任务',
      value: stats.tasks.total,
      sub: `${stats.tasks.completed} 已完成`,
    },
    {
      label: '评估维度',
      value: stats.dimensions.total,
      sub: `${stats.dimensions.endpoints} 个端点`,
    },
    {
      label: '音频文件',
      value: stats.audio_files.total,
      sub: `${stats.audio_files.dry} 个干音`,
    },
    {
      label: '在线设备',
      value: stats.devices.online,
      sub: `${stats.devices.offline} 台离线`,
    },
    {
      label: 'API 服务',
      value: stats.apis.total,
      sub: `${stats.apis.online} 个在线`,
    },
  ]

  return (
    <RollingNumberGroup>
      <div className='border-border/70 flex flex-wrap items-center justify-between gap-x-8 gap-y-4 border-t pt-6'>
        <span className='text-muted-foreground text-xs'>
          {STATS_BAR.label}
        </span>
        <dl className='flex flex-wrap items-center gap-x-8 gap-y-4'>
          {items.map((item) => (
            <div key={item.label}>
              <dd className='text-lg font-semibold tabular-nums'>
                <RollingNumber value={item.value} batch='home-stats' />
              </dd>
              <dt className='text-muted-foreground text-xs'>
                {item.label} · {item.sub}
              </dt>
            </div>
          ))}
        </dl>
      </div>
    </RollingNumberGroup>
  )
}

/** 加载骨架位（真实接线后 useQuery pending 态消费） */
export function StatsBarSkeleton() {
  return (
    <div className='border-border/70 flex flex-wrap items-center gap-x-8 gap-y-4 border-t pt-6'>
      <Skeleton className='h-4 w-12' />
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className='h-6 w-12' />
      ))}
    </div>
  )
}
