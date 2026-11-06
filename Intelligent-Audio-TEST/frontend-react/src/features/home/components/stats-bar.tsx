import { Link } from '@tanstack/react-router'

import { RollingNumber, RollingNumberGroup } from '@/components/rolling-number'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useHomeStats } from '@/application/hooks/use-home-stats'
import { usePermissions } from '@/application/hooks/use-permissions'
import { cn } from '@/lib/utils'
import { STATS_BAR } from '../constants'

/** 规模条单项（to 限定为六项对应管理页路由，类型上防误填） */
type StatsBarItem = {
  key: string
  label: string
  value: number
  sub: string
  to:
    | '/testcases'
    | '/tasks'
    | '/Evaluation'
    | '/audio-import'
    | '/devices'
    | '/APITest'
  permission: string
  /** Alert 态（当前仅 API 在线率低于阈值） */
  alert?: boolean
}

/**
 * 平台规模条（03_首页.md §3.2 尾部，对位 Vue QuickStats）：
 * 六项指标数字滚动；整项可点击跳对应管理页（无对应权限时仍展示但不渲染链接）；
 * 任务/音频副行细分；API 在线率低于阈值标 Alert 色 + 故障告警角标；
 * 未登录/无 home:read 整条替换为登录引导；登录态加载中显骨架（真实接口 pending）。
 */
export function StatsBar() {
  const { data: stats, isLoading, isError } = useHomeStats()
  const { user, hasPermission } = usePermissions()
  const canRead = hasPermission('home:read')

  if (!user || !canRead) {
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

  if (isLoading) {
    return <StatsBarSkeleton />
  }

  // 接口失败整条隐藏不报错（03_首页.md §3.2：统计缺位不阻断品牌叙事）
  if (isError || !stats) {
    return null
  }

  const apiOnlineRateAlert =
    stats.apis.total > 0 &&
    stats.apis.online / stats.apis.total <
      STATS_BAR.apiOnlineRateAlertThreshold

  const items: StatsBarItem[] = [
    {
      key: 'testCases',
      label: '测试用例',
      value: stats.testCases.total,
      sub: `${stats.testCases.groups} 个分组`,
      to: '/testcases',
      permission: 'testcase:read',
    },
    {
      key: 'tasks',
      label: '测试任务',
      value: stats.tasks.total,
      sub: `${stats.tasks.completed} 已完成 / ${stats.tasks.running} 进行中 / ${stats.tasks.failed} 失败`,
      to: '/tasks',
      permission: 'task:read',
    },
    {
      key: 'dimensions',
      label: '评估维度',
      value: stats.dimensions.total,
      sub: `${stats.dimensions.endpoints} 个端点`,
      to: '/Evaluation',
      permission: 'evaluation:read',
    },
    {
      key: 'audioFiles',
      label: '音频文件',
      value: stats.audioFiles.total,
      sub: `${stats.audioFiles.dry} 干音 / ${stats.audioFiles.noise} 噪声 / ${stats.audioFiles.prompt} 提示音`,
      to: '/audio-import',
      permission: 'audio:read',
    },
    {
      key: 'devices',
      label: '在线设备',
      value: stats.devices.online,
      sub: `${stats.devices.offline} 台离线`,
      to: '/devices',
      permission: 'device:read',
    },
    {
      key: 'apis',
      label: 'API 服务',
      value: stats.apis.total,
      sub: `${stats.apis.online} 个在线`,
      to: '/APITest',
      permission: 'task:execute',
      alert: apiOnlineRateAlert,
    },
  ]

  return (
    <RollingNumberGroup>
      <div className='border-border/70 flex flex-wrap items-center justify-between gap-x-8 gap-y-4 border-t pt-6'>
        <span className='text-muted-foreground text-xs'>
          {STATS_BAR.label}
        </span>
        <dl className='flex flex-wrap items-center gap-x-2 gap-y-2'>
          {items.map((item) => {
            const canLink = hasPermission(item.permission)
            return (
              <div
                key={item.key}
                className={cn(
                  'relative rounded-xl px-3 py-1.5',
                  // 整项可点击：hover 上移 4px + 阴影（03_首页.md §3.2）；无权限项为静态展示
                  canLink &&
                    'hover:shadow-md transition-[transform,box-shadow] duration-200 hover:-translate-y-1'
                )}
              >
                {canLink ? (
                  // 拉伸覆盖整项，保证 dd/dt 语义不变的同时整块可点
                  <Link
                    to={item.to}
                    aria-label={item.label}
                    className='focus-visible:ring-ring absolute inset-0 rounded-xl focus-visible:ring-2 focus-visible:outline-none'
                  />
                ) : null}
                <dd
                  className={cn(
                    'text-lg font-semibold tabular-nums',
                    item.alert && 'text-destructive'
                  )}
                >
                  <RollingNumber value={item.value} batch='home-stats' />
                  {item.alert ? (
                    <Badge variant='destructive' className='ml-1.5 align-middle'>
                      {STATS_BAR.apiAlertBadge}
                    </Badge>
                  ) : null}
                </dd>
                <dt
                  className={cn(
                    'text-muted-foreground text-xs',
                    item.alert && 'text-destructive'
                  )}
                >
                  {item.label} · {item.sub}
                </dt>
              </div>
            )
          })}
        </dl>
      </div>
    </RollingNumberGroup>
  )
}

/** 加载骨架位（真实接口 pending 态消费） */
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
