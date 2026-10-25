/**
 * 挑选步骤（Step 1/4，18_挑选合并交互重设计.md §3.8.2/§3.8.3/§5.1，INT-600/INT-1047）。
 * 两阶段状态机（§3.8.2）：阶段 1 选择任务（PickTaskStage）→ 阶段 2 选择结果；
 * 阶段 2 三视图（用例视图 / 设备视图 / 结果类型视图，§3.8.3），共享同一 selectedResultIds；
 * 勾选跨阶段保留；已选汇总条（sticky）。
 */
import {
  ChevronsDownUp,
  ChevronsUpDown,
  ListChecks,
  Smartphone,
  Tag,
  TriangleAlert,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import type { PickFilters } from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
import {
  EMPTY_PICK_FILTERS,
  useCherryPickCandidates,
  useCherryPickCaseView,
  useCherryPickDeviceView,
  useCherryPickResultTypeView,
  usePickFilterOptions,
} from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import { useCherryPickContainers } from '@/application/tasks/cherry-pick/use-cherry-pick-containers'
import { usePickOrg } from '@/application/tasks/cherry-pick/use-pick-org'
import type {
  PickTreeBranch,
  PickTreeItem,
  PickTreeLeaf,
} from '@/domain/models/cherryPick'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  clearSelection,
  computeSelectionStats,
  invertVisibleSelection,
  selectAllVisible,
  toggleBranchSelection,
  toggleLeafSelection,
} from '@/domain/lib/cherry-pick-tree'
import { excludeContainerTaskRows } from '@/domain/lib/container-composition'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PickFilterBar } from '@/features/tasks/cherry-pick/components/pick-filter-bar'
import {
  PickTaskStage,
  getTaskStatusOrder,
  type PickTaskRow,
} from '@/features/tasks/cherry-pick/components/pick-task-stage'
import { PickCaseView } from '@/features/tasks/cherry-pick/components/pick-case-view'
import {
  PickCaseOrgControls,
  PickCaseOrgList,
} from '@/features/tasks/cherry-pick/components/pick-case-org-list'
import { PickTree } from '@/features/tasks/cherry-pick/components/pick-tree'
import { SelectedSummaryBar } from '@/features/tasks/cherry-pick/components/selected-summary-bar'

/** 阶段 2 三视图（§3.8.3：用例/设备/结果类型，任务维度由阶段 1 承载） */
export type PickResultView = 'case' | 'device' | 'resultType'

export function PickStep({
  filters,
  onFiltersChange,
  onResetFilters,
  onAdded,
  presetTaskIds,
}: {
  filters: PickFilters
  onFiltersChange: (filters: PickFilters) => void
  onResetFilters: () => void
  /** 加购成功（已转购物车步骤） */
  onAdded: (addedCount: number, skippedCount: number) => void
  /** 批量「加入挑选」预选任务：非空 → 跳过阶段 1 直达阶段 2（§3.8.2/§6.1） */
  presetTaskIds?: number[]
}) {
  const options = usePickFilterOptions()
  // 阶段 1 任务集聚合（全量候选，不受阶段 2 任务筛选影响，§3.8.2 数据源=候选行聚合）
  const allCandidatesQuery = useCherryPickCandidates(EMPTY_PICK_FILTERS)
  const candidatesQuery = useCherryPickCandidates(filters)
  const caseView = useCherryPickCaseView(candidatesQuery.data)
  const deviceView = useCherryPickDeviceView(candidatesQuery.data)
  const resultTypeView = useCherryPickResultTypeView(candidatesQuery.data)
  const addEntries = usePickCartStore((s) => s.addEntries)
  // §5.5.5：容器本身不进阶段 1 可挑选清单。后端候选聚合本就不含容器（容器无 test_results），
  // 这里按既有容器列表再显式过滤一次，保证后端口径变化时清单仍成立；
  // 与页签计数同一 query key → 向导内零新增请求。
  const containersQuery = useCherryPickContainers({})
  const containerTaskIds = useMemo(
    () => new Set((containersQuery.data?.items ?? []).map((c) => c.id)),
    [containersQuery.data]
  )

  const [phase, setPhase] = useState<'tasks' | 'results'>(
    presetTaskIds && presetTaskIds.length > 0 ? 'results' : 'tasks'
  )
  const [selectedTaskIds, setSelectedTaskIds] = useState<Set<number>>(
    () => new Set(presetTaskIds ?? filters.taskIds)
  )
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [view, setView] = useState<PickResultView>('case')
  const [expandSignal, setExpandSignal] = useState<{ all: boolean; tick: number }>({
    all: false,
    tick: 0,
  })
  const [adding, setAdding] = useState(false)
  /** §3.8.3 用例层组织（三视图共享：分组/标签 + 平铺/交叉，阶段 2 会话态，usePickOrg） */
  const { org, subView, setOrg, setSubView } = usePickOrg()

  /** 阶段 1 任务行聚合（终态候选按 taskId 分组，§3.8.2 按状态/名称排序） */
  const taskRows = useMemo<PickTaskRow[]>(() => {
    const rows = allCandidatesQuery.data ?? []
    const map = new Map<number, PickTaskRow>()
    for (const c of rows) {
      const cur = map.get(c.taskId)
      if (cur) {
        cur.count += 1
        if (!cur.createdAt && c.createdAt) cur.createdAt = c.createdAt
      } else {
        map.set(c.taskId, {
          taskId: c.taskId,
          taskName: c.taskName,
          executionStatus: c.executionStatus,
          createdAt: c.createdAt,
          count: 1,
        })
      }
    }
    return excludeContainerTaskRows([...map.values()], containerTaskIds).sort(
      (a, b) =>
        getTaskStatusOrder(a.executionStatus) - getTaskStatusOrder(b.executionStatus) ||
        a.taskName.localeCompare(b.taskName, 'zh-CN')
    )
  }, [allCandidatesQuery.data, containerTaskIds])

  /** 任务名映射（阶段 2 任务集摘要条；fetchPickableTasks 兜底补未入候选页的任务） */
  const taskNameById = useMemo(() => {
    const map = new Map<number, string>()
    for (const c of allCandidatesQuery.data ?? []) map.set(c.taskId, c.taskName)
    for (const t of options.tasks) if (!map.has(t.id)) map.set(t.id, t.name)
    return map
  }, [allCandidatesQuery.data, options.tasks])

  const selectedTaskNames = useMemo(
    () => [...selectedTaskIds].map((id) => taskNameById.get(id)).filter(Boolean) as string[],
    [selectedTaskIds, taskNameById]
  )

  /** 当前视图树（用例/设备/结果类型，三视图共享同一 selectedResultIds） */
  const currentTree = useMemo<PickTreeItem[]>(() => {
    if (view === 'case') return caseView
    if (view === 'device') return deviceView
    return resultTypeView
  }, [view, caseView, deviceView, resultTypeView])

  const stats = useMemo(
    () => computeSelectionStats(currentTree, selectedIds),
    [currentTree, selectedIds]
  )

  const handleToggleLeaf = (leaf: PickTreeLeaf) =>
    setSelectedIds((prev) => toggleLeafSelection(leaf, prev))

  const handleToggleBranch = (branch: PickTreeBranch, select: boolean) =>
    setSelectedIds((prev) => toggleBranchSelection(branch, prev, select))

  /** 阶段 1「下一步：选择结果」——提交任务集锁定阶段 2 候选，勾选跨阶段保留 */
  const handleNext = () => {
    onFiltersChange({ ...filters, taskIds: [...selectedTaskIds] })
    setPhase('results')
  }

  /** 重置：阶段 2 保留阶段 1 锁定的任务集（§6.2 筛选与勾选解耦） */
  const handleResetFilters = () => {
    if (phase === 'results') {
      onFiltersChange({ ...EMPTY_PICK_FILTERS, taskIds: [...selectedTaskIds] })
    } else {
      onResetFilters()
    }
  }

  const handleAddToCart = async () => {
    if (stats.results === 0) return
    setAdding(true)
    try {
      const { addedCount, skippedCount, invalidCount } = await addEntries([
        ...selectedIds,
      ])
      if (addedCount > 0) {
        const suffix =
          invalidCount > 0
            ? `${addedCount} 条，${invalidCount} 条源结果已失效未加入`
            : skippedCount > 0
              ? `${addedCount} 条（重复 ${skippedCount} 条已跳过）`
              : `${addedCount} 条`
        toast.success(`已加入购物车 ${suffix}`)
        setSelectedIds(new Set())
        onAdded(addedCount, skippedCount)
      } else {
        toast.success('已加入购物车（重复条目已跳过）')
        setSelectedIds(new Set())
        onAdded(0, skippedCount)
      }
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.userMessage : '加入购物车失败，请重试'
      )
    } finally {
      setAdding(false)
    }
  }

  /** 阶段 1 · 选择任务 */
  if (phase === 'tasks') {
    return (
      <PickTaskStage
        tasks={taskRows}
        selectedTaskIds={selectedTaskIds}
        loading={allCandidatesQuery.isLoading}
        isError={allCandidatesQuery.isError}
        onRetry={() => void allCandidatesQuery.refetch()}
        onToggle={(taskId) =>
          setSelectedTaskIds((prev) => {
            const next = new Set(prev)
            if (next.has(taskId)) next.delete(taskId)
            else next.add(taskId)
            return next
          })
        }
        onSelectAll={(ids) => setSelectedTaskIds(new Set(ids))}
        onClear={() => setSelectedTaskIds(new Set())}
        onNext={handleNext}
      />
    )
  }

  /** 阶段 2 · 选择结果（三视图） */
  return (
    <div className='flex min-h-0 flex-1 flex-col gap-3'>
      <h3 className='text-sm font-medium'>挑选 · 阶段 2：选择结果</h3>
      <PickFilterBar
        filters={filters}
        onChange={onFiltersChange}
        options={options}
        onReset={handleResetFilters}
        hideTaskFacet
      />

      {/* 任务集摘要条 +「更换任务」（§3.8.2，勾选跨阶段保留不清空） */}
      <div className='flex flex-wrap items-center gap-2'>
        <span className='text-sm font-medium'>已选任务：</span>
        <span className='text-muted-foreground min-w-0 flex-1 truncate text-sm'>
          {selectedTaskNames.length > 0 ? selectedTaskNames.join(' · ') : '—'}
        </span>
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground h-7 text-xs'
          onClick={() => setPhase('tasks')}
        >
          更换任务
        </Button>
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        <div className='bg-muted/60 flex items-center gap-0.5 rounded-lg p-0.5'>
          <Button
            variant={view === 'case' ? 'default' : 'ghost'}
            size='sm'
            className='h-6 gap-1 px-2 text-xs'
            onClick={() => setView('case')}
          >
            <ListChecks aria-hidden='true' className='size-3.5' />
            用例视图
          </Button>
          <Button
            variant={view === 'device' ? 'default' : 'ghost'}
            size='sm'
            className='h-6 gap-1 px-2 text-xs'
            onClick={() => setView('device')}
          >
            <Smartphone aria-hidden='true' className='size-3.5' />
            设备视图
          </Button>
          <Button
            variant={view === 'resultType' ? 'default' : 'ghost'}
            size='sm'
            className='h-6 gap-1 px-2 text-xs'
            onClick={() => setView('resultType')}
          >
            <Tag aria-hidden='true' className='size-3.5' />
            结果类型视图
          </Button>
        </div>
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground h-7 gap-1 text-xs'
          onClick={() => setExpandSignal((s) => ({ all: true, tick: s.tick + 1 }))}
        >
          <ChevronsDownUp aria-hidden='true' className='size-3.5' />
          全部展开
        </Button>
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground h-7 gap-1 text-xs'
          onClick={() => setExpandSignal((s) => ({ all: false, tick: s.tick + 1 }))}
        >
          <ChevronsUpDown aria-hidden='true' className='size-3.5' />
          全部收起
        </Button>
        <span className='text-muted-foreground ml-auto text-xs'>
          仅已完成、执行失败、已停止的终态任务可挑选
        </span>
      </div>

      <div className='min-h-0 flex-1 overflow-auto rounded-lg border'>
        {candidatesQuery.isLoading ? (
          <div className='flex flex-col gap-2 p-3'>
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className='h-9 w-full' />
            ))}
          </div>
        ) : candidatesQuery.isError ? (
          <div className='flex flex-col items-center gap-2 py-10 text-center'>
            <TriangleAlert aria-hidden='true' className='text-destructive size-6' />
            <p className='text-muted-foreground text-sm'>候选加载失败，请重试</p>
            <Button
              variant='outline'
              size='sm'
              className='mt-1'
              onClick={() => void candidatesQuery.refetch()}
            >
              重试
            </Button>
          </div>
        ) : currentTree.length === 0 ? (
          <div className='flex flex-col items-center gap-1 py-10 text-center'>
            <p className='text-muted-foreground text-sm'>无符合条件的执行结果</p>
            <p className='text-muted-foreground/70 text-xs'>
              仅已完成、执行失败、已停止的终态任务可挑选，默认剔除已删除用例的结果
            </p>
          </div>
        ) : view === 'case' ? (
          <PickCaseView
            branches={caseView}
            selectedIds={selectedIds}
            onToggleLeaf={handleToggleLeaf}
            onToggleBranch={handleToggleBranch}
            expandSignal={expandSignal}
            org={org}
            subView={subView}
            onOrgChange={setOrg}
            onSubViewChange={setSubView}
          />
        ) : (
          // 设备/结果类型视图：顶/二层分支行 + 每 result_type/设备 节点下用例层组织（§3.8.3 用例层组织）
          <div className='flex min-h-0 flex-col'>
            <div className='border-b py-2'>
              <PickCaseOrgControls
                org={org}
                subView={subView}
                onOrgChange={setOrg}
                onSubViewChange={setSubView}
              />
            </div>
            <PickTree
              className='p-2'
              items={view === 'device' ? deviceView : resultTypeView}
              selectedIds={selectedIds}
              onToggleLeaf={handleToggleLeaf}
              onToggleBranch={handleToggleBranch}
              expandSignal={expandSignal}
              showLeafTask
              renderCaseLayer={(caseBranches) => (
                <PickCaseOrgList
                  branches={caseBranches}
                  selectedIds={selectedIds}
                  onToggleLeaf={handleToggleLeaf}
                  onToggleBranch={handleToggleBranch}
                  expandSignal={expandSignal}
                  org={org}
                  subView={subView}
                  onOrgChange={setOrg}
                  onSubViewChange={setSubView}
                  showControls={false}
                />
              )}
            />
          </div>
        )}
      </div>

      <SelectedSummaryBar
        stats={stats}
        hasVisibleItems={currentTree.length > 0}
        onSelectAll={() =>
          setSelectedIds((prev) => selectAllVisible(currentTree, prev))
        }
        onInvert={() =>
          setSelectedIds((prev) => invertVisibleSelection(currentTree, prev))
        }
        onClear={() => setSelectedIds(clearSelection())}
        onAddToCart={handleAddToCart}
        adding={adding}
      />
    </div>
  )
}
