/**
 * 播放设备 DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §10）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 * device_type 归一（dry/noise）、current_spl_mapping_id 仅透传（映射名由应用层 refs 关联）。
 */
import type { PlaybackDevice, PlaybackDeviceType } from '@/domain/models/playbackDevice'
import type { PlaybackDeviceItemDto } from '@/infrastructure/dto/playback-device.dto'
import { toDeviceFiveState } from '@/infrastructure/adapters/testDeviceAdapter'

const PLAYBACK_TYPE_SET: ReadonlySet<string> = new Set(['dry', 'noise'])

export function toPlaybackDeviceType(type: string | null): PlaybackDeviceType | null {
  if (!type || !PLAYBACK_TYPE_SET.has(type)) return null
  return type as PlaybackDeviceType
}

export function playbackDeviceFromDto(dto: PlaybackDeviceItemDto): PlaybackDevice {
  return {
    id: dto.id,
    name: dto.name,
    model: dto.model,
    description: dto.description,
    deviceType: toPlaybackDeviceType(dto.device_type),
    sampleRate: dto.sample_rate,
    channelIndex: dto.channel_index,
    deviceUniqueId: dto.device_unique_id,
    status: toDeviceFiveState(dto.status),
    currentSplMappingId: dto.current_spl_mapping_id,
    currentSplMappingName: null,
    labId: dto.lab_id,
    labName: dto.lab_name,
    occupied: dto.occupied,
    supportedFormats: dto.supported_formats,
    supportedChannels: dto.supported_channels,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}
