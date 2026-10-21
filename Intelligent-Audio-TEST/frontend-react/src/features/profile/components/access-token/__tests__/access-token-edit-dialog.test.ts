/**
 * Access Token 编辑对话框 expiry 映射单测（features/profile/components/access-token，
 * INT-1153 代码审计 P2-1 修复）：
 * - expiryPresetFromTimestamp：0=永不过期；仅命中 30/90/180/365 整档取对应预设；
 *   非整档剩余（5/25/45/366 天）与已过期一律回落 'custom'——不误导显示，也未改
 *   有效时间保存时不再把 expires_at 静默延长为「现在 + 整档」；
 * - resolveEditExpiry：never→0；custom 保留原值；预设→now + 整档天数。
 */
import { describe, expect, it } from 'vitest'

import { datetimeLocalString } from '../access-token-create-dialog'
import {
  expiryPresetFromTimestamp,
  resolveEditExpiry,
} from '../access-token-edit-dialog'

const DAY_MS = 24 * 60 * 60 * 1000
const NOW = new Date('2026-10-21T08:00:00+08:00').getTime()

describe('expiryPresetFromTimestamp', () => {
  it('0=永不过期 → never', () => {
    expect(expiryPresetFromTimestamp(0, NOW)).toBe('never')
  })

  it('命中 30/90/180/365 整档 → 对应预设', () => {
    expect(expiryPresetFromTimestamp(NOW + 30 * DAY_MS, NOW)).toBe('30d')
    expect(expiryPresetFromTimestamp(NOW + 90 * DAY_MS, NOW)).toBe('90d')
    expect(expiryPresetFromTimestamp(NOW + 180 * DAY_MS, NOW)).toBe('180d')
    expect(expiryPresetFromTimestamp(NOW + 365 * DAY_MS, NOW)).toBe('1y')
  })

  it('非整档剩余天数（5/25/45/366）→ custom，不向上取档', () => {
    expect(expiryPresetFromTimestamp(NOW + 5 * DAY_MS, NOW)).toBe('custom')
    expect(expiryPresetFromTimestamp(NOW + 25 * DAY_MS, NOW)).toBe('custom')
    expect(expiryPresetFromTimestamp(NOW + 45 * DAY_MS, NOW)).toBe('custom')
    expect(expiryPresetFromTimestamp(NOW + 366 * DAY_MS, NOW)).toBe('custom')
  })

  it('已过期（剩余 ≤0 天）→ custom，不被「复活」', () => {
    expect(expiryPresetFromTimestamp(NOW - DAY_MS, NOW)).toBe('custom')
    expect(expiryPresetFromTimestamp(NOW - 30 * DAY_MS, NOW)).toBe('custom')
  })
})

describe('resolveEditExpiry', () => {
  it('never → 0（永不过期）', () => {
    expect(resolveEditExpiry({ expiry: 'never', customExpiresAt: undefined }, NOW)).toBe(0)
  })

  it('custom 保留原值（编辑框未改动时与原 expires_at 一致）', () => {
    const original = datetimeLocalString(new Date(NOW + 5 * DAY_MS))
    expect(resolveEditExpiry({ expiry: 'custom', customExpiresAt: original }, NOW)).toBe(
      original
    )
  })

  it('custom 无值 → 0', () => {
    expect(resolveEditExpiry({ expiry: 'custom', customExpiresAt: undefined }, NOW)).toBe(0)
  })

  it('预设档 → 现在 + 整档天数', () => {
    expect(resolveEditExpiry({ expiry: '30d', customExpiresAt: undefined }, NOW)).toBe(
      datetimeLocalString(new Date(NOW + 30 * DAY_MS))
    )
    expect(resolveEditExpiry({ expiry: '1y', customExpiresAt: undefined }, NOW)).toBe(
      datetimeLocalString(new Date(NOW + 365 * DAY_MS))
    )
  })
})

describe('编辑仅改名未动有效时间（P2-1 复现回归）', () => {
  it('剩余 5 天的 token：预设回落 custom，提交值仍是 5 天后而非 now+30d', () => {
    const expiresAt = NOW + 5 * DAY_MS
    const preset = expiryPresetFromTimestamp(expiresAt, NOW)
    expect(preset).toBe('custom')
    const originalLocal = datetimeLocalString(new Date(expiresAt))
    const submitted = resolveEditExpiry({ expiry: preset, customExpiresAt: originalLocal }, NOW)
    expect(submitted).toBe(originalLocal)
  })
})
