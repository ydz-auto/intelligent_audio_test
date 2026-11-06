/**
 * 容器详情「再次挑选」入口（18_挑选合并功能交互重设计.md §5.5.5，INT-1717）。
 * 两个按钮，与报告区并列在容器详情：
 * - 「复用本次结果重新挑选」：取该容器引用的全部 `result_id`（source 端点，含失效条目）
 *   → `POST /tasks/cherry-picks/cart/items` 批量加购（后端幂等跳过已加购 / 失效）→ toast → 打开购物车抽屉；
 * - 「开始挑选」：打开挑选向导阶段 1（§3.8.2，不预筛任何来源任务），走 `/tasks/cherry-picks?wizard=pick`。
 * 购物车抽屉的「去预览」同样经 `?wizard=review` 把向导开到预览步骤（向导状态在任务页持有）。
 * 权限：`task:cherry_pick`（§8 注 5：加购 / 下单 / 购物车增删全链同码）。
 * 容器不复制、不新建任务——只是把同一批源结果重新交给购物车（§5.5.5）。
 */
import { useNavigate } from '@tanstack/react-router'
import { ListChecks, RefreshCcw } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import { Button } from '@/components/ui/button'
import { CartDrawer } from '@/features/tasks/cherry-pick/components/cart-drawer'
import { ApiError } from '@/infrastructure/api/api-error'

/** 加购结果 toast 文案（§5.5.5 / §9：失效优先于重复） */
export function describeAddToCartToast(
  addedCount: number,
  skippedCount: number,
  invalidCount: number
): string {
  if (invalidCount > 0) return `已加入购物车 ${addedCount} 条（${invalidCount} 条源结果已失效未加入）`
  if (skippedCount > 0 && addedCount > 0)
    return `已加入购物车 ${addedCount} 条（重复 ${skippedCount} 条已跳过）`
  if (addedCount > 0) return `已加入购物车 ${addedCount} 条`
  return '已加入购物车（重复条目已跳过）'
}

export function ContainerRePickActions({
  resultIds,
}: {
  /** 容器引用的全部源结果 id（source 端点，含失效条目——后端幂等跳过） */
  resultIds: number[]
}) {
  const navigate = useNavigate()
  const addEntries = usePickCartStore((s) => s.addEntries)
  const [pending, setPending] = useState(false)
  const [cartOpen, setCartOpen] = useState(false)

  const goWizard = (step: 'pick' | 'review') => {
    void navigate({
      to: '/tasks/$tab',
      params: { tab: 'cherry-picks' },
      search: { wizard: step } as never,
    })
  }

  /** 复用本次结果：整批源结果重新加购（不复制容器、不新建任务） */
  const reuseResults = async () => {
    if (resultIds.length === 0) return
    setPending(true)
    try {
      const { addedCount, skippedCount, invalidCount } = await addEntries(resultIds)
      toast.success(describeAddToCartToast(addedCount, skippedCount, invalidCount))
      setCartOpen(true)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.userMessage : '加入购物车失败')
    } finally {
      setPending(false)
    }
  }

  const noSource = resultIds.length === 0

  return (
    <>
      <Button
        size='sm'
        variant='outline'
        disabled={pending || noSource}
        title={
          noSource
            ? '该任务没有合并来源记录'
            : '把这批源结果重新放进购物车，可增删后再下单'
        }
        onClick={() => void reuseResults()}
        data-testid='container-repick-reuse'
      >
        <RefreshCcw aria-hidden='true' className='size-3.5' />
        复用本次结果重新挑选
      </Button>
      <Button
        size='sm'
        variant='ghost'
        onClick={() => goWizard('pick')}
        data-testid='container-repick-start'
      >
        <ListChecks aria-hidden='true' className='size-3.5' />
        开始挑选
      </Button>

      <CartDrawer
        open={cartOpen}
        onOpenChange={setCartOpen}
        onGoReview={() => goWizard('review')}
      />
    </>
  )
}
