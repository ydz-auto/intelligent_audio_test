/**
 * /dashboard 工作台（04_控制台.md §3.3，INT-378 视觉稿四分区 mock 实现 + INT-486 补算法大卡）：
 * ① 算法卡片网格（INT-436：每算法一张大卡，点击切换全局算法；双入口——右上角切换器+页内大卡）
 * ② 开始使用引导卡（双形态）③ 平台概览卡（三 StatCard + 设备状态）
 * ④ 双面板行（最近任务 ｜ 用例分组排行）⑤ 任务统计图表区（#task-charts）。
 * 数据一律 mock 常量（红线④），query 桩见 infrastructure/api。
 */
import { useIsFetching, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { LoaderCircle, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { AlgorithmCardGrid } from '@/components/algorithm-card-grid'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useSetupGuide } from '@/application/dashboard/use-setup-guide'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { FadeIn } from '@/features/dashboard/components/page-transition'
import { PlatformSummary } from '@/features/dashboard/components/platform-summary'
import { RecentTasksPanel } from '@/features/dashboard/components/recent-tasks-panel'
import { SetupGuide } from '@/features/dashboard/components/setup-guide'
import { TaskCharts } from '@/features/dashboard/components/task-charts'
import { TopGroupsPanel } from '@/features/dashboard/components/top-groups-panel'
import { useDashboardStats } from '@/application/dashboard/use-dashboard-stats'

export function DashboardPage() {
  const { hasPermission } = usePermissions()
  const queryClient = useQueryClient()
  const statsQuery = useDashboardStats()
  const setupGuide = useSetupGuide(statsQuery.data)
  // 最近任务/图表区同门控（§3.7/§3.8：task:read 整面板隐藏）
  const taskRead = hasPermission('task:read')
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
        {taskRead && (
          <Button variant='ghost' size='sm' render={<Link to='/tasks' />}>
            查看任务
          </Button>
        )}
      </SectionPageLayout.Actions>
      <SectionPageLayout.Content>
        <div className='flex flex-col gap-4'>
          <FadeIn>
            {/* ① 算法卡片网格（INT-436/486：每算法一张大卡，点击切换全局算法；双入口） */}
            <AlgorithmCardGrid title='当前算法' />
          </FadeIn>

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

          {/* ④ 双面板行（§3.7）：最近任务 task:read 整面板隐藏；用例分组排行 home:read 即渲染 */}
          <div className='grid grid-cols-1 gap-4 xl:grid-cols-2'>
            {taskRead && (
              <FadeIn delay={0.1} className='h-full'>
                <RecentTasksPanel />
              </FadeIn>
            )}
            <FadeIn delay={taskRead ? 0.15 : 0.1} className='h-full'>
              <TopGroupsPanel />
            </FadeIn>
          </div>

          {taskRead && (
            <FadeIn delay={0.2}>
              <TaskCharts />
            </FadeIn>
          )}
        </div>
      </SectionPageLayout.Content>
    </SectionPageLayout>
  )
}
