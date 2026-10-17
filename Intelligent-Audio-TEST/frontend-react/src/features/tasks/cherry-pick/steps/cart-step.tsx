/**
 * 购物车步骤（Step 2/4，18_挑选合并交互重设计.md §4/§5.1，INT-600）。
 * 购物车树（管理态）+ 移除矩阵全量；可继续挑选/去复核。
 */
import { CartPanel } from '@/features/tasks/cherry-pick/components/cart-panel'

export function CartStep({
  onGoPick,
  onGoReview,
}: {
  onGoPick: () => void
  onGoReview: () => void
}) {
  return (
    <CartPanel
      onGoContinuePick={onGoPick}
      continueLabel='继续挑选'
      onGoReview={onGoReview}
      reviewLabel='去复核'
    />
  )
}
