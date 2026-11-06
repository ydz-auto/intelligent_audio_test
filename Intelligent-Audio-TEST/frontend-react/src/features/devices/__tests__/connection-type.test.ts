import { describe, expect, it } from 'vitest'

import { connectionTypeLabel } from '@/features/devices/lib/connection-type'

describe('connectionTypeLabel（INT-2187）', () => {
  it('usb / remote 归一为中文文案', () => {
    expect(connectionTypeLabel('usb')).toBe('USB连接')
    expect(connectionTypeLabel('remote')).toBe('远程连接')
  })

  it('null / undefined / 未知值返回 null（列表与详情显「—」，不误判为 USB）', () => {
    expect(connectionTypeLabel(null)).toBeNull()
    expect(connectionTypeLabel(undefined)).toBeNull()
    expect(connectionTypeLabel('')).toBeNull()
    expect(connectionTypeLabel('bluetooth')).toBeNull()
  })
})
