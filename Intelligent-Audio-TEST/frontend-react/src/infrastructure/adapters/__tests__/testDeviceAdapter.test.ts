import { describe, expect, it } from 'vitest'

import { testDeviceFromDto, toDeviceFiveState } from '@/infrastructure/adapters/testDeviceAdapter'
import type { TestDeviceItemDto } from '@/infrastructure/dto/test-device.dto'

const BASE_DTO: TestDeviceItemDto = {
  id: 1,
  name: '音箱-客厅位',
  model: '旗舰 S1',
  description: '客厅远场位',
  type: 'physical',
  system: 'harmony',
  system_version: '3.2.1',
  app_name: '音乐播放器',
  app_version: '2.4.0',
  location: null,
  max_audio_duration: 300,
  needs_prompt_audio: true,
  connection_type: 'usb',
  keywords: null,
  serial_number: 'SN-A001-8821',
  ip: '192.168.1.21',
  status: 'online',
  last_online_at: '2026-10-17T08:40:00',
  created_at: '2026-09-01T09:00:00',
  updated_at: '2026-10-17T08:40:00',
  driver_name: 'HDC 驱动 3.1',
  supported_algorithms: ['asr_streaming', 'wakeword_detect'],
  lab_id: 1,
  lab_name: '声学实验室 A',
  occupied: true,
}

describe('testDeviceFromDto', () => {
  it('将五态状态机值归一为 domain 枚举（五态全覆盖）', () => {
    expect(toDeviceFiveState('online')).toBe('online')
    expect(toDeviceFiveState('offline')).toBe('offline')
    expect(toDeviceFiveState('connecting')).toBe('connecting')
    expect(toDeviceFiveState('disconnecting')).toBe('disconnecting')
    expect(toDeviceFiveState('error')).toBe('error')
    expect(toDeviceFiveState('unknown-value')).toBeNull()
    expect(toDeviceFiveState(null)).toBeNull()
  })

  it('透传 INT-487 lab_id/lab_name 与 occupied 占用态，接线不返工', () => {
    const device = testDeviceFromDto(BASE_DTO)
    expect(device.labId).toBe(1)
    expect(device.labName).toBe('声学实验室 A')
    expect(device.occupied).toBe(true)
    expect(device.status).toBe('online')
  })

  it('camelCase 字段一一映射 snake_case DTO（字段命名契约 §10.1 全覆盖）', () => {
    const device = testDeviceFromDto(BASE_DTO)
    expect(device.id).toBe(BASE_DTO.id)
    expect(device.name).toBe(BASE_DTO.name)
    expect(device.model).toBe(BASE_DTO.model)
    expect(device.description).toBe(BASE_DTO.description)
    expect(device.type).toBe(BASE_DTO.type)
    expect(device.system).toBe(BASE_DTO.system)
    expect(device.systemVersion).toBe(BASE_DTO.system_version)
    expect(device.appName).toBe(BASE_DTO.app_name)
    expect(device.appVersion).toBe(BASE_DTO.app_version)
    expect(device.connectionType).toBe(BASE_DTO.connection_type)
    expect(device.serialNumber).toBe(BASE_DTO.serial_number)
    expect(device.ip).toBe(BASE_DTO.ip)
    expect(device.driverName).toBe(BASE_DTO.driver_name)
    expect(device.supportedAlgorithms).toEqual(BASE_DTO.supported_algorithms)
    expect(device.needsPromptAudio).toBe(BASE_DTO.needs_prompt_audio)
    expect(device.maxAudioDuration).toBe(BASE_DTO.max_audio_duration)
    expect(device.location).toBe(BASE_DTO.location)
    expect(device.keywords).toBe(BASE_DTO.keywords)
    expect(device.lastOnlineAt).toBe(BASE_DTO.last_online_at)
    expect(device.createdAt).toBe(BASE_DTO.created_at)
    expect(device.updatedAt).toBe(BASE_DTO.updated_at)
  })

  it('§6.2 高级设置字段（apiLevel/remark/tags/customAttributes/priority）缺省回退', () => {
    const device = testDeviceFromDto(BASE_DTO)
    expect(device.apiLevel).toBeNull()
    expect(device.remark).toBeNull()
    expect(device.tags).toBeNull()
    expect(device.customAttributes).toBeNull()
    expect(device.priority).toBeNull()
  })

  it('未绑定实验室/未占用时返回 null/false（INT-487 未绑定口径）', () => {
    const device = testDeviceFromDto({ ...BASE_DTO, lab_id: null, lab_name: null, occupied: false })
    expect(device.labId).toBeNull()
    expect(device.labName).toBeNull()
    expect(device.occupied).toBe(false)
  })
})
