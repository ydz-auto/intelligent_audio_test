/**
 * 任务域页（09_任务域.md §3 + 18_挑选合并交互重设计.md §2.2，SectionPageLayout fixedContent + 三页签 + DataTablePage 骨架）。
 * 装配：Title「任务管理」/ Actions（创建新任务·导入数据·查看统计图表）/
 * Content（Tabs → 筛选工具栏 → 页签表格 → 批量浮条）/ Footer（分页 Portal）。
 * 页签路径式 /tasks/$tab（白名单校验在路由层）；「挑选合并」页签由 CherryPickTab 自持
 * （统一容器列表 + 四步向导），旧「合并」页签已收编（§2.2 裁定①）。
 */
import { Link, useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { ChartLine, FileDown, Plus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTasksList, type TaskListFilters } from '@/application/tasks/use-tasks-list'
import { useCherryPickContainers } from '@/application/tasks/cherry-pick/use-cherry-pick-containers'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { fetchPublishedTaskList } from '@/infrastructure/api/tasks-list-api'
import type { PublishedTaskItem, TaskListItem } from '@/domain/models/task'
import {
  TASKS_TABS,
  type TasksTabKey,
} from '@/features/tasks/constants'
import { TasksFilterToolbar } from '@/features/tasks/components/tasks-filter-toolbar'
import { DailyTaskTable } from '@/features/tasks/components/daily-task-table'
import { PublishedTaskTable } from '@/features/tasks/components/published-task-table'
import { CherryPickTab } from '@/features/tasks/cherry-pick'
import type { WizardStepKey } from '@/features/tasks/cherry-pick/constants'
import { TasksPagination } from '@/features/tasks/components/tasks-pagination'
import { QuickViewDialog } from '@/features/tasks/components/quick-view-dialog'
import { PublishTaskDialog } from '@/features/tasks/components/publish-task-dialog'
import { TaskTypeDialog } from '@/features/tasks/components/task-type-dialog'

export interface WizardState {
  step: WizardStepKey
  taskIds?: number[]
}

export function TasksPage({ tab }: { tab: TasksTabKey }) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)

  const [filters, setFilters] = useState<TaskListFilters>({ page: 1, pageSize: 10 })
  const [quickViewTask, setQuickViewTask] = useState<TaskListItem | null>(null)
  const [typeDialogOpen, setTypeDialogOpen] = useState(false)
  const [publishTask, setPublishTask] = useState<TaskListItem | null>(null)
  const [wizard, setWizard] = useState<WizardState | null>(null)

  // 页签切换重置筛选（URL 态回归：接线后 page/search/… 进 search，随 useTableUrlState）
  useEffect(() => {
    setFilters({ page: 1, pageSize: 10 })
  }, [tab])

  const algorithmType = algorithmId ? algorithmId : null
  const listQuery = useTasksList(tab, {
    ...filters,
    algorithmType: filters.algorithmType ?? algorithmType,
  })
  // 「挑选合并」页签计数 = 两类合并容器总数（§2.3/§11-1；各页签常取，供角标）
  const cherryContainers = useCherryPickContainers({})
  const cherryTotal = cherryContainers.data?.total ?? 0
  // 「已发布」页签计数 = published 列表 total（各页签常取，供角标；无权限隐藏页签不取）。
  // 本页签直接复用列表 query 的 total（与列表条数同源，口径一致）；其他页签由独立 count
  // query 提供（per_page=1 取 total，staleTime 与列表 query 对齐）。
  const publishedCountQuery = useQuery({
    queryKey: ['tasks', 'count', 'published'],
    queryFn: async () => (await fetchPublishedTaskList({ perPage: 1 })).total,
    enabled: hasPermission('published_task:read'),
    staleTime: 15_000,
  })
  const publishedTotal =
    tab === 'published'
      ? (listQuery.data?.total ?? publishedCountQuery.data ?? 0)
      : (publishedCountQuery.data ?? 0)

  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0

  const isFiltered = useMemo(
    () =>
      Object.entries(filters).some(([key, value]) => {
        if (key === 'algorithmType' || key === 'page' || key === 'pageSize') return false
        if (Array.isArray(value)) return value.length > 0
        return value != null && value !== '' && value !== false && value !== 'all'
      }),
    [filters]
  )

  /** 标签 facet 数据源：已加载日常任务的标签去重集合（对齐旧 Vue currentTags 口径，替代 mock 静态源） */
  const tagOptions = useMemo(() => {
    if (tab !== 'daily') return []
    const set = new Set<string>()
    ;(items as TaskListItem[]).forEach((t) => t.tags.forEach((tag) => set.add(tag)))
    return Array.from(set).sort()
  }, [items, tab])

  const handleQuickView = (task: TaskListItem) => {
    setQuickViewTask(task)
  }

  const handlePublish = (task: TaskListItem) => {
    setPublishTask(task)
  }

  const handleBatchPublish = (tasks: TaskListItem[]) => {
    // 批量发布：接首个选中任务打开 §5.2 发布弹窗（完整 BatchPublish 确认留待接线）
    setPublishTask(tasks[0] ?? null)
  }

  /** 批量浮条「加入挑选」（§2.2 裁定②：原「合并任务」钮撤销，吸收为任务级挑选） */
  const handleJoinPick = (tasks: TaskListItem[]) => {
    setWizard({ step: 'pick', taskIds: tasks.map((t) => t.id) })
    void navigate({ to: '/tasks/$tab', params: { tab: 'cherry-picks' } })
  }

  /** 筛选变化/查询：回到第 1 页（分页与筛选共用 queryKey） */
  const handleFiltersChange = (next: TaskListFilters) => {
    setFilters({ ...next, page: 1, pageSize: filters.pageSize ?? 10 })
  }

  const tabCount = (t: TasksTabKey) => {
    if (t === 'cherry-picks') return cherryTotal
    if (t === 'published') return publishedTotal
    return 0
  }

  return (
    <>
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
                  {t.key !== 'daily' && <span className='text-muted-foreground font-mono text-[11px] tabular-nums'>{tabCount(t.key) > 0 ? tabCount(t.key) : 0}</span>}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {tab !== 'cherry-picks' && (
            <TasksFilterToolbar
              tab={tab}
              filters={filters}
              tagOptions={tagOptions}
              onChange={handleFiltersChange}
              onReset={() => setFilters({ page: 1, pageSize: filters.pageSize ?? 10 })}
              onSearch={() => listQuery.refetch()}
              isFiltered={isFiltered}
            />
          )}

          <div className='min-h-0 flex-1 overflow-auto'>
            {tab === 'published' ? (
              <PublishedTaskTable
                tasks={items as PublishedTaskItem[]}
                loading={listQuery.isLoading}
                error={listQuery.isError}
                onRetry={() => listQuery.refetch()}
              />
            ) : tab === 'cherry-picks' ? (
              <CherryPickTab
                wizard={wizard}
                onWizardOpen={(step, taskIds) => setWizard({ step, taskIds })}
                onWizardClose={() => setWizard(null)}
              />
            ) : (
              <DailyTaskTable
                tasks={items as TaskListItem[]}
                loading={listQuery.isLoading}
                error={listQuery.isError}
                onRetry={() => listQuery.refetch()}
                trash={filters.trash ?? false}
                onQuickView={handleQuickView}
                onPublish={handlePublish}
                onBatchPublish={handleBatchPublish}
                onJoinPick={handleJoinPick}
                onCreate={() => setTypeDialogOpen(true)}
              />
            )}
          </div>
        </div>

        {tab !== 'cherry-picks' && (
          <TasksPagination
            total={total}
            page={filters.page ?? 1}
            pageSize={filters.pageSize ?? 10}
            onPageChange={(page) => setFilters((prev) => ({ ...prev, page }))}
            onPageSizeChange={(pageSize) => setFilters((prev) => ({ ...prev, pageSize, page: 1 }))}
          />
        )}
      </SectionPageLayout.Content>
    </SectionPageLayout>

    <QuickViewDialog
        task={quickViewTask}
        open={quickViewTask != null}
        onOpenChange={(open) => !open && setQuickViewTask(null)}
      />
      <TaskTypeDialog open={typeDialogOpen} onOpenChange={setTypeDialogOpen} />
      <PublishTaskDialog
        key={publishTask?.id ?? 'none'}
        open={publishTask != null}
        onOpenChange={(open) => !open && setPublishTask(null)}
        task={publishTask ?? undefined}
      />
    </>
  )
}
