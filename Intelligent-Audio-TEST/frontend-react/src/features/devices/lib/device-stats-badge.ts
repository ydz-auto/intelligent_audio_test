/**
 * 设备页头统计口径（INT-2368，接 INT-2330 错误态口径）：
 * 列表首载中、或首载失败、且没有任何可展示数据时，统计值未知——
 * 徽标显示占位「在线 —/共 —」、分页不渲染，避免把「尚未加载完」显示成
 * 「在线 0/共 0」「共 0 条」而被误读为「没有设备」。
 */
export interface DeviceListState {
  isLoading: boolean
  isError: boolean
  hasRows: boolean
}

/** 统计口径是否未知（加载中/加载失败且无旧数据） */
export function isDeviceListUnknown(state: DeviceListState): boolean {
  return !state.hasRows && (state.isLoading || state.isError)
}

/** 页头徽标文案：未知显示「在线 —/共 —」，取到数据按当前页签口径展示 */
export function getDeviceStatsBadgeText(
  state: DeviceListState,
  stats: { online: number; total: number }
): string {
  if (isDeviceListUnknown(state)) return '在线 —/共 —'
  return `在线 ${stats.online}/共 ${stats.total}`
}
