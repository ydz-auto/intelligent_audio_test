/**
 * 播放设备领域模型（domain 层；16_设备域.md §3.5 落位）。
 * 形态对照 api_gateway/schemas/playback.py PlaybackDeviceItem 实测逐字段 +
 * 播放设备表列口径（设备管理功能设计文档.md:280-286：设备类型/支持的格式/支持的通道数）。
 * 五态状态机同 §3.4；「测试中」占用叠加态（INT-487）同 occupied 承载。
 * INT-381 补口：supportedFormats/supportedChannels 后端 schema 未覆盖（§11-23），mock 先行。
 */
import type { DeviceFiveState } from './testDevice'

export type PlaybackDeviceType = 'dry' | 'noise'

export const PLAYBACK_DEVICE_TYPE_META: Record<
  PlaybackDeviceType,
  { label: string }
> = {
  dry: { label: '干声设备' },
  noise: { label: '噪声设备' },
}

export interface PlaybackDevice {
  id: number
  name: string
  model: string | null
  description: string | null
  deviceType: PlaybackDeviceType | null
  sampleRate: number | null
  channelIndex: number | null
  deviceUniqueId: string | null
  status: DeviceFiveState | null
  /** 声压映射（current_spl_mapping_id → 映射名，§6.4 关联弹窗） */
  currentSplMappingId: number | null
  currentSplMappingName: string | null
  /** 所属实验室（INT-487：待后端 DTO 暴露 lab_id，mock 先行） */
  labId: number | null
  labName: string | null
  /** 「测试中」占用态（INT-487 本地瞬时态兜底） */
  occupied: boolean
  /** INT-381 补口（§11-23：后端 schema 未覆盖，mock 先行） */
  supportedFormats: string[] | null
  supportedChannels: number | null
  createdAt: string | null
  updatedAt: string | null
}
