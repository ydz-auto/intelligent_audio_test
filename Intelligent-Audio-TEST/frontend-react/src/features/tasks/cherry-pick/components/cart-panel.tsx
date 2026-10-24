/**
 * 购物车管理面板（18_挑选合并交互重设计.md §4.2/§4.3，INT-600 / INT-1694）。
 * 购物车抽屉与复核步骤（编辑态）共用的购物车树 + 移除矩阵全量：
 * 单条 X / 节点「移除该组」/ 批量勾选移除 / 一键移除失效 / 清空 / 另存挑选集。
 * INT-1694 二次口径：任务视图（默认，任务在第一级）下再分 用例/设备/结果类型 子模式，
 * 用例子模式渲染用例层组织控件（复用阶段 2 的 usePickOrg + PickCaseOrgControls）。
 */
import { ListChecks, Save, Smartphone, Tag, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import { usePickOrg } from '@/application/tasks/cherry-pick/use-pick-org'
import type { CartTaskSubView } from '@/domain/lib/cherry-pick-tree'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/confirm-dialog'
import type { CartTreeBranch, CartTreeLeaf } from '@/domain/models/cherryPick'
import { CartTree } from '@/features/tasks/cherry-pick/components/cart-tree'
import {
  CartViewSwitcher,
  type CartView,
} from '@/features/tasks/cherry-pick/components/cart-view-switcher'
import { PickCaseOrgControls } from '@/features/tasks/cherry-pick/components/pick-case-org-list'
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
  /** §4.2 视图切换（任务视图默认；切换视图/子模式不改变勾选/失效标记） */
  const [view, setView] = useState<CartView>('task')
  /** 任务视图子模式（任务下再分 用例/设备/结果类型，INT-1694 B 组） */
  const [taskSubView, setTaskSubView] = useState<CartTaskSubView>('case')
  /** 用例层组织（用例视图顶层 + 任务视图用例子模式共享，复用阶段 2 usePickOrg） */
  const { org, subView, setOrg, setSubView } = usePickOrg()

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
            {/* §4.2 视图切换器（任务视图默认 + 用例/设备/结果类型；购物车抽屉与复核步骤共用） */}
            <div className='mb-3 flex flex-wrap items-center gap-2'>
              <CartViewSwitcher view={view} onChange={setView} className='w-max' />
              {/* 任务视图：任务下再分三子模式（INT-1694 B 组） */}
              {view === 'task' && (
                <div className='bg-muted/60 flex items-center gap-0.5 rounded-lg p-0.5'>
                  <Button
                    variant={taskSubView === 'case' ? 'default' : 'ghost'}
                    size='sm'
                    className='h-6 gap-1 px-2 text-xs'
                    onClick={() => setTaskSubView('case')}
                  >
                    <ListChecks aria-hidden='true' className='size-3.5' />
                    用例
                  </Button>
                  <Button
                    variant={taskSubView === 'device' ? 'default' : 'ghost'}
                    size='sm'
                    className='h-6 gap-1 px-2 text-xs'
                    onClick={() => setTaskSubView('device')}
                  >
                    <Smartphone aria-hidden='true' className='size-3.5' />
                    设备
                  </Button>
                  <Button
                    variant={taskSubView === 'resultType' ? 'default' : 'ghost'}
                    size='sm'
                    className='h-6 gap-1 px-2 text-xs'
                    onClick={() => setTaskSubView('resultType')}
                  >
                    <Tag aria-hidden='true' className='size-3.5' />
                    结果类型
                  </Button>
                </div>
              )}
            </div>
            {/* 任务视图用例子模式：用例层组织控件（分组/标签 + 平铺/交叉，作用到每个任务节点内） */}
            {view === 'task' && taskSubView === 'case' && (
              <div className='mb-2'>
                <PickCaseOrgControls
                  org={org}
                  subView={subView}
                  onOrgChange={setOrg}
                  onSubViewChange={setSubView}
                />
              </div>
            )}
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
              view={view}
              taskSubView={taskSubView}
              org={org}
              subView={subView}
              onOrgChange={setOrg}
              onSubViewChange={setSubView}
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
