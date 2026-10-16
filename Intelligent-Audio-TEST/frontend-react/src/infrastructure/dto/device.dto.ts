/**
 * 设备 DTO（infrastructure/dto 层——snake_case 唯一出现层；10_测试执行.md §9）。
 * 形态对照 api_gateway/schemas/device.py DeviceItem 实测逐字段。
 */

export type DeviceTypeDto = 'physical' | 'http_api' | 'websocket_api'

/** GET /devices 列表项（device.py DeviceItem） */
export interface DeviceItemDto {
  id: number
  name: string
  model: string | null
  description: string | null
  type: DeviceTypeDto | null
  system: string | null
  system_version: string | null
  serial_number: string | null
  ip: string | null
  status: string | null
  last_online_at: string | null
  supported_algorithms: string[] | null
  connection_type: string | null
}
