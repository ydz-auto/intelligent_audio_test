/**
 * 设备域导入导出领域模型（domain 层；INT-1624 接 INT-816 三资源端点）。
 * 三页签（测试设备 / 播放设备 / 测试 API）共用一套模型，资源差异只在
 * infrastructure 的端点映射里体现（见 api/devicesApi.ts RESOURCE_ENDPOINTS）。
 * 契约来源：api_gateway/schemas/common.py ResourceExportQuery / ResourceImportResult。
 */

/** 导出格式（ResourceExportQuery.format ∈ {json, excel}） */
export type DeviceExportFormat = 'json' | 'excel'

/**
 * 导出范围（页面设计 §4.5.2）。
 * 映射：all → 不带 ids；selected → 当前选中 ids；filtered → 当前筛选后 ids。
 */
export type DeviceExportRange = 'all' | 'selected' | 'filtered'

/** 导入计数报告（ResourceImportResult；errors 为「第N行: 原因」中文串） */
export interface DeviceImportResult {
  importedCount: number
  updatedCount: number
  skippedCount: number
  errors: string[]
}

/** 导入结果摘要文案（弹窗与 toast 同口径，§4.5.1「成功导入 x 个，更新 y 个，跳过 z 个」） */
export function formatImportSummary(result: DeviceImportResult): string {
  return `成功导入 ${result.importedCount} 个，更新 ${result.updatedCount} 个，跳过 ${result.skippedCount} 个`
}
