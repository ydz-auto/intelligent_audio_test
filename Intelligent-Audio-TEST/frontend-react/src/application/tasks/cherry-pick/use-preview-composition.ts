/**
 * 预览步骤组成装配（application/tasks/cherry-pick，18_挑选合并交互重设计.md §5.2 ⑤/⑧，INT-2003）。
 * 两个既有数据源，零新增 query：购物车快照 `usePickCartStore.groups`（条目）+ `useCherryPickPreview()`
 * （摘要 / 失效 id 集，已随 cart revision 失效，见 use-cherry-pick-preview.ts）。
 * 预览不取 `GET /tasks/cherry-picks/{id}/source`——那是下单之后的容器端点，此时容器还不存在。
 */
import { useMemo } from 'react'

import { useCherryPickPreview } from '@/application/tasks/cherry-pick/use-cherry-pick-preview'
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import {
  groupCompositionEntries,
  summarizeComposition,
  toPreviewCompositionEntries,
} from '@/domain/lib/container-composition'

export function usePreviewComposition() {
  const cartGroups = usePickCartStore((s) => s.groups)
  const cartLoading = usePickCartStore((s) => s.loading)
  const preview = useCherryPickPreview()

  const entries = useMemo(
    () =>
      toPreviewCompositionEntries(
        cartGroups.flatMap((g) => g.entries),
        preview.data
      ),
    [cartGroups, preview.data]
  )

  const groups = useMemo(() => groupCompositionEntries(entries), [entries])
  const summary = useMemo(() => summarizeComposition(entries), [entries])

  return {
    entries,
    groups,
    summary,
    /** 预览摘要（未返回 / 失败为 undefined：徽章与主钮都不做假数字） */
    preview: preview.data,
    /** cart / preview 任一 pending → 骨架 + 主钮禁用（§5.2 ⑦） */
    loading: cartLoading || preview.isLoading,
    /** 非 400 的预览失败（400 空购物车已由 infrastructure 兜底成空预览） */
    error: preview.error,
    retry: () => void preview.refetch(),
  }
}
