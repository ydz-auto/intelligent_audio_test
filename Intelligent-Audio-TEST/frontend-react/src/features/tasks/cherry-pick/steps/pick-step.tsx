/**
 * 挑选步骤（Step 1/4，18_挑选合并交互重设计.md §3.3/§5.1，INT-600）。
 * 筛选栏 + 树形/平铺切换 + 全部展开/收起 + 多级挑选树 + 已选汇总条（sticky）。
 */
import {
  ChevronsDownUp,
  ChevronsUpDown,
  Layers,
  List,
  TreePine,
  TriangleAlert,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import type { PickFilters } from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
import {
  useCherryPickCandidates,
  useCherryPickCaseView,
  useCherryPickTree,
  usePickFilterOptions,
} from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import type { PickTreeBranch, PickTreeLeaf, PickTreeItem } from '@/domain/models/cherryPick'
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
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { Badge } from '@/components/ui/badge'
import { formatPickDateTime } from '@/features/tasks/cherry-pick/constants'
import { getEvaluationStatusMeta } from '@/features/tasks/constants'
import { PickFilterBar } from '@/features/tasks/cherry-pick/components/pick-filter-bar'
import { PickTree } from '@/features/tasks/cherry-pick/components/pick-tree'
import { SelectedSummaryBar } from '@/features/tasks/cherry-pick/components/selected-summary-bar'

export function PickStep({
  filters,
  onFiltersChange,
  onResetFilters,
  onAdded,
}: {
  filters: PickFilters
  onFiltersChange: (filters: PickFilters) => void
  onResetFilters: () => void
  /** 加购成功（已转购物车步骤） */
  onAdded: (addedCount: number, skippedCount: number) => void
}) {
  const options = usePickFilterOptions()
  const candidatesQuery = useCherryPickCandidates(filters)
  const tree = useCherryPickTree(candidatesQuery.data)
  const caseTree = useCherryPickCaseView(candidatesQuery.data)
  const addEntries = usePickCartStore((s) => s.addEntries)

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [view, setView] = useState<'tree' | 'case' | 'flat'>('tree')
  const [expandSignal, setExpandSignal] = useState<{ all: boolean; tick: number }>({
    all: false,
    tick: 0,
  })
  const [adding, setAdding] = useState(false)

  const stats = useMemo(
    () => computeSelectionStats(tree, selectedIds),
    [tree, selectedIds]
  )

  const handleToggleLeaf = (leaf: PickTreeLeaf) =>
    setSelectedIds((prev) => toggleLeafSelection(leaf, prev))

  const handleToggleBranch = (branch: PickTreeBranch, select: boolean) =>
    setSelectedIds((prev) => toggleBranchSelection(branch, prev, select))

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

  const flatLeaves = useMemo(() => {
    const leaves: PickTreeLeaf[] = []
    const walk = (items: PickTreeItem[]) => {
      for (const item of items) {
        if (item.kind === 'leaf') leaves.push(item)
        else walk(item.children)
      }
    }
    walk(tree)
    return leaves
  }, [tree])

  return (
    <div className='flex min-h-0 flex-1 flex-col gap-3'>
      <PickFilterBar
        filters={filters}
        onChange={onFiltersChange}
        options={options}
        onReset={onResetFilters}
      />

      <div className='flex flex-wrap items-center gap-2'>
        <div className='bg-muted/60 flex items-center gap-0.5 rounded-lg p-0.5'>
          <Button
            variant={view === 'tree' ? 'default' : 'ghost'}
            size='sm'
            className='h-6 gap-1 px-2 text-xs'
            onClick={() => setView('tree')}
          >
            <TreePine aria-hidden='true' className='size-3.5' />
            树形
          </Button>
          <Button
            variant={view === 'case' ? 'default' : 'ghost'}
            size='sm'
            className='h-6 gap-1 px-2 text-xs'
            onClick={() => setView('case')}
          >
            <Layers aria-hidden='true' className='size-3.5' />
            用例视角
          </Button>
          <Button
            variant={view === 'flat' ? 'default' : 'ghost'}
            size='sm'
            className='h-6 gap-1 px-2 text-xs'
            onClick={() => setView('flat')}
          >
            <List aria-hidden='true' className='size-3.5' />
            平铺
          </Button>
        </div>
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground h-7 gap-1 text-xs'
          onClick={() =>
            setExpandSignal((s) => ({ all: true, tick: s.tick + 1 }))
          }
        >
          <ChevronsDownUp aria-hidden='true' className='size-3.5' />
          全部展开
        </Button>
        <Button
          variant='ghost'
          size='sm'
          className='text-muted-foreground h-7 gap-1 text-xs'
          onClick={() =>
            setExpandSignal((s) => ({ all: false, tick: s.tick + 1 }))
          }
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
        ) : tree.length === 0 ? (
          <div className='flex flex-col items-center gap-1 py-10 text-center'>
            <p className='text-muted-foreground text-sm'>无符合条件的执行结果</p>
            <p className='text-muted-foreground/70 text-xs'>
              仅已完成、执行失败、已停止的终态任务可挑选，默认剔除已删除用例的结果
            </p>
          </div>
        ) : view === 'tree' ? (
          <PickTree
            className='p-2'
            items={tree}
            selectedIds={selectedIds}
            onToggleLeaf={handleToggleLeaf}
            onToggleBranch={handleToggleBranch}
            expandSignal={expandSignal}
          />
        ) : view === 'case' ? (
          <PickTree
            className='p-2'
            items={caseTree}
            selectedIds={selectedIds}
            onToggleLeaf={handleToggleLeaf}
            onToggleBranch={handleToggleBranch}
            expandSignal={expandSignal}
          />
        ) : (
          <div className='flex flex-col p-2'>
            {flatLeaves.map((leaf) => {
              const evalMeta = getEvaluationStatusMeta(leaf.evaluationStatus)
              return (
                <div
                  key={leaf.key}
                  className='hover:bg-muted/40 flex min-w-0 items-center gap-2 rounded-md px-2 py-1 text-[13px] transition-colors'
                >
                  <input
                    type='checkbox'
                    checked={selectedIds.has(leaf.resultId)}
                    onChange={() => handleToggleLeaf(leaf)}
                    className='accent-primary size-3.5'
                    aria-label={`结果 ${leaf.resultId}`}
                  />
                  <span className='min-w-0 flex-1 truncate font-medium'>
                    {leaf.caseName}
                  </span>
                  <span className='text-muted-foreground min-w-0 max-w-40 truncate'>
                    {leaf.deviceName ?? leaf.apiName ?? '—'}
                  </span>
                  <Badge variant='outline' className='font-mono text-[10px]'>
                    {leaf.resultType}
                  </Badge>
                  <StatusBadge
                    label={
                      leaf.executionStatus === 'completed'
                        ? '已完成'
                        : leaf.executionStatus === 'failed'
                          ? '执行失败'
                          : '已停止'
                    }
                    variant={
                      leaf.executionStatus === 'completed'
                        ? 'success'
                        : leaf.executionStatus === 'failed'
                          ? 'danger'
                          : 'neutral'
                    }
                  />
                  <StatusBadge
                    label={evalMeta.label}
                    variant={evalMeta.variant}
                    pulse={evalMeta.pulse}
                  />
                  <span className='text-muted-foreground shrink-0 font-mono text-[10px] whitespace-nowrap tabular-nums'>
                    {formatPickDateTime(leaf.createdAt)}
                  </span>
                  {leaf.added && (
                    <span className='text-muted-foreground/70 shrink-0 text-xs'>
                      已加购
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      <SelectedSummaryBar
        stats={stats}
        hasVisibleItems={tree.length > 0}
        onSelectAll={() => setSelectedIds((prev) => selectAllVisible(tree, prev))}
        onInvert={() => setSelectedIds((prev) => invertVisibleSelection(tree, prev))}
        onClear={() => setSelectedIds(clearSelection())}
        onAddToCart={handleAddToCart}
        adding={adding}
      />
    </div>
  )
}
