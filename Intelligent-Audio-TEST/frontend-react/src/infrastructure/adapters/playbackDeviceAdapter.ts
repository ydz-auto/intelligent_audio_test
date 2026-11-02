/**
 * 播放设备 DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §10）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 * device_type 归一（dry/noise）、current_spl_mapping_id 仅透传；映射名由
 * `attachSplMappingNames` 用 GET /spl 数据（与关联弹窗同源）按 id 关联（INT-2347）。
 */
import type { PlaybackDevice, PlaybackDeviceType } from '@/domain/models/playbackDevice'
import type { SplMapping } from '@/domain/models/splMapping'
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

/**
 * 回填播放设备当前声压映射名（INT-2347；列表/详情展示用）。
 * GET /playback-devices 只回 `current_spl_mapping_id`、不回名称，故用同一份 GET /spl
 * 数据（与关联弹窗同源）在应用层按 id 关联；后端契约不变。
 * mappings 未就绪（未下发/未返回）或无匹配项时 name 保持 null，由展示层回退。
 */
export function attachSplMappingNames(
  devices: PlaybackDevice[],
  mappings: SplMapping[] | undefined
): PlaybackDevice[] {
  if (!mappings || mappings.length === 0) return devices
  const nameById = new Map(mappings.map((mapping) => [mapping.id, mapping.name]))
  let changed = false
  const enriched = devices.map((device) => {
    const name =
      device.currentSplMappingId == null
        ? null
        : (nameById.get(device.currentSplMappingId) ?? null)
    if (name === device.currentSplMappingName) return device
    changed = true
    return { ...device, currentSplMappingName: name }
  })
  return changed ? enriched : devices
}
