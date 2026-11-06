/**
 * 播放设备 DTO（infrastructure/dto 层——snake_case 唯一出现层；16_设备域.md §3.5）。
 * 形态对照 api_gateway/schemas/playback.py PlaybackDeviceItem 实测逐字段 +
 * 播放设备表列口径（设备管理功能设计文档.md:280-286：设备类型/支持的格式/支持的通道数）。
 * INT-487 待后端：lab_id 未暴露（§11-25）、occupied 未暴露（§11-26）；
 * INT-381 补口：supported_formats/supported_channels 后端 schema 未覆盖（§11-23）——mock 先行。
 */
import type { DeviceFiveStateDto } from './test-device.dto'

/** GET /playback-devices 列表项（playback.py PlaybackDeviceItem + INT-381/487 补口） */
export interface PlaybackDeviceItemDto {
  id: number
  name: string
  model: string | null
  device_type: string | null
  sample_rate: number | null
  channel_index: number | null
  device_unique_id: string | null
  description: string | null
  status: DeviceFiveStateDto | null
  current_spl_mapping_id: number | null
  created_at: string | null
  updated_at: string | null
  /** INT-487：待后端 DTO 暴露 lab_id（§11-25） */
  lab_id: number | null
  lab_name: string | null
  /** INT-487：待后端暴露 occupied/testing（§11-26） */
  occupied: boolean
  /** INT-381 补口（§11-23） */
  supported_formats: string[] | null
  supported_channels: number | null
}
