/**
 * ② 平台概览卡（04_控制台.md §3.5，照 newAPI SummaryCards 双区版式）：
 * 左区三枚 StatCard（任务总数/通过率/平均得分，mock + sparkline）+ 右区设备状态面板。
 */
import { Link } from '@tanstack/react-router'
import { ChartLine, ClipboardList, Music, Server, Star } from 'lucide-react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useDashboardStats } from '@/application/dashboard/use-dashboard-stats'
import {
  useTaskDomainStats,
} from '@/application/dashboard/use-task-domain-stats'
import { useTaskQualityStats } from '@/application/dashboard/use-task-quality-stats'
import {
  CardStaggerContainer as StaggerContainer,
  CardStaggerItem as StaggerItem,
} from '@/features/dashboard/components/page-transition'
import { StatCard } from '@/features/dashboard/components/ui/stat-card'
import {
  MOCK_AVG_SCORE_TREND,
  MOCK_PASS_RATE_TREND,
} from '@/infrastructure/mock/dashboard-mock'
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

export function PlatformSummary() {
  const { hasPermission } = usePermissions()
  const statsQuery = useDashboardStats()
  const qualityQuery = useTaskQualityStats()
  // 任务卡 sparkline：trend 12 桶（无 task:read 时接口 403 降级——mock 阶段恒有数据）
  const domainStatsQuery = useTaskDomainStats('day')

  const details = statsQuery.data
  const quality = qualityQuery.data
  const loading =
    statsQuery.isLoading || qualityQuery.isLoading || domainStatsQuery.isLoading

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
            <StaggerItem className='bg-background/60 rounded-lg border px-2 py-1.5 sm:rounded-xl sm:p-3'>
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
            </StaggerItem>
            <StaggerItem className='bg-background/60 rounded-lg border px-2 py-1.5 sm:rounded-xl sm:p-3'>
              <StatCard
                title='通过率'
                value={
                  quality
                    ? `${quality.pass_rate.toFixed(1)}%`
                    : '--'
                }
                description={
                  details
                    ? `${details.tasks.completed}/${details.tasks.total} 执行完成`
                    : '统计暂不可用'
                }
                icon={ChartLine}
                tone='accent-2'
                sparkline={
                  domainStatsQuery.isLoading ? undefined : MOCK_PASS_RATE_TREND
                }
                sparklineVariant='line'
                loading={loading}
                error={qualityQuery.isError}
                compactMobile
              />
            </StaggerItem>
            <StaggerItem className='bg-background/60 rounded-lg border px-2 py-1.5 sm:rounded-xl sm:p-3'>
              <StatCard
                title='平均得分'
                value={quality ? quality.average_score.toFixed(1) : '--'}
                description={
                  quality ? `${quality.scored_reports} 份报告参与评分` : '统计暂不可用'
                }
                icon={Star}
                tone='accent-3'
                sparkline={
                  domainStatsQuery.isLoading ? undefined : MOCK_AVG_SCORE_TREND
                }
                sparklineVariant='line'
                loading={loading}
                error={qualityQuery.isError}
                compactMobile
              />
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
