/**
 * 预览摘要 hook（application/tasks/cherry-pick，18_挑选合并交互重设计.md §7.2/§5.2，INT-600）。
 * POST /tasks/cherry-picks/preview 零新增接口；queryKey 随购物车 revision 失效。
 */
import { useQuery } from '@tanstack/react-query'

import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import { fetchCherryPickPreview } from '@/infrastructure/api/cherry-pick-api'

export function useCherryPickPreview() {
  const revision = usePickCartStore((s) => s.revision)
  return useQuery({
    queryKey: ['cherry-pick', 'preview', revision],
    queryFn: fetchCherryPickPreview,
    enabled: revision > 0,
  })
}
