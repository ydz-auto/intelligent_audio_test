/**
 * /dashboard 工作台（04_控制台.md §3.3，INT-378 视觉稿四分区 mock 实现）：
 * ① 开始使用引导卡（双形态）② 平台概览卡（三 StatCard + 设备状态）
 * ③ 最近任务面板 ④ 任务统计图表区（#task-charts）。
 * 数据一律 mock 常量（红线④），query 桩见 infrastructure/api。
 */
import { useIsFetching, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { LoaderCircle, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useSetupGuide } from '@/application/dashboard/use-setup-guide'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import {
  FadeIn,
} from '@/features/dashboard/components/page-transition'
import { PlatformSummary } from '@/features/dashboard/components/platform-summary'
import { RecentTasksPanel } from '@/features/dashboard/components/recent-tasks-panel'
import { SetupGuide } from '@/features/dashboard/components/setup-guide'
import { TaskCharts } from '@/features/dashboard/components/task-charts'
import { useDashboardStats } from '@/application/dashboard/use-dashboard-stats'

/** 控制台面包屑（页面件轻量实现——基座 ui/ 无 breadcrumb 公共件，随页面落位） */
function DashboardBreadcrumb() {
  return (
    <nav aria-label='面包屑' className='text-sm'>
      <ol className='flex flex-wrap items-center gap-1.5'>
        <li>
          <Link
            to='/dashboard'
            className='text-muted-foreground hover:text-foreground transition-colors'
          >
            控制台
          </Link>
        </li>
        <li aria-hidden='true' className='text-muted-foreground/50'>
          /
        </li>
        <li aria-current='page' className='text-foreground font-medium'>
          工作台
        </li>
      </ol>
    </nav>
  )
}

export function DashboardPage() {
  const { hasPermission } = usePermissions()
  const queryClient = useQueryClient()
  const statsQuery = useDashboardStats()
  const setupGuide = useSetupGuide(statsQuery.data)
  // 「刷新统计」同时 invalidate 三个 queryKey（details/summary/domain-stats——§3.7）
  const refreshing = useIsFetching({
    predicate: (query) =>
      query.queryKey[0] === 'home' || query.queryKey[0] === 'tasks',
  })

  const handleRefresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['home'] })
    void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    toast.success('统计已刷新')
  }

  return (
    <SectionPageLayout>
      <SectionPageLayout.Breadcrumb>
        <DashboardBreadcrumb />
      </SectionPageLayout.Breadcrumb>
      <SectionPageLayout.Title>工作台</SectionPageLayout.Title>
      <SectionPageLayout.Actions>
        {setupGuide.setupComplete && (
          <Button
            variant='ghost'
            size='sm'
            aria-expanded={setupGuide.expanded}
            onClick={setupGuide.toggle}
          >
            开始使用
          </Button>
        )}
        {hasPermission('home:refresh') && (
          <Button
            variant='ghost'
            size='sm'
            disabled={refreshing > 0}
            onClick={handleRefresh}
          >
            {refreshing > 0 ? (
              <LoaderCircle
                data-icon='inline-start'
                className='size-3.5 animate-spin'
              />
            ) : (
              <RefreshCw data-icon='inline-start' />
            )}
            {refreshing > 0 ? '刷新中…' : '刷新统计'}
          </Button>
        )}
        {hasPermission('task:read') && (
          <Button variant='ghost' size='sm' render={<Link to='/tasks' />}>
            查看任务
          </Button>
        )}
      </SectionPageLayout.Actions>
      <SectionPageLayout.Content>
        <div className='flex flex-col gap-4'>
          <FadeIn>
            <SetupGuide
              steps={setupGuide.steps}
              completedCount={setupGuide.completedCount}
              expanded={setupGuide.expanded}
              details={statsQuery.data}
              onToggle={setupGuide.toggle}
            />
          </FadeIn>

          <FadeIn delay={0.05}>
            <PlatformSummary />
          </FadeIn>

          <FadeIn delay={0.1}>
            <RecentTasksPanel />
          </FadeIn>

          {hasPermission('task:read') && (
            <FadeIn delay={0.15}>
              <TaskCharts />
            </FadeIn>
          )}
        </div>
      </SectionPageLayout.Content>
    </SectionPageLayout>
  )
}
