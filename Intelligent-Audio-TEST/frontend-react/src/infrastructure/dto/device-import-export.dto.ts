/**
 * 设备域导入导出 DTO（infrastructure/dto 层——snake_case 唯一出现层；INT-1624 接 INT-816）。
 * 契约：api_gateway/schemas/common.py ResourceImportResult
 * {imported_count, updated_count, skipped_count, errors}。
 * 导出文件流（JSON / XLSX）不走统一信封，见 api/devicesApi.ts exportDeviceResource。
 */

/** POST /{resource}/import 的 data 体（ResourceImportResult） */
export interface DeviceImportResultDto {
  imported_count: number
  updated_count: number
  skipped_count: number
  /** 「第N行: 原因」中文串（后端逐行累计） */
  errors?: string[] | null
}
