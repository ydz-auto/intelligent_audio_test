/**
 * 播放设备真实 API（infrastructure/api 层；INT-710 批量设置播放设备/噪声接线）。
 * GET /playback-devices（playback_bp.py:11 列表）+ POST /playback-devices/scan（:42 扫描）。
 * 对照 api_gateway/schemas/playback.py PlaybackDeviceItem 实测字段（snake_case → camelCase
 * 收敛在本层）；device_type 枚举 dry/noise 直接映射 domain PlaybackDeviceType。
 */
import { apiClient } from './client'
import type { PlaybackDevice, PlaybackDeviceType } from '@/domain/models/playbackDevice'

interface PlaybackDeviceItemDto {
  id: number
  name: string
  model: string | null
  description: string | null
  device_type: string | null
  sample_rate: number | null
  channel_index: number | null
  device_unique_id: string | null
  status: string | null
  current_spl_mapping_id: number | null
  created_at: string | null
  updated_at: string | null
}

function toPlaybackDevice(dto: PlaybackDeviceItemDto): PlaybackDevice {
  const rawType = dto.device_type
  const deviceType: PlaybackDeviceType | null =
    rawType === 'dry' || rawType === 'noise' ? rawType : null
  return {
    id: dto.id,
    name: dto.name,
    model: dto.model ?? null,
    description: dto.description ?? null,
    deviceType,
    sampleRate: dto.sample_rate ?? null,
    channelIndex: dto.channel_index ?? null,
    deviceUniqueId: dto.device_unique_id ?? null,
    status: (dto.status ?? null) as PlaybackDevice['status'],
    currentSplMappingId: dto.current_spl_mapping_id ?? null,
    currentSplMappingName: null,
    labId: null,
    labName: null,
    occupied: false,
    supportedFormats: null,
    supportedChannels: null,
    createdAt: dto.created_at ?? null,
    updatedAt: dto.updated_at ?? null,
  }
}

/** 播放设备列表（GET /playback-devices；device_type/keyword 可选过滤） */
export async function fetchRealPlaybackDevices(): Promise<PlaybackDevice[]> {
  const dto = await apiClient.get<{ items?: PlaybackDeviceItemDto[] }>(
    '/playback-devices',
    { params: { per_page: 200 } }
  )
  return (dto?.items ?? []).map(toPlaybackDevice)
}

/** 扫描可用播放设备（POST /playback-devices/scan；扫描到的未注册通道并入列表） */
export async function scanRealPlaybackDevices(): Promise<PlaybackDevice[]> {
  const dto = await apiClient.post<{ items?: PlaybackDeviceItemDto[] }>(
    '/playback-devices/scan'
  )
  return (dto?.items ?? []).map(toPlaybackDevice)
}
