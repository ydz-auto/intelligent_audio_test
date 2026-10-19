/**
 * ④b 用例分组排行面板（04_控制台.md §3.7，PanelWrapper 形态）。
 * home:read 即渲染（summary 接口门槛实测 home:read）；
 * 名次/分组名/「{n} 条」+ 占比条（Progress h-1 轻量可视化，不新增图表）。
 */
import { Link } from '@tanstack/react-router'
import { FolderOpen } from 'lucide-react'

import { useDashboardSummary } from '@/application/dashboard/use-dashboard-summary'
import { usePermissions } from '@/application/hooks/use-permissions'
import { IconBadge } from '@/components/ui/icon-badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { PanelWrapper } from '@/features/dashboard/components/ui/panel-wrapper'

export function TopGroupsPanel() {
  const { hasPermission } = usePermissions()
  const summaryQuery = useDashboardSummary()

  const groups = summaryQuery.data?.topGroups ?? []
  const loading = summaryQuery.isLoading
  const empty = !loading && groups.length === 0
  const maxCount = Math.max(...groups.map((group) => group.caseCount), 0)
  const canOpenGroup = hasPermission('testcase:read')

  return (
    <PanelWrapper
      title={
        <span className='flex items-center gap-2'>
          <IconBadge tone='chart-2' size='sm'>
            <FolderOpen />
          </IconBadge>
          用例分组排行
        </span>
      }
      description='按用例数量排序的前 5 个分组'
      loading={loading}
      empty={empty}
      emptyMessage='在用例管理中创建分组后，这里会显示排行'
      height='h-72'
      contentClassName='p-0'
    >
      <ScrollArea className='h-72'>
        <div className='px-3 py-1 sm:px-5'>
          {groups.map((group, index) => (
            <div
              key={group.id}
              className='flex items-center gap-3 border-b border-transparent py-2.5 last:border-b-0'
            >
              <span className='text-muted-foreground/80 w-6 shrink-0 text-right font-mono text-xs tabular-nums'>
                {index + 1}
              </span>
              {canOpenGroup ? (
                <Link
                  to='/testcases'
                  // TODO(API 接线): ?group={id} 查询参数随 INT-356 用例页路由落定后接线
                  className='text-foreground min-w-0 flex-1 truncate text-sm font-medium transition-colors hover:underline'
                >
                  {group.name}
                </Link>
              ) : (
                <span className='text-foreground min-w-0 flex-1 truncate text-sm font-medium'>
                  {group.name}
                </span>
              )}
              <span className='text-muted-foreground shrink-0 text-xs tabular-nums'>
                {group.caseCount} 条
              </span>
              {/* 占比条：max=第一名计数（§3.7 轻量可视化） */}
              <div
                className='bg-muted h-1 w-16 shrink-0 overflow-hidden rounded-full sm:w-24'
                aria-hidden='true'
              >
                <div
                  className='bg-chart-2 h-full rounded-full'
                  style={{
                    width: `${
                      maxCount > 0 ? (group.caseCount / maxCount) * 100 : 0
                    }%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </PanelWrapper>
  )
}
