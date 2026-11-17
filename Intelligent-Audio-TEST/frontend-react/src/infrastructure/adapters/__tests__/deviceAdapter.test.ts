import { describe, expect, it } from 'vitest'

import { toDeviceType } from '@/domain/models/device'
import { deviceFromDto, toDeviceStatus } from '@/infrastructure/adapters/deviceAdapter'
import type { DeviceItemDto } from '@/infrastructure/dto/device.dto'

const BASE_DTO: DeviceItemDto = {
  id: 9,
  name: 'pura90',
  model: 'Harmony Device',
  description: null,
  type: 'physical',
  system: 'harmony',
  system_version: '1.0.0',
  serial_number: '5SM0125701000448',
  ip: null,
  status: 'online',
  last_online_at: '2026-11-02T20:03:59.679438',
  supported_algorithms: ['voice_llm'],
  connection_type: 'usb',
  lab_id: 1,
  lab_name: 'LAB-A',
}

describe('deviceFromDto', () => {
  it('camelCase 字段一一映射 snake_case DTO', () => {
    const device = deviceFromDto(BASE_DTO)
    expect(device).toEqual({
      id: 9,
      name: 'pura90',
      model: 'Harmony Device',
      description: null,
      type: 'physical',
      system: 'harmony',
      systemVersion: '1.0.0',
      serialNumber: '5SM0125701000448',
      ip: null,
      status: 'online',
      lastOnlineAt: '2026-11-02T20:03:59.679438',
      supportedAlgorithms: ['voice_llm'],
      connectionType: 'usb',
      labId: 1,
      labName: 'LAB-A',
    })
  })

  it('INT-2641：透传真实 lab_id/lab_name，实验室 facet 按此绑定过滤', () => {
    const device = deviceFromDto(BASE_DTO)
    expect(device.labId).toBe(1)
    expect(device.labName).toBe('LAB-A')

    const unbound = deviceFromDto({ ...BASE_DTO, lab_id: null, lab_name: null })
    expect(unbound.labId).toBeNull()
    expect(unbound.labName).toBeNull()
  })

  it('状态 / 类型归一：未知值不冒充枚举', () => {
    expect(toDeviceStatus('online')).toBe('online')
    expect(toDeviceStatus('offline')).toBe('offline')
    expect(toDeviceStatus('connecting')).toBe('offline')
    expect(toDeviceStatus(null)).toBeNull()
    expect(toDeviceType('http_api')).toBe('http_api')
    expect(toDeviceType('phone')).toBeNull()
    expect(toDeviceType(null)).toBeNull()
  })
})
