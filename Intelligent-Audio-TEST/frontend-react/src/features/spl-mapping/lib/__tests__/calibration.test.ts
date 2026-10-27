/**
 * 数字域校准点集校验/提交纯函数测试（features/spl-mapping/lib/calibration）。
 * INT-2081 口径：校准点主输入 = 目标 SPL + 实测 dBFS（必填 -120~0），线性增益只读推导
 * （10^((dBFS+30)/20)）不入参校验。覆盖 deriveGainLinear / validatePoint /
 * detectDuplicateIndexes / countValidCalibrationRows / buildCalibrationPayload。
 */
import { describe, expect, it } from 'vitest'

import {
  buildCalibrationPayload,
  countValidCalibrationRows,
  detectDuplicateIndexes,
  deriveGainLinear,
  generateCalibrationPointsByReference,
  validatePoint,
  type CalibrationPointDraft,
} from '@/features/spl-mapping/lib/calibration'

function makePoints(...rows: Partial<CalibrationPointDraft>[]): CalibrationPointDraft[] {
  return rows.map((row) => ({
    targetSpl: '',
    rmsDbfs: '',
    ...row,
  }))
}

describe('deriveGainLinear（INT-2081 增益推导）', () => {
  it('基准电平 -30 dBFS → 增益 1.0', () => {
    expect(deriveGainLinear('-30')).toBe(1)
  })

  it('-50 dBFS → 0.1（-20dB 偏移）', () => {
    expect(deriveGainLinear('-50')).toBeCloseTo(0.1, 12)
  })

  it('-40 dBFS → 10^(-0.5) ≈ 0.316', () => {
    expect(deriveGainLinear('-40')).toBeCloseTo(Math.pow(10, (-40 + 30) / 20), 12)
  })

  it('-10 dBFS → 10（+20dB 偏移）', () => {
    expect(deriveGainLinear('-10')).toBeCloseTo(10, 12)
  })

  it('空/非数值 → null', () => {
    expect(deriveGainLinear('')).toBeNull()
    expect(deriveGainLinear('abc')).toBeNull()
  })
})

describe('validatePoint（INT-2081 行级校验）', () => {
  it('合法点（目标 65、dBFS -50）无错误', () => {
    expect(validatePoint({ targetSpl: '65', rmsDbfs: '-50' })).toEqual({})
  })

  it('目标越 0~120 → 「范围 0~120」', () => {
    expect(validatePoint({ targetSpl: '999', rmsDbfs: '-50' }).targetSpl)
      .toBe('范围 0~120')
  })

  it('目标空 → 「请输入目标 SPL」', () => {
    expect(validatePoint({ targetSpl: '', rmsDbfs: '-50' }).targetSpl)
      .toBe('请输入目标 SPL')
  })

  it('dBFS 空/非数值 → 「请输入实测 dBFS」', () => {
    expect(validatePoint({ targetSpl: '65', rmsDbfs: '' }).rmsDbfs)
      .toBe('请输入实测 dBFS')
    expect(validatePoint({ targetSpl: '65', rmsDbfs: 'abc' }).rmsDbfs)
      .toBe('请输入实测 dBFS')
  })

  it('dBFS 越 -120~0 → 「范围 -120~0」', () => {
    expect(validatePoint({ targetSpl: '65', rmsDbfs: '5' }).rmsDbfs)
      .toBe('范围 -120~0')
    expect(validatePoint({ targetSpl: '65', rmsDbfs: '-200' }).rmsDbfs)
      .toBe('范围 -120~0')
  })
})

describe('detectDuplicateIndexes（§6.10 重复 x 拦截）', () => {
  it("'65' 与 '65.0' 数值相等 → 均判重（P3-1 修复）", () => {
    const points = makePoints(
      { targetSpl: '65', rmsDbfs: '-50' },
      { targetSpl: '65.0', rmsDbfs: '-40' },
      { targetSpl: '75', rmsDbfs: '-30' },
    )
    const dup = detectDuplicateIndexes(points)
    expect(dup.has(0)).toBe(true)
    expect(dup.has(1)).toBe(true)
    expect(dup.has(2)).toBe(false)
  })

  it('空/非数值目标不参与判重', () => {
    const points = makePoints({ targetSpl: '' }, { targetSpl: 'abc' }, { targetSpl: '65' })
    expect(detectDuplicateIndexes(points).size).toBe(0)
  })
})

describe('countValidCalibrationRows（提交钮门控）', () => {
  it('混合有效+越界+空行 → 只计有效行', () => {
    const points = makePoints(
      { targetSpl: '65', rmsDbfs: '-50' },
      { targetSpl: '999', rmsDbfs: '-40' },
      { targetSpl: '', rmsDbfs: '' },
    )
    const errors = points.map((p) => validatePoint(p))
    const dup = detectDuplicateIndexes(points)
    expect(countValidCalibrationRows(points, errors, dup)).toBe(1)
  })
})

describe('buildCalibrationPayload（INT-2081 提交 payload；P2 回归）', () => {
  it('有效行按 dBFS 推导增益提交', () => {
    const points = makePoints(
      { targetSpl: '45', rmsDbfs: '-60' },
      { targetSpl: '65', rmsDbfs: '-50' },
    )
    const errors = points.map((p) => validatePoint(p))
    const dup = detectDuplicateIndexes(points)
    const payload = buildCalibrationPayload(points, errors, dup)
    expect(payload).toEqual([
      { targetSpl: 45, gainLinear: Math.pow(10, (-60 + 30) / 20), rmsDbfs: -60 },
      { targetSpl: 65, gainLinear: Math.pow(10, (-50 + 30) / 20), rmsDbfs: -50 },
    ])
  })

  it('无效/重复/空行不混入提交，增益由 dBFS 推导（重复行两端均判重排除）', () => {
    const points = makePoints(
      { targetSpl: '65', rmsDbfs: '-50' },
      { targetSpl: '999', rmsDbfs: '-40' }, // 目标越界 → 排除
      { targetSpl: '65.0', rmsDbfs: '-30' }, // 与行 1 数值重复 → 两端均排除
      { targetSpl: '', rmsDbfs: '' }, // 空行 → 排除
      { targetSpl: '75', rmsDbfs: '-40' }, // 有效
    )
    const errors = points.map((p) => validatePoint(p))
    const dup = detectDuplicateIndexes(points)
    const payload = buildCalibrationPayload(points, errors, dup)
    expect(payload).toEqual([
      { targetSpl: 75, gainLinear: Math.pow(10, (-40 + 30) / 20), rmsDbfs: -40 },
    ])
  })

  it('全无效 → 空 payload（提交钮已 disabled，payload 兜底为空）', () => {
    const points = makePoints({ targetSpl: '999', rmsDbfs: '-40' }, { targetSpl: '', rmsDbfs: '' })
    const errors = points.map((p) => validatePoint(p))
    const dup = detectDuplicateIndexes(points)
    expect(buildCalibrationPayload(points, errors, dup)).toEqual([])
  })
})

describe('generateCalibrationPointsByReference（INT-2081 按参考生成）', () => {
  it('refSpl 65 / refGain 1.0 → 5 点，中心点 dBFS -30 且增益推导为 1', () => {
    const points = generateCalibrationPointsByReference(65, 1.0)
    expect(points).toHaveLength(5)
    expect(points[2]).toEqual({ targetSpl: '65', rmsDbfs: '-30.0' })
    expect(deriveGainLinear(points[2].rmsDbfs)).toBe(1)
  })

  it('相邻点间隔 10dB SPL，dBFS 随偏移 +20dB 增益变化', () => {
    const points = generateCalibrationPointsByReference(65, 1.0)
    const gains = points.map((p) => deriveGainLinear(p.rmsDbfs))
    expect(gains[0]).toBeCloseTo(0.1, 6) // offset -20 → 10^-1
    expect(gains[1]).toBeCloseTo(Math.pow(10, -0.5), 6)
    expect(gains[3]).toBeCloseTo(Math.pow(10, 0.5), 6)
    expect(gains[4]).toBeCloseTo(10, 6) // offset +20 → 10^1
  })
})
