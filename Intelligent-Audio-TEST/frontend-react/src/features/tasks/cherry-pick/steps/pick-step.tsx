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
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import type { PickFilters } from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
import {
  EMPTY_PICK_FILTERS,
  useCherryPickCandidates,
  useCherryPickCaseView,
  useCherryPickDeviceView,
  useCherryPickResultTypeView,
  usePickableTasks,
  usePickFilterOptions,
} from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import { usePickOrg } from '@/application/tasks/cherry-pick/use-pick-org'
import type {
  PickableTaskSortBy,
  PickableTaskSortOrder,
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
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PickFilterBar } from '@/features/tasks/cherry-pick/components/pick-filter-bar'
import { PickTaskStage } from '@/features/tasks/cherry-pick/components/pick-task-stage'
import { SlowCandidatesNotice } from '@/features/tasks/cherry-pick/components/slow-candidates-notice'
import { PickCaseView } from '@/features/tasks/cherry-pick/components/pick-case-view'
import {
  PickCaseOrgControls,
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
  /** 阶段 1 服务端排序（INT-1496 sort_by/sort_order；取代原客户端状态权重排序） */
  const [sortBy, setSortBy] = useState<PickableTaskSortBy>('status')
  const [sortOrder, setSortOrder] = useState<PickableTaskSortOrder>('asc')
  // 阶段 1 任务清单（pickable-tasks 任务级聚合 + 服务端分页排序，不受阶段 2 任务筛选影响）
  const pickableTasksQuery = usePickableTasks({ sortBy, sortOrder })
  const [phase, setPhase] = useState<'tasks' | 'results'>(
    presetTaskIds && presetTaskIds.length > 0 ? 'results' : 'tasks'
  )
  // 阶段 2 候选与筛选选项只在阶段 2 发起：阶段 1 的 Network 只应有 pickable-tasks（INT-1509）
  const candidatesQuery = useCherryPickCandidates(filters, {
    enabled: phase === 'results',
  })
  const options = usePickFilterOptions(phase === 'results')
  /** §3.8.3 用例层组织（三视图共享：分组/标签 + 平铺/交叉，阶段 2 会话态，usePickOrg） */
  const { org, subView, setOrg, setSubView } = usePickOrg()
  const caseView = useCherryPickCaseView(candidatesQuery.data)
  // 设备 / 结果类型视图的组织层纳入树构建（result_type 之下、用例卡之上）
  const deviceView = useCherryPickDeviceView(candidatesQuery.data, org, subView)
  const resultTypeView = useCherryPickResultTypeView(candidatesQuery.data, org, subView)
  const addEntries = usePickCartStore((s) => s.addEntries)

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

  /** 阶段 1 任务行（服务端已按 sort_by/sort_order 排序，前端不再聚合/重排） */
  const taskRows = pickableTasksQuery.items

  /** 任务名映射（阶段 2 任务集摘要条；pickable-tasks 即全量可挑选任务清单） */
  const taskNameById = useMemo(() => {
    const map = new Map<number, string>()
    for (const t of pickableTasksQuery.items) map.set(t.taskId, t.taskName)
    return map
  }, [pickableTasksQuery.items])

  /** 状态同步（§3.8.2）：清单刷新后剔除已不可挑选的旧任务，返回上一步/切换排序不残留 */
  useEffect(() => {
    if (pickableTasksQuery.isLoading || pickableTasksQuery.isError) return
    const available = new Set(pickableTasksQuery.items.map((t) => t.taskId))
    setSelectedTaskIds((prev) => {
      if (prev.size === 0) return prev
      const next = new Set([...prev].filter((id) => available.has(id)))
      return next.size === prev.size ? prev : next
    })
  }, [
    pickableTasksQuery.items,
    pickableTasksQuery.isLoading,
    pickableTasksQuery.isError,
  ])

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
        total={pickableTasksQuery.total}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onSortChange={(nextSortBy, nextSortOrder) => {
          setSortBy(nextSortBy)
          setSortOrder(nextSortOrder)
        }}
        selectedTaskIds={selectedTaskIds}
        loading={pickableTasksQuery.isLoading}
        slow={pickableTasksQuery.isSlow}
        isError={pickableTasksQuery.isError}
        onRetry={pickableTasksQuery.retry}
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
          candidatesQuery.isSlow ? (
            <SlowCandidatesNotice onRetry={candidatesQuery.retryCandidates} />
          ) : (
            <div className='flex flex-col gap-2 p-3'>
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className='h-9 w-full' />
              ))}
            </div>
          )
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
          // 设备/结果类型视图：顶/二层分支行 + result_type/设备 节点下的**组织层**
          // （分组/标签组头 → 用例卡，树由 buildPickDeviceView / buildPickResultTypeView 构建）
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
