/**
 * 报告收藏/回收站演示 store（infrastructure 层；红线④：mock 交互态）。
 * 出图先：mock 列表为常量，收藏/软删/恢复/彻底删除经本 store 覆盖，
 * 使收藏工具条与回收站模式的交互可演示；TODO(API 接线): 移除本 store，
 * 改 favoritesPort（POST/DELETE /reports/{id}/favorite、restore、purge）+ 列表失效重拉。
 */
import { create } from 'zustand'

type ReportsUiState = {
  /** 额外收藏的报告 id 集合 */
  favoriteIds: Set<number>
  /** 已收藏但被取消的报告 id 集合 */
  unfavoritedIds: Set<number>
  /** 软删除（回收站）报告 id 集合 */
  deletedIds: Set<number>
  /** 已彻底删除报告 id 集合 */
  purgedIds: Set<number>
  toggleFavorite: (id: number) => void
  softDelete: (ids: number[]) => void
  restore: (ids: number[]) => void
  purge: (ids: number[]) => void
}

export const useReportsUiStore = create<ReportsUiState>((set) => ({
  favoriteIds: new Set(),
  unfavoritedIds: new Set(),
  deletedIds: new Set(),
  purgedIds: new Set(),
  toggleFavorite: (id) =>
    set((state) => {
      const favoriteIds = new Set(state.favoriteIds)
      const unfavoritedIds = new Set(state.unfavoritedIds)
      if (favoriteIds.has(id)) {
        favoriteIds.delete(id)
        unfavoritedIds.add(id)
      } else {
        favoriteIds.add(id)
        unfavoritedIds.delete(id)
      }
      return { favoriteIds, unfavoritedIds }
    }),
  softDelete: (ids) =>
    set((state) => ({
      deletedIds: new Set([...state.deletedIds, ...ids]),
    })),
  restore: (ids) =>
    set((state) => {
      const deletedIds = new Set(state.deletedIds)
      for (const id of ids) deletedIds.delete(id)
      return { deletedIds }
    }),
  purge: (ids) =>
    set((state) => ({
      purgedIds: new Set([...state.purgedIds, ...ids]),
      deletedIds: new Set([...state.deletedIds].filter((id) => !ids.includes(id))),
    })),
}))

/** 读取演示态覆盖后的收藏/删除标记（fetchReportList 消费） */
export function resolveReportUiFlags(
  id: number,
  baseFavorite?: boolean
): { isFavorite: boolean; deleted: boolean } {
  const state = useReportsUiStore.getState()
  if (state.purgedIds.has(id)) return { isFavorite: false, deleted: true }
  if (state.deletedIds.has(id)) return { isFavorite: false, deleted: true }
  const favorited = state.favoriteIds.has(id)
  const unfavorited = state.unfavoritedIds.has(id)
  return {
    isFavorite: favorited ? true : unfavorited ? false : (baseFavorite ?? false),
    deleted: false,
  }
}
