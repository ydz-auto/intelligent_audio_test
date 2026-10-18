/**
 * 任务域页（09_任务域.md §3 + 18_挑选合并交互重设计.md §2.2，SectionPageLayout fixedContent + 三页签 + DataTablePage 骨架）。
 * 装配：Title「任务管理」/ Actions（创建新任务·导入数据·查看统计图表）/
 * Content（Tabs → 筛选工具栏 → 页签表格 → 批量浮条）/ Footer（分页 Portal）。
 * 页签路径式 /tasks/$tab（白名单校验在路由层）；「挑选合并」页签由 CherryPickTab 自持
 * （统一容器列表 + 四步向导），旧「合并」页签已收编（§2.2 裁定①）。
 * 模态窗群：任务类型/发布/快速查看 + §5.7 重新执行·重新评估范围 + §5.12 导出/导入数据。
 */
import { Link, useNavigate } from '@tanstack/react-router'
import { ChartLine, FileDown, Plus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTasksList, type TaskListFilters } from '@/application/tasks/use-tasks-list'
import { useCherryPickContainers } from '@/application/tasks/cherry-pick/use-cherry-pick-containers'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
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
import { ReexecuteScopeDialog } from '@/features/tasks/components/reexecute-scope-dialog'
import { DataExportDialog } from '@/features/tasks/components/data-export-dialog'
import { DataImportDialog } from '@/features/tasks/components/data-import-dialog'
import type { ReexecuteActionType } from '@/features/tasks/components/task-row-actions'

const EMPTY_FILTERS: TaskListFilters = {}

export interface WizardState {
  step: WizardStepKey
  taskIds?: number[]
}

export function TasksPage({ tab }: { tab: TasksTabKey }) {
  const { hasPermission } = usePermissions()
  const navigate = useNavigate()
  const algorithmId = useAlgorithmStore((s) => s.algorithmId)

  const [filters, setFilters] = useState<TaskListFilters>(EMPTY_FILTERS)
  const [quickViewTask, setQuickViewTask] = useState<TaskListItem | null>(null)
  const [typeDialogOpen, setTypeDialogOpen] = useState(false)
  const [publishTask, setPublishTask] = useState<TaskListItem | null>(null)
  const [wizard, setWizard] = useState<WizardState | null>(null)
  const [reexecuteState, setReexecuteState] = useState<{
    task: TaskListItem
    actionType: ReexecuteActionType
  } | null>(null)
  const [exportTasks, setExportTasks] = useState<TaskListItem[] | null>(null)
  const [importOpen, setImportOpen] = useState(false)

  // 页签切换重置筛选（URL 态回归：接线后 page/search/… 进 search，随 useTableUrlState）
  useEffect(() => {
    setFilters(EMPTY_FILTERS)
  }, [tab])

  const algorithmType = algorithmId ? algorithmId : null
  const listQuery = useTasksList(tab, {
    ...filters,
    algorithmType: filters.algorithmType ?? algorithmType,
  })
  // 「挑选合并」页签计数 = 两类合并容器总数（§2.3/§11-1）
  const cherryContainers = useCherryPickContainers({})
  const cherryTotal = tab === 'cherry-picks' ? cherryContainers.data?.total ?? 0 : 0

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

  /** 重新执行/重新评估 → §5.7 范围选择弹窗 */
  const handleReexecute = (task: TaskListItem, actionType: ReexecuteActionType) => {
    setReexecuteState({ task, actionType })
  }

  /** 批量浮条「导出数据」→ §5.12 导出弹窗 */
  const handleExport = (tasks: TaskListItem[]) => {
    setExportTasks(tasks)
  }

  const tabCount = (t: TasksTabKey) => {
    if (t === 'cherry-picks') return cherryTotal
    return total
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
            onClick={() => setImportOpen(true)}
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
              onChange={setFilters}
              onReset={() => setFilters(EMPTY_FILTERS)}
              onSearch={() => listQuery.refetch()}
              isFiltered={isFiltered}
            />
          )}

          <div className='min-h-0 flex-1 overflow-auto'>
            {tab === 'published' ? (
              <PublishedTaskTable
                tasks={items as PublishedTaskItem[]}
                loading={listQuery.isLoading}
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
                trash={filters.trash ?? false}
                onQuickView={handleQuickView}
                onPublish={handlePublish}
                onBatchPublish={handleBatchPublish}
                onJoinPick={handleJoinPick}
                onReexecute={handleReexecute}
                onExport={handleExport}
                onCreate={() => setTypeDialogOpen(true)}
              />
            )}
          </div>
        </div>

        {tab !== 'cherry-picks' && <TasksPagination total={total} />}
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
      <ReexecuteScopeDialog
        open={reexecuteState != null}
        onOpenChange={(open) => !open && setReexecuteState(null)}
        taskId={reexecuteState?.task.id ?? 0}
        taskName={reexecuteState?.task.name ?? ''}
        actionType={reexecuteState?.actionType ?? 'retry'}
      />
      <DataExportDialog
        open={exportTasks != null}
        onOpenChange={(open) => !open && setExportTasks(null)}
        tasks={(exportTasks ?? []).map((t) => ({
          id: t.id,
          name: t.name,
          status: t.execution_status,
        }))}
        onExported={() => void listQuery.refetch()}
      />
      <DataImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onImported={() => void listQuery.refetch()}
      />
    </>
  )
}
