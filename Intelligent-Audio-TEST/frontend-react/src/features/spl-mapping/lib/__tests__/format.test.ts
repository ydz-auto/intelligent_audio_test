/**
 * 声压级映射展示格式化纯函数测试（features/spl-mapping/lib/format）。
 * 覆盖 gainToDb / formatReferenceBase / formatGainClamp / formatDistance / formatTargetSpl /
 * formatTestFrequency 的主要成功路径与边界（§3.14 文案断言稳定）。
 */
import { describe, expect, it } from 'vitest'

import {
  formatDistance,
  formatGainClamp,
  formatReferenceBase,
  formatTargetSpl,
  formatTestFrequency,
  gainToDb,
} from '@/features/spl-mapping/lib/format'

describe('gainToDb（§4.3 20log10）', () => {
  it('线性增益 1.0 → 0.0 dB', () => {
    expect(gainToDb(1.0)).toBe('0.0 dB')
  })

  it('线性增益 10 → 20.0 dB', () => {
    expect(gainToDb(10)).toBe('20.0 dB')
  })

  it('非正数/非有限/空值回 "-"', () => {
    expect(gainToDb(0)).toBe('-')
    expect(gainToDb(-1)).toBe('-')
    expect(gainToDb(Number.NaN)).toBe('-')
    expect(gainToDb(null)).toBe('-')
    expect(gainToDb(undefined)).toBe('-')
  })
})

describe('formatReferenceBase（§4.3）', () => {
  it('双值 → "65 dB / 1.0"', () => {
    expect(formatReferenceBase(65, 1.0)).toBe('65 dB / 1.0')
  })

  it('单值缺省占位 "-"，双空回 "—"', () => {
    expect(formatReferenceBase(65, null)).toBe('65 dB / -')
    expect(formatReferenceBase(null, null)).toBe('—')
  })
})

describe('formatGainClamp（§4.3）', () => {
  it('双值 → "0.001 ~ 10.0"', () => {
    expect(formatGainClamp(0.001, 10.0)).toBe('0.001 ~ 10.0')
  })

  it('双空回 "—"', () => {
    expect(formatGainClamp(null, null)).toBe('—')
  })
})

describe('物理域列格式（§4.2）', () => {
  it('测量距离 → "{n} 米"，空回 "—"', () => {
    expect(formatDistance(1)).toBe('1 米')
    expect(formatDistance(null)).toBe('—')
  })

  it('目标声压级 → "{n} dB"，空回 "—"', () => {
    expect(formatTargetSpl(65)).toBe('65 dB')
    expect(formatTargetSpl(null)).toBe('—')
  })

  it('测试频率 → "{n} Hz"，空回 "—"', () => {
    expect(formatTestFrequency(1000)).toBe('1000 Hz')
    expect(formatTestFrequency(null)).toBe('—')
  })
})
