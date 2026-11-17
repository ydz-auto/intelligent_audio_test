/**
 * 设备类型三值归一（INT-2640）：后端 type 值域与前端三值枚举对齐的唯一入口。
 * 三值之外（历史 phone / 扫描脏值）一律 null，展示层统一「未知」，不外露英文枚举。
 */
import { describe, expect, it } from 'vitest'

import {
  DEVICE_TYPE_META,
  DEVICE_TYPE_UNKNOWN_LABEL,
  DEVICE_TYPE_VALUES,
  deviceTypeLabel,
  toDeviceType,
} from '@/domain/models/device'

describe('toDeviceType', () => {
  it('三值原样返回', () => {
    expect(toDeviceType('physical')).toBe('physical')
    expect(toDeviceType('http_api')).toBe('http_api')
    expect(toDeviceType('websocket_api')).toBe('websocket_api')
  })

  it('历史 phone / 其它脏值 / 空值统一归为 null', () => {
    expect(toDeviceType('phone')).toBeNull()
    expect(toDeviceType('tablet')).toBeNull()
    expect(toDeviceType('')).toBeNull()
    expect(toDeviceType(null)).toBeNull()
    expect(toDeviceType(undefined)).toBeNull()
  })

  it('白名单与徽章元数据同源（三值一一对应）', () => {
    expect([...DEVICE_TYPE_VALUES]).toEqual(Object.keys(DEVICE_TYPE_META))
  })
})

describe('deviceTypeLabel', () => {
  it('三值取中文文案', () => {
    expect(deviceTypeLabel('physical')).toBe('真机')
    expect(deviceTypeLabel('http_api')).toBe('HTTP API')
    expect(deviceTypeLabel('websocket_api')).toBe('Realtime WS')
  })

  it('null / undefined 统一「未知」', () => {
    expect(DEVICE_TYPE_UNKNOWN_LABEL).toBe('未知')
    expect(deviceTypeLabel(null)).toBe('未知')
    expect(deviceTypeLabel(undefined)).toBe('未知')
  })
})
