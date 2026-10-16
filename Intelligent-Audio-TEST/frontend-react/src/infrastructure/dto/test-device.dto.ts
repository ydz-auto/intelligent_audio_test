/**
 * 测试设备 DTO（infrastructure/dto 层——snake_case 唯一出现层；16_设备域.md §3.4）。
 * 形态对照 api_gateway/schemas/device.py DeviceItem 实测逐字段。
 * INT-487 待后端：`lab_id`/`lab_name` 后端 DTO 未暴露（§11-25）、`occupied` 占用状态字段未暴露
 * （§11-26）——mock 先行承载本地瞬时态，字段落地后接线不返工。
 */

/** 设备五态（§3.4；「测试中」占用态不落此枚举） */
export type DeviceFiveStateDto =
  | 'online'
  | 'offline'
  | 'connecting'
  | 'disconnecting'
  | 'error'

/** GET /test-devices 列表项（device.py DeviceItem 全字段 + INT-487 补口） */
export interface TestDeviceItemDto {
  id: number
  name: string
  model: string | null
  description: string | null
  type: string | null
  system: string | null
  system_version: string | null
  app_name: string | null
  app_version: string | null
  location: string | null
  max_audio_duration: number | null
  needs_prompt_audio: boolean | null
  connection_type: string | null
  keywords: string | null
  serial_number: string | null
  ip: string | null
  status: DeviceFiveStateDto | null
  last_online_at: string | null
  created_at: string | null
  updated_at: string | null
  driver_name: string | null
  supported_algorithms: string[] | null
  /** INT-487：待后端 DTO 暴露 lab_id/lab_name（§11-25） */
  lab_id: number | null
  lab_name: string | null
  /** INT-487：待后端暴露 occupied/testing（§11-26），mock 本地瞬时态兜底 */
  occupied: boolean
}
