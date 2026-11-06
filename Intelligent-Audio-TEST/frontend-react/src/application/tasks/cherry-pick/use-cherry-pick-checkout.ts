/**
 * 下单 mutation hook（application/tasks/cherry-pick，18_挑选合并交互重设计.md §7.2/§5.3，INT-600）。
 * POST /cart/checkout 三出口 merge/reexecute/reevaluate；成功出清购物车 + invalidate 容器列表。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import type { CheckoutPayload } from '@/infrastructure/api/cherry-pick-api'
import { checkoutCart } from '@/infrastructure/api/cherry-pick-api'

export function useCherryPickCheckout() {
  const queryClient = useQueryClient()
  const refreshCart = usePickCartStore((s) => s.refreshCart)

  return useMutation({
    mutationKey: ['cherry-pick', 'checkout'],
    mutationFn: (payload: CheckoutPayload) => checkoutCart(payload),
    onSuccess: async () => {
      // 出清后回写镜像（失效/重复条目保留）+ 页签计数刷新（§6.3 同步点）
      await refreshCart()
      await queryClient.invalidateQueries({ queryKey: ['tasks', 'cherry-picks'] })
    },
  })
}
