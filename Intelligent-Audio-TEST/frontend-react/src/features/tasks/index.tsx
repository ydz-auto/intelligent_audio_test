/**
 * 任务域页（09_任务域.md §3，SectionPageLayout fixedContent + 四页签 + DataTablePage 骨架）。
 * 装配：Title「任务管理」/ Actions（创建新任务·导入数据·查看统计图表）/
 * Content（Tabs → 筛选工具栏 → 页签表格 → 批量浮条）/ Footer（分页 Portal）。
 * 页签路径式 /tasks/$tab（白名单校验在路由层），本组件消费 tab 参数分发。
 */
import { Link, useNavigate } from '@tanstack/react-router'
import { ChartLine, FileDown, Plus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTasksList, type TaskListFilters } from '@/application/tasks/use-tasks-list'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import type { CherryPickTask, PublishedTaskItem, TaskListItem } from '@/domain/models/task'
import {
  TASKS_TABS,
  type TasksTabKey,
} from '@/features/tasks/constants'
import { TasksFilterToolbar } from '@/features/tasks/components/tasks-filter-toolbar'
import { DailyTaskTable } from '@/features/tasks/components/daily-task-table'
import { PublishedTaskTable } from '@/features/tasks/components/published-task-table'
import { MergedTaskTable } from '@/features/tasks/components/merged-task-table'
import { CherryPickTab } from '@/features/tasks/components/cherry-pick-tab'
import { TasksPagination } from '@/features/tasks/components/tasks-pagination'
import { QuickViewDialog } from '@/features/tasks/components/quick-view-dialog'
import { PublishTaskDialog } from '@/features/tasks/components/publish-task-dialog'
import { TaskTypeDialog } from '@/features/tasks/components/task-type-dialog'

const EMPTY_FILTERS: TaskListFilters = {}

export function TasksPage({ tab }: { tab: TasksTabKey }) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)

  const [filters, setFilters] = useState<TaskListFilters>(EMPTY_FILTERS)
  const [quickViewTask, setQuickViewTask] = useState<TaskListItem | null>(null)
  const [typeDialogOpen, setTypeDialogOpen] = useState(false)
  const [publishTask, setPublishTask] = useState<TaskListItem | null>(null)

  // 页签切换重置筛选（URL 态回归：接线后 page/search/… 进 search，随 useTableUrlState）
  useEffect(() => {
    setFilters(EMPTY_FILTERS)
  }, [tab])

  const algorithmType = algorithmId ? algorithmId : null
  const listQuery = useTasksList(tab, {
    ...filters,
    algorithmType: filters.algorithmType ?? algorithmType,
  })

  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0

  const isFiltered = useMemo(
    () =>
      Object.entries(filters).some(([key, value]) => {
        if (key === 'algorithmType') return false
        if (Array.isArray(value)) return value.length > 0
        return value != null && value !== '' && value !== false && value !== 'all'
      }),
    [filters]
  )

  const handleQuickView = (task: TaskListItem) => {
    setQuickViewTask(task)
  }

  return (
    <SectionPageLayout fixedContent>
      <SectionPageLayout.Breadcrumb>
        <nav aria-label='面包屑' className='text-sm'>
          <ol className='flex flex-wrap items-center gap-1.5'>
            <li>
              <Link to='/dashboard' className='text-muted-foreground hover:text-foreground transition-colors'>
                工作台
              </Link>
            </li>
            <li aria-hidden='true' className='text-muted-foreground/50'>/</li>
            <li aria-current='page' className='text-foreground font-medium'>
              任务管理
            </li>
          </ol>
        </nav>
      </SectionPageLayout.Breadcrumb>

      <SectionPageLayout.Title>任务管理</SectionPageLayout.Title>

      <SectionPageLayout.Actions>
        {hasPermission('task:create') && (
          <Button size='sm' className='h-7 gap-1.5' onClick={() => setTypeDialogOpen(true)}>
            <Plus aria-hidden='true' className='size-3.5' />
            创建新任务
          </Button>
        )}
        {hasPermission('task:import') && (
          <Button
            size='sm'
            variant='outline'
            className='h-7 gap-1.5'
            onClick={() => {
              // §5.12 导入弹窗（视觉稿占位：toast 演示，完整弹窗随后续卡）
              void navigate({ to: '/tasks/$tab', params: { tab: 'daily' } })
            }}
          >
            <FileDown aria-hidden='true' className='size-3.5' />
            导入数据
          </Button>
        )}
        {hasPermission('task:read') && (
          <Button
            size='sm'
            variant='link'
            className='h-7 gap-1.5'
            render={<Link to='/dashboard' hash='task-charts' />}
          >
            <ChartLine aria-hidden='true' className='size-3.5' />
            查看任务统计图表
          </Button>
        )}
      </SectionPageLayout.Actions>

      <SectionPageLayout.Content>
        <div className='flex h-full min-h-0 flex-col gap-3'>
          <Tabs
            value={tab}
            onValueChange={(value) => void navigate({ to: '/tasks/$tab', params: { tab: value } })}
          >
            <TabsList variant='default' className='max-w-full flex-wrap justify-start'>
              {TASKS_TABS.filter((t) => {
                if (t.key === 'published') return hasPermission('published_task:read')
                return hasPermission('task:read')
              }).map((t) => (
                <TabsTrigger key={t.key} value={t.key} className='px-3'>
                  {t.label}
                  {t.key !== 'daily' && <span className='text-muted-foreground font-mono text-[11px] tabular-nums'>{total > 0 ? total : 0}</span>}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <TasksFilterToolbar
            tab={tab}
            filters={filters}
            onChange={setFilters}
            onReset={() => setFilters(EMPTY_FILTERS)}
            onSearch={() => listQuery.refetch()}
            isFiltered={isFiltered}
          />

          <div className='min-h-0 flex-1 overflow-auto'>
            {tab === 'published' ? (
              <PublishedTaskTable
                tasks={items as PublishedTaskItem[]}
                loading={listQuery.isLoading}
              />
            ) : tab === 'merged' ? (
              <MergedTaskTable
                tasks={items as TaskListItem[]}
                loading={listQuery.isLoading}
                onQuickView={handleQuickView}
              />
            ) : tab === 'cherry-picks' ? (
              <CherryPickTab
                tasks={items as CherryPickTask[]}
                loading={listQuery.isLoading}
              />
            ) : (
              <DailyTaskTable
                tasks={items as TaskListItem[]}
                loading={listQuery.isLoading}
                trash={filters.trash ?? false}
                onQuickView={handleQuickView}
              />
            )}
          </div>
        </div>
      </SectionPageLayout.Content>

      <TasksPagination total={total} />

      <QuickViewDialog
        task={quickViewTask}
        open={quickViewTask != null}
        onOpenChange={(open) => !open && setQuickViewTask(null)}
      />
      <TaskTypeDialog open={typeDialogOpen} onOpenChange={setTypeDialogOpen} />
      <PublishTaskDialog
        open={publishTask != null}
        onOpenChange={(open) => !open && setPublishTask(null)}
        task={publishTask ?? undefined}
      />
    </SectionPageLayout>
  )
}
