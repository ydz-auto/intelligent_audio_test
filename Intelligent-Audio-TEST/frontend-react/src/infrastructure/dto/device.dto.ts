/**
 * 设备 DTO（infrastructure/dto 层——snake_case 唯一出现层；10_测试执行.md §9）。
 * 形态对照 api_gateway/schemas/device.py DeviceItem 实测逐字段。
 * INT-2641：/test-devices 实测已返回 lab_id/lab_name（网关装饰），实验室 facet 由此接线。
 */

export type DeviceTypeDto = 'physical' | 'http_api' | 'websocket_api'

/** GET /test-devices 列表项（device.py DeviceItem） */
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
  /** 所属实验室 ID（未挂实验室为 null） */
  lab_id: number | null
  /** 所属实验室名称（网关装饰字段） */
  lab_name: string | null
}
