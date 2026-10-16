/**
 * 数字域校准点集校验/提交纯函数测试（features/spl-mapping/lib/calibration）。
 * 覆盖 validatePoint / detectDuplicateIndexes / countValidCalibrationRows /
 * buildCalibrationPayload（P2 审计回归：无效/重复/空行不混入提交 payload）。
 */
import { describe, expect, it } from 'vitest'

import {
  buildCalibrationPayload,
  countValidCalibrationRows,
  detectDuplicateIndexes,
  validatePoint,
  type CalibrationPointDraft,
} from '@/features/spl-mapping/lib/calibration'

function makePoints(...rows: Partial<CalibrationPointDraft>[]): CalibrationPointDraft[] {
  return rows.map((row) => ({
    targetSpl: '',
    gainLinear: '',
    rmsDbfs: '',
    ...row,
  }))
}

describe('validatePoint（§6.10 行级校验）', () => {
  it('合法点（目标 65、增益 1）无错误', () => {
    expect(validatePoint({ targetSpl: '65', gainLinear: '1', rmsDbfs: '-50' }, 0.001, 10.0)).toEqual({})
  })

  it('目标越 0~120 → 「范围 0~120」', () => {
    expect(validatePoint({ targetSpl: '999', gainLinear: '1', rmsDbfs: '' }, 0.001, 10.0).targetSpl)
      .toBe('范围 0~120')
  })

  it('目标空 → 「请输入目标 SPL」', () => {
    expect(validatePoint({ targetSpl: '', gainLinear: '1', rmsDbfs: '' }, 0.001, 10.0).targetSpl)
      .toBe('请输入目标 SPL')
  })

  it('增益非正/越限幅 → 「请输入正数增益」/「限幅 …」', () => {
    expect(validatePoint({ targetSpl: '65', gainLinear: '0', rmsDbfs: '' }, 0.001, 10.0).gainLinear)
      .toBe('请输入正数增益')
    expect(validatePoint({ targetSpl: '65', gainLinear: '100', rmsDbfs: '' }, 0.001, 10.0).gainLinear)
      .toBe('限幅 0.001~10.0')
  })
})

describe('detectDuplicateIndexes（§6.10 重复 x 拦截）', () => {
  it("'65' 与 '65.0' 数值相等 → 均判重（P3-1 修复）", () => {
    const points = makePoints(
      { targetSpl: '65', gainLinear: '1' },
      { targetSpl: '65.0', gainLinear: '1.5' },
      { targetSpl: '75', gainLinear: '2' },
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
      { targetSpl: '65', gainLinear: '1' },
      { targetSpl: '999', gainLinear: '1' },
      { targetSpl: '', gainLinear: '' },
    )
    const errors = points.map((p) => validatePoint(p, 0.001, 10.0))
    const dup = detectDuplicateIndexes(points)
    expect(countValidCalibrationRows(points, errors, dup)).toBe(1)
  })
})

describe('buildCalibrationPayload（§6.10 提交 payload；P2 回归）', () => {
  it('无效/重复/空行不混入提交，空 RMS 转 null（重复行两端均判重排除）', () => {
    const points = makePoints(
      { targetSpl: '65', gainLinear: '1.0', rmsDbfs: '-50' },
      { targetSpl: '999', gainLinear: '1', rmsDbfs: '' }, // 越界 → 排除
      { targetSpl: '65.0', gainLinear: '1.5', rmsDbfs: '' }, // 与行 1 数值重复 → 排除
      { targetSpl: '', gainLinear: '', rmsDbfs: '' }, // 空行 → 排除
      { targetSpl: '75', gainLinear: '2', rmsDbfs: '' }, // 有效，RMS 空 → null
    )
    const errors = points.map((p) => validatePoint(p, 0.001, 10.0))
    const dup = detectDuplicateIndexes(points)
    const payload = buildCalibrationPayload(points, errors, dup)
    expect(payload).toEqual([
      { targetSpl: 75, gainLinear: 2, rmsDbfs: null },
    ])
  })

  it('全无效 → 空 payload（提交钮已 disabled，payload 兜底为空）', () => {
    const points = makePoints({ targetSpl: '999', gainLinear: '1' }, { targetSpl: '', gainLinear: '' })
    const errors = points.map((p) => validatePoint(p, 0.001, 10.0))
    const dup = detectDuplicateIndexes(points)
    expect(buildCalibrationPayload(points, errors, dup)).toEqual([])
  })
})
