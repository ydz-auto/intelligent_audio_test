/**
 * 报告展示页计数口径（INT-2378，接 INT-2368 设备页 / INT-2330 错误态口径）：
 * 列表首载中、或首载失败、且没有任何可展示数据时，计数未知——
 * 页头徽标与工具栏计数同显占位「共 — 个已发布报告」，避免把「尚未加载完 / 取不到」
 * 显示成「共 0 个已发布报告」而被误读为「没有已发布报告」。
 *
 * 口径与设备页 `isDeviceListUnknown` 一致：刷新时保留的上一份数据（placeholderData）
 * 不算未知，按上一份真实计数展示；真·空列表仍显示 0。
 */
export interface ShowcaseListState {
  isLoading: boolean
  isError: boolean
  hasData: boolean
}

/** 计数是否未知（首载加载中 / 首载失败且无数据） */
export function isShowcaseCountUnknown(state: ShowcaseListState): boolean {
  return !state.hasData && (state.isLoading || state.isError)
}

/** 计数文案：未知显示「共 — 个已发布报告」，取到数据按真实总数展示 */
export function getShowcaseCountText(state: ShowcaseListState, total: number): string {
  return `共 ${isShowcaseCountUnknown(state) ? '—' : total} 个已发布报告`
}
