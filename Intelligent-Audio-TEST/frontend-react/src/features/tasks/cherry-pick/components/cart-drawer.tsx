/**
 * 购物车抽屉（18_挑选合并交互重设计.md §4.4/§7.1，INT-600）。
 * Sheet sm:max-w-lg 全局入口（导航栏角标落位 INT-344，本卡页内同步）；
 * 内容复用 CartPanel（购物车树 + 移除矩阵全量）。
 * 底部：继续挑选（关抽屉回挑选）｜主钮「去复核（{n}）」（外部跳向导 Step 3）。
 */
import { ShoppingCart } from 'lucide-react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { CartPanel } from '@/features/tasks/cherry-pick/components/cart-panel'

export function CartDrawer({
  open,
  onOpenChange,
  onGoReview,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 去复核（外部打开向导 Step 3；未开向导时先开向导跳复核） */
  onGoReview?: () => void
}) {
  const { hasPermission } = usePermissions()
  const total = usePickCartStore((s) => s.total)
  // §8：algo_engineer（仅 task:read）抽屉只读，增删钮隐藏；不授额外权限
  const canWrite = hasPermission('task:cherry_pick')

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side='right' className='w-3/4 sm:max-w-lg'>
        <SheetHeader>
          <SheetTitle className='flex items-center gap-2'>
            <ShoppingCart aria-hidden='true' className='size-4' />
            我的购物车
            {total > 0 && <span className='font-mono text-xs'>{total}</span>}
          </SheetTitle>
        </SheetHeader>

        <CartPanel
          readOnly={!canWrite}
          onGoContinuePick={() => onOpenChange(false)}
          onGoReview={
            canWrite
              ? () => {
                  onOpenChange(false)
                  onGoReview?.()
                }
              : undefined
          }
        />
      </SheetContent>
    </Sheet>
  )
}
