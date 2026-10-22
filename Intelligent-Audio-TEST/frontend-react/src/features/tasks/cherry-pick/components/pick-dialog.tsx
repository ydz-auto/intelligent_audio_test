/**
 * 快捷加购弹窗（18_挑选合并交互重设计.md §6.1/§7.1，INT-600）。
 * 任务详情关联用例结果行 / 对比报告结果行入口；复用多级挑选树，预筛来源任务=当前任务。
 * 加购后可「继续挑选」或「去购物车」。
 */
import { ShoppingCart, TriangleAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  useCherryPickCandidates,
  useCherryPickTree,
} from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import type { PickTreeBranch, PickTreeLeaf } from '@/domain/models/cherryPick'
import {
  computeSelectionStats,
  toggleBranchSelection,
  toggleLeafSelection,
} from '@/domain/lib/cherry-pick-tree'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { PickTree } from '@/features/tasks/cherry-pick/components/pick-tree'
import { SlowCandidatesNotice } from '@/features/tasks/cherry-pick/components/slow-candidates-notice'
import { EMPTY_PICK_FILTERS } from '@/application/tasks/cherry-pick/use-cherry-pick-candidates'

export function PickDialog({
  open,
  onOpenChange,
  sourceTaskId,
  sourceTaskName,
  onGoCart,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  sourceTaskId?: number
  sourceTaskName?: string
  /** 加购成功后可「去购物车」 */
  onGoCart?: () => void
}) {
  const filters = useMemo<typeof EMPTY_PICK_FILTERS>(
    () => ({
      ...EMPTY_PICK_FILTERS,
      taskIds: sourceTaskId != null ? [sourceTaskId] : [],
    }),
    [sourceTaskId]
  )
  const candidatesQuery = useCherryPickCandidates(filters)
  const tree = useCherryPickTree(candidatesQuery.data)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const addEntries = usePickCartStore((s) => s.addEntries)
  const [adding, setAdding] = useState(false)

  const stats = useMemo(
    () => computeSelectionStats(tree, selectedIds),
    [tree, selectedIds]
  )

  const handleToggleLeaf = (leaf: PickTreeLeaf) =>
    setSelectedIds((prev) => toggleLeafSelection(leaf, prev))

  const handleToggleBranch = (branch: PickTreeBranch, select: boolean) =>
    setSelectedIds((prev) => toggleBranchSelection(branch, prev, select))

  const handleAdd = async () => {
    setAdding(true)
    const { addedCount, skippedCount, invalidCount } = await addEntries(
      [...selectedIds]
    )
    setAdding(false)
    if (addedCount > 0) {
      const suffix =
        invalidCount > 0
          ? `${addedCount} 条，${invalidCount} 条源结果已失效未加入`
          : skippedCount > 0
            ? `${addedCount} 条（重复 ${skippedCount} 条已跳过）`
            : `${addedCount} 条`
      toast.success(`已加入购物车 ${suffix}`)
      setSelectedIds(new Set())
      onOpenChange(false)
    } else {
      toast.success('已加入购物车（重复条目已跳过）')
      onOpenChange(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle>加入购物车</DialogTitle>
          <DialogDescription>
            {sourceTaskName
              ? `从任务「${sourceTaskName}」勾选执行结果加入购物车`
              : '勾选执行结果加入购物车'}
          </DialogDescription>
        </DialogHeader>

        {candidatesQuery.isLoading ? (
          candidatesQuery.isSlow ? (
            <SlowCandidatesNotice onRetry={candidatesQuery.retryCandidates} />
          ) : (
            <div className='flex flex-col gap-2 py-2'>
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className='h-9 w-full' />
              ))}
            </div>
          )
        ) : candidatesQuery.isError ? (
          <div className='flex flex-col items-center gap-2 px-2 py-6 text-center'>
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
          <p className='text-muted-foreground px-2 py-6 text-center text-sm'>
            无符合条件的执行结果
          </p>
        ) : (
          <ScrollArea className='max-h-[420px]'>
            <PickTree
              items={tree}
              selectedIds={selectedIds}
              onToggleLeaf={handleToggleLeaf}
              onToggleBranch={handleToggleBranch}
            />
          </ScrollArea>
        )}

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            className='gap-1.5'
            disabled={stats.results === 0}
            onClick={handleAdd}
          >
            <ShoppingCart aria-hidden='true' className='size-3.5' />
            {adding ? '加入中…' : `加入购物车（${stats.results}）`}
          </Button>
          {onGoCart && (
            <Button variant='ghost' onClick={onGoCart}>
              去购物车
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
