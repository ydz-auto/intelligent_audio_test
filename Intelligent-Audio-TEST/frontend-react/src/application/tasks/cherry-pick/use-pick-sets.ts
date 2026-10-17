/**
 * 挑选集 hook（application/tasks/cherry-pick，18_挑选合并交互重设计.md §7.2，INT-600）。
 * 挑选集 list/save/restore/delete；数据源为 usePickCartStore.pickSets（单例镜像）。
 */
import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'

export function usePickSets() {
  const pickSets = usePickCartStore((s) => s.pickSets)
  const saveAsPickSet = usePickCartStore((s) => s.saveAsPickSet)
  const restorePickSet = usePickCartStore((s) => s.restorePickSet)
  const deletePickSet = usePickCartStore((s) => s.deletePickSet)

  return { pickSets, saveAsPickSet, restorePickSet, deletePickSet }
}
