/**
 * 播放设备适配器：声压映射名回填（INT-2347）。
 * 列表接口只回 current_spl_mapping_id，名称由 GET /spl 数据按 id 关联。
 */
import { describe, expect, it } from 'vitest'

import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { SplMapping } from '@/domain/models/splMapping'
import {
  attachSplMappingNames,
  playbackDeviceFromDto,
} from '@/infrastructure/adapters/playbackDeviceAdapter'
import type { PlaybackDeviceItemDto } from '@/infrastructure/dto/playback-device.dto'

const DTO: PlaybackDeviceItemDto = {
  id: 6,
  name: '设备正左侧（1m-90°）',
  model: 'Speakon 6',
  device_type: 'dry',
  sample_rate: 48_000,
  channel_index: 0,
  device_unique_id: 'spk-6',
  description: null,
  status: 'online',
  current_spl_mapping_id: 16,
  created_at: null,
  updated_at: null,
  lab_id: null,
  lab_name: null,
  occupied: false,
  supported_formats: null,
  supported_channels: null,
}

function mapping(id: number, name: string): SplMapping {
  return {
    id,
    name,
    description: null,
    deviceId: null,
    deviceName: null,
    deviceModel: null,
    deviceType: 'dry',
    distance: 1,
    targetSpl: 65,
    digitalGain: 0,
    calibrationStatus: 'calibrated',
    testFrequency: 1000,
    calibrationData: null,
    isCurrent: null,
    createdAt: null,
    updatedAt: null,
  }
}

function deviceWithSplId(id: number, splId: number | null): PlaybackDevice {
  return { ...playbackDeviceFromDto(DTO), id, currentSplMappingId: splId }
}

describe('attachSplMappingNames', () => {
  it('按 current_spl_mapping_id 回填名称', () => {
    const [enriched] = attachSplMappingNames(
      [deviceWithSplId(6, 16)],
      [mapping(16, '设备正左侧映射'), mapping(5, '其他映射')]
    )

    expect(enriched.currentSplMappingName).toBe('设备正左侧映射')
  })

  it('未关联（id 为空）不解析名称', () => {
    const [enriched] = attachSplMappingNames([deviceWithSplId(6, null)], [mapping(16, '设备正左侧映射')])

    expect(enriched.currentSplMappingName).toBeNull()
  })

  it('映射列表未就绪或 id 不在列表时保持 null（展示层回退）', () => {
    expect(
      attachSplMappingNames([deviceWithSplId(6, 16)], undefined)[0].currentSplMappingName
    ).toBeNull()
    expect(
      attachSplMappingNames([deviceWithSplId(6, 16)], [mapping(7, '别的映射')])[0]
        .currentSplMappingName
    ).toBeNull()
  })

  it('名称未变化时返回原数组引用（避免无谓重渲染）', () => {
    const devices = attachSplMappingNames([deviceWithSplId(6, 16)], [mapping(16, '设备正左侧映射')])
    const again = attachSplMappingNames(devices, [mapping(16, '设备正左侧映射')])

    expect(again).toBe(devices)
  })
})
