/**
 * ② 平台概览卡（04_控制台.md §3.6，照 newAPI SummaryCards 双区版式）：
 * 左区三枚 StatCard（任务总数/完成率/最近任务，mock + sparkline）+ 右区设备状态面板。
 * 点击口径（负责人 2026-10-17 拍板）：任务总数 → 任务列表 /tasks；
 * 完成率、最近任务 → 最近一个任务详情 /tasks/:id（task:read 缺失时降级纯展示）。
 * sparkline mock 序列经 application hook 透出（useTaskDomainStats/useTaskQualityStats），
 * feature 层不直触 infrastructure。
 */
import { Link } from '@tanstack/react-router'
import { ChartLine, ClipboardList, Clock, Music, Server } from 'lucide-react'
import type { ReactNode } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useDashboardStats } from '@/application/dashboard/use-dashboard-stats'
import { useTaskDomainStats } from '@/application/dashboard/use-task-domain-stats'
import { useTaskQualityStats } from '@/application/dashboard/use-task-quality-stats'
import { useDashboardSummary } from '@/application/dashboard/use-dashboard-summary'
import { useLatestTaskDetail } from '@/application/dashboard/use-latest-task-detail'
import {
  CardStaggerContainer as StaggerContainer,
  CardStaggerItem as StaggerItem,
} from '@/features/dashboard/components/page-transition'
import {
  formatDateTime,
  getTaskStatusLabel,
} from '@/features/dashboard/constants'
import { StatCard } from '@/features/dashboard/components/ui/stat-card'
import { cn } from '@/lib/utils'

type HealthLevel = 'healthy' | 'caution' | 'critical' | 'none'

function getDeviceHealthLevel(
  online: number,
  offline: number,
  total: number
): HealthLevel {
  if (total === 0) return 'none'
  if (offline === 0) return 'healthy'
  if (online === 0) return 'critical'
  return 'caution'
}

const HEALTH_CONFIG: Record<HealthLevel, { dotClass: string; label: string }> =
  {
    healthy: { dotClass: 'bg-success', label: '正常' },
    caution: { dotClass: 'bg-warning', label: '' }, // label 由「{n} 台离线」动态填
    critical: { dotClass: 'bg-destructive', label: '全部离线' },
    none: { dotClass: 'bg-muted-foreground', label: '暂无设备' },
  }

/** 概览卡点击目标：任务列表 / 最近任务详情（task:read 缺失不渲染 Link，降级纯展示） */
type OverviewTileLink =
  | { kind: 'tasks-list' }
  | { kind: 'task-detail'; taskId: number }

const TILE_BASE_CLASS =
  'bg-background/60 rounded-lg border px-2 py-1.5 sm:rounded-xl sm:p-3'

function OverviewTile(props: { link?: OverviewTileLink; children: ReactNode }) {
  if (!props.link) {
    return <div className={TILE_BASE_CLASS}>{props.children}</div>
  }
  const clickableClass = cn(
    TILE_BASE_CLASS,
    'block h-full transition-colors hover:bg-muted/40'
  )
  if (props.link.kind === 'tasks-list') {
    return (
      <Link to='/tasks' className={clickableClass}>
        {props.children}
      </Link>
    )
  }
  return (
    <Link
      to='/tasks/$tab'
      params={{ tab: String(props.link.taskId) }}
      className={clickableClass}
    >
      {props.children}
    </Link>
  )
}

export function PlatformSummary() {
  const { hasPermission } = usePermissions()
  const statsQuery = useDashboardStats()
  const qualityQuery = useTaskQualityStats()
  // 任务卡 sparkline：trend 12 桶（无 task:read 时接口 403 降级——mock 阶段恒有数据）
  const domainStatsQuery = useTaskDomainStats('day')
  const summaryQuery = useDashboardSummary()
  const latestTaskId = summaryQuery.data?.recent_tasks[0]?.id
  const latestTaskQuery = useLatestTaskDetail(latestTaskId)

  const details = statsQuery.data
  const latestTask = latestTaskQuery.data
  const canOpenTask = hasPermission('task:read')
  const loading =
    statsQuery.isLoading ||
    qualityQuery.isLoading ||
    domainStatsQuery.isLoading ||
    summaryQuery.isLoading ||
    latestTaskQuery.isLoading

  const devices = details?.devices
  const healthLevel = getDeviceHealthLevel(
    devices?.online ?? 0,
    devices?.offline ?? 0,
    devices?.total ?? 0
  )
  const healthLabel =
    healthLevel === 'caution'
      ? `${devices?.offline ?? 0} 台离线`
      : HEALTH_CONFIG[healthLevel].label

  // 完成率 = 已完成任务 / 任务总数（task.py TaskStatsData 同源口径）
  const completionRate =
    details && details.tasks.total > 0
      ? `${((details.tasks.completed / details.tasks.total) * 100).toFixed(1)}%`
      : '--'

  return (
    <div className='bg-card overflow-hidden rounded-2xl border shadow-xs'>
      <div className='grid xl:grid-cols-[minmax(0,1fr)_19rem]'>
        <div className='flex flex-col gap-2.5 p-3 sm:gap-3 sm:p-5'>
          <div className='flex flex-col gap-1'>
            <h3 className='text-sm font-semibold sm:text-base'>平台概览</h3>
            <p className='text-muted-foreground text-xs sm:text-sm'>
              监控任务、资产与设备状态
            </p>
          </div>
          <StaggerContainer className='grid grid-cols-3 gap-1.5 sm:gap-3'>
            <StaggerItem>
              <OverviewTile link={canOpenTask ? { kind: 'tasks-list' } : undefined}>
                <StatCard
                  title='任务总数'
                  value={details?.tasks.total ?? 0}
                  description={`${details?.tasks.completed ?? 0} 个已完成`}
                  icon={ClipboardList}
                  tone='accent-1'
                  sparkline={domainStatsQuery.taskTrendSparkline}
                  sparklineVariant='line'
                  loading={loading}
                  error={statsQuery.isError}
                  compactMobile
                />
              </OverviewTile>
            </StaggerItem>
            <StaggerItem>
              <OverviewTile
                link={
                  canOpenTask && latestTaskId != null
                    ? { kind: 'task-detail', taskId: latestTaskId }
                    : undefined
                }
              >
                <StatCard
                  title='完成率'
                  value={completionRate}
                  description={
                    details
                      ? `${details.tasks.completed}/${details.tasks.total} 执行完成`
                      : '统计暂不可用'
                  }
                  icon={ChartLine}
                  tone='accent-2'
                  sparkline={qualityQuery.passRateTrend}
                  sparklineVariant='line'
                  loading={loading}
                  error={statsQuery.isError || qualityQuery.isError}
                  compactMobile
                />
              </OverviewTile>
            </StaggerItem>
            <StaggerItem>
              <OverviewTile
                link={
                  canOpenTask && latestTaskId != null
                    ? { kind: 'task-detail', taskId: latestTaskId }
                    : undefined
                }
              >
                <StatCard
                  title='最近任务'
                  value={
                    latestTask
                      ? getTaskStatusLabel(
                          latestTask.execution_status ?? latestTask.status
                        )
                      : '--'
                  }
                  description={latestTask?.name ?? '统计暂不可用'}
                  icon={Clock}
                  tone='accent-3'
                  details={
                    latestTask
                      ? [
                          {
                            label: '完成时间',
                            value: latestTask.completed_at
                              ? formatDateTime(latestTask.completed_at)
                              : '进行中',
                          },
                          {
                            label: '预计完成时间',
                            value: formatDateTime(
                              latestTask.expected_complete_time
                            ),
                          },
                          {
                            label: '测试所用时间',
                            value: latestTask.used_time ?? '—',
                          },
                        ]
                      : undefined
                  }
                  loading={loading}
                  error={summaryQuery.isError || latestTaskQuery.isError}
                  compactMobile
                />
              </OverviewTile>
            </StaggerItem>
          </StaggerContainer>
        </div>

        <div className='bg-muted/30 flex flex-col justify-between gap-3 border-t p-3 sm:gap-4 sm:p-5 xl:border-t-0 xl:border-l'>
          <div className='flex flex-col gap-2 sm:gap-3'>
            <div className='flex items-center justify-between'>
              <span className='text-muted-foreground text-xs font-medium'>
                设备状态
              </span>
              <span className='flex items-center gap-1.5'>
                <span
                  className={cn(
                    'size-1.5 rounded-full',
                    HEALTH_CONFIG[healthLevel].dotClass
                  )}
                  aria-hidden='true'
                />
                <span className='text-muted-foreground text-[11px] font-medium'>
                  {healthLabel}
                </span>
              </span>
            </div>

            <div className='font-mono text-xl font-semibold tracking-tight sm:text-2xl'>
              {details ? devices?.online : '--'}
              <span className='text-muted-foreground ml-1.5 text-xs font-normal'>
                台在线
              </span>
            </div>

            <div className='grid grid-cols-2 gap-2'>
              {hasPermission('audio:read') ? (
                <Link
                  to='/audio-import'
                  className='bg-card rounded-lg border px-2.5 py-2 transition-colors hover:bg-muted/40'
                >
                  <div className='text-muted-foreground flex items-center gap-1 text-[11px] leading-none font-medium'>
                    <Music className='size-3 shrink-0' aria-hidden='true' />
                    <span className='truncate'>音频文件</span>
                  </div>
                  <div className='text-foreground mt-1.5 truncate text-xs font-semibold tabular-nums'>
                    {details ? details.audio_files.total : '--'}
                  </div>
                  <div className='text-muted-foreground/60 mt-0.5 truncate text-[11px]'>
                    干音 {details ? details.audio_files.dry : '--'} 个
                  </div>
                </Link>
              ) : (
                <div className='bg-card rounded-lg border px-2.5 py-2'>
                  <div className='text-muted-foreground flex items-center gap-1 text-[11px] leading-none font-medium'>
                    <Music className='size-3 shrink-0' aria-hidden='true' />
                    <span className='truncate'>音频文件</span>
                  </div>
                  <div className='text-foreground mt-1.5 truncate text-xs font-semibold tabular-nums'>
                    {details ? details.audio_files.total : '--'}
                  </div>
                  <div className='text-muted-foreground/60 mt-0.5 truncate text-[11px]'>
                    干音 {details ? details.audio_files.dry : '--'} 个
                  </div>
                </div>
              )}
              {/* TODO(API 接线): API 服务卡跳转 /system-settings/testing/apis，路由随 INT-347 落定后接线 */}
              <div className='bg-card rounded-lg border px-2.5 py-2'>
                <div className='text-muted-foreground flex items-center gap-1 text-[11px] leading-none font-medium'>
                  <Server className='size-3 shrink-0' aria-hidden='true' />
                  <span className='truncate'>API 服务</span>
                </div>
                <div className='text-foreground mt-1.5 truncate text-xs font-semibold tabular-nums'>
                  {details ? details.apis.total : '--'}
                </div>
                <div className='text-muted-foreground/60 mt-0.5 truncate text-[11px]'>
                  在线 {details ? details.apis.online : '--'} 个
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
