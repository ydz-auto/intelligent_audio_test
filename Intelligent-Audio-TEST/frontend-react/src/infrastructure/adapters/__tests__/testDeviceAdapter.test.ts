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
  it('将五态状态机值归一为 domain 枚举（在线/连接中/错误等）', () => {
    expect(toDeviceFiveState('online')).toBe('online')
    expect(toDeviceFiveState('connecting')).toBe('connecting')
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

  it('camelCase 字段一一映射 snake_case DTO（字段命名契约 §10.1）', () => {
    const device = testDeviceFromDto(BASE_DTO)
    expect(device.serialNumber).toBe(BASE_DTO.serial_number)
    expect(device.systemVersion).toBe(BASE_DTO.system_version)
    expect(device.supportedAlgorithms).toEqual(BASE_DTO.supported_algorithms)
    expect(device.needsPromptAudio).toBe(BASE_DTO.needs_prompt_audio)
    expect(device.lastOnlineAt).toBe(BASE_DTO.last_online_at)
  })

  it('未绑定实验室/未占用时返回 null/false（INT-487 未绑定口径）', () => {
    const device = testDeviceFromDto({ ...BASE_DTO, lab_id: null, lab_name: null, occupied: false })
    expect(device.labId).toBeNull()
    expect(device.labName).toBeNull()
    expect(device.occupied).toBe(false)
  })
})
