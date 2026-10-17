/**
 * 购物车管理面板（18_挑选合并交互重设计.md §4.2/§4.3，INT-600）。
 * 购物车抽屉与复核步骤（编辑态）共用的购物车树 + 移除矩阵全量：
 * 单条 X / 节点「移除该组」/ 整组「移除整组」/ 批量勾选移除 / 一键移除失效 / 清空 / 另存挑选集。
 */
import { Save, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/confirm-dialog'
import type { CartTreeBranch, CartTreeLeaf } from '@/domain/models/cherryPick'
import { CartTree } from '@/features/tasks/cherry-pick/components/cart-tree'
import { SavePickSetDialog } from '@/features/tasks/cherry-pick/components/save-pick-set-dialog'

interface ConfirmState {
  open: boolean
  title: string
  desc: string
  onConfirm: () => void
}

/**
 * 购物车树 + 移除矩阵 + 清空/另存挑选集。onGoReview/onGoContinuePick 由外层注入
 * （抽屉「去复核（n）」/「继续挑选」，复核步骤「返回挑选」）。
 */
export function CartPanel({
  onGoReview,
  onGoContinuePick,
  continueLabel = '继续挑选',
  reviewLabel = '去复核',
  showFooter = true,
  readOnly = false,
}: {
  onGoReview?: () => void
  onGoContinuePick?: () => void
  continueLabel?: string
  reviewLabel?: string
  showFooter?: boolean
  /** 只读态（algo_engineer：增删钮隐藏，§8） */
  readOnly?: boolean
}) {
  const groups = usePickCartStore((s) => s.groups)
  const total = usePickCartStore((s) => s.total)
  const invalidItemIds = usePickCartStore((s) => s.invalidItemIds)
  const removeEntries = usePickCartStore((s) => s.removeEntries)
  const removeInvalid = usePickCartStore((s) => s.removeInvalid)
  const clearCart = usePickCartStore((s) => s.clearCart)

  const [selectedEntryIds, setSelectedEntryIds] = useState<Set<string>>(new Set())
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)

  const selectedCount = selectedEntryIds.size

  const askRemove = (title: string, desc: string, onConfirm: () => void) => {
    setConfirm({ open: true, title, desc, onConfirm })
  }

  const removeMany = async (ids: string[]) => {
    await removeEntries(ids)
    setSelectedEntryIds(new Set())
    toast.success(`已移除 ${ids.length} 条`)
  }

  const handleRemoveSingle = (entryId: string) => {
    askRemove('移除该结果', '将移除该结果条目，是否继续？', () => {
      void removeMany([entryId])
    })
  }

  const handleRemoveNode = (
    entryIds: string[],
    levelLabel: string,
    name: string,
    count: number
  ) => {
    askRemove(
      `移除${levelLabel}「${name}」`,
      `将移除该${levelLabel}下的 ${count} 条结果，是否继续？`,
      () => void removeMany(entryIds)
    )
  }

  const handleRemoveTask = (taskId: number, taskName: string, count: number) => {
    const group = groups.find((g) => g.taskId === taskId)
    if (!group) return
    const ids = group.entries.map((e) => e.itemId)
    askRemove(
      `移除来源任务「${taskName}」`,
      `将移除来源任务「${taskName}」下的 ${count} 条结果，是否继续？`,
      () => void removeMany(ids)
    )
  }

  const handleClear = () => {
    askRemove('清空购物车', `将清空购物车全部 ${total} 条结果，是否继续？`, async () => {
      await clearCart()
      setSelectedEntryIds(new Set())
      toast.success('购物车已清空')
    })
  }

  return (
    <div className='flex min-h-0 flex-1 flex-col'>
      <div className='min-h-0 flex-1 overflow-y-auto'>
        {total === 0 ? (
          <div className='flex flex-col items-center gap-2 py-10 text-center'>
            <Trash2 aria-hidden='true' className='text-muted-foreground size-8' />
            <p className='text-muted-foreground text-sm'>购物车为空</p>
            <p className='text-muted-foreground/70 text-xs'>
              从任务详情或报告结果列表勾选执行结果「加入购物车」
            </p>
          </div>
        ) : (
          <>
            {!readOnly && invalidItemIds.length > 0 && (
              <div className='border-warning/40 bg-warning/10 mb-3 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs'>
                <span className='flex-1'>
                  {invalidItemIds.length} 条已失效（源结果已删除）
                </span>
                <Button
                  variant='ghost'
                  size='xs'
                  className='text-warning h-6'
                  onClick={async () => {
                    await removeInvalid()
                    toast.success('失效条目已移除')
                  }}
                >
                  移除失效条目（{invalidItemIds.length}）
                </Button>
              </div>
            )}
            <CartTree
              groups={groups}
              selectedEntryIds={selectedEntryIds}
              readOnly={readOnly}
              onToggleLeaf={(leaf: CartTreeLeaf) =>
                setSelectedEntryIds((prev) => {
                  const next = new Set(prev)
                  if (next.has(leaf.entryId)) next.delete(leaf.entryId)
                  else next.add(leaf.entryId)
                  return next
                })
              }
              onToggleBranch={(branch: CartTreeBranch, select: boolean) =>
                setSelectedEntryIds((prev) => {
                  const next = new Set(prev)
                  for (const id of branch.entryIds) {
                    if (select) next.add(id)
                    else next.delete(id)
                  }
                  return next
                })
              }
              onRemoveEntry={handleRemoveSingle}
              onRemoveNode={handleRemoveNode}
              onRemoveTask={handleRemoveTask}
            />
            {!readOnly && selectedCount > 0 && (
              <div className='sticky bottom-3 mt-3'>
                <div className='bg-background/95 supports-backdrop-filter:bg-background/60 mx-auto flex w-max items-center gap-1 rounded-xl border p-2 shadow-xl backdrop-blur-lg'>
                  <Badge className='min-w-8 justify-center rounded-lg'>
                    {selectedCount}
                  </Badge>
                  <Button
                    size='sm'
                    variant='destructive'
                    className='gap-1.5'
                    onClick={() =>
                      askRemove(
                        '批量移除',
                        `将移除已选 ${selectedCount} 条结果，是否继续？`,
                        () => void removeMany([...selectedEntryIds])
                      )
                    }
                  >
                    <Trash2 aria-hidden='true' className='size-3.5' />
                    移除已选（{selectedCount}）
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {showFooter && (
        <div className='mt-3 flex flex-wrap items-center gap-2 border-t pt-3'>
          {!readOnly && (
            <>
              <Button
                variant='ghost'
                size='sm'
                className='text-destructive hover:text-destructive gap-1.5'
                disabled={total === 0}
                onClick={handleClear}
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
                清空购物车
              </Button>
              <Button
                variant='outline'
                size='sm'
                className='gap-1.5'
                disabled={total === 0}
                onClick={() => setSaveOpen(true)}
              >
                <Save aria-hidden='true' className='size-3.5' />
                另存为挑选集
              </Button>
            </>
          )}
          <div className='ml-auto flex gap-2'>
            {onGoContinuePick && (
              <Button variant='outline' size='sm' onClick={onGoContinuePick}>
                {continueLabel}
              </Button>
            )}
            {onGoReview && (
              <Button size='sm' disabled={total === 0} onClick={onGoReview}>
                {reviewLabel}（{total}）
              </Button>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirm?.open ?? false}
        onOpenChange={(v) => setConfirm((c) => (c ? { ...c, open: v } : c))}
        title={confirm?.title ?? ''}
        desc={confirm?.desc ?? ''}
        destructive
        confirmText='继续'
        handleConfirm={async () => {
          await confirm?.onConfirm()
          setConfirm(null)
        }}
      />

      <SavePickSetDialog open={saveOpen} onOpenChange={setSaveOpen} />
    </div>
  )
}
