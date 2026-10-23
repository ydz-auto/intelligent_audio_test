import { describe, expect, it } from 'vitest'

import {
  calibrationDataFromDto,
  calibrationPointFromDto,
} from '@/infrastructure/adapters/splAdapter'
import type { CalibrationPointDto } from '@/infrastructure/dto/spl.dto'

describe('calibrationPointFromDto', () => {
  it('后端模拟校准写入键 gain → gainOffset，并按 §6.7 口径推导其余三列（INT-1503）', () => {
    const point = calibrationPointFromDto({ spl: 40, gain: 1 })
    expect(point).toEqual({
      spl: 40,
      gainOffset: 1,
      digitalGain: 1,
      baseLevel: -30,
      finalLevel: -29,
    })
  })

  it('gain 上限点：100 dB 增益 → 最终电平 70 dBFS', () => {
    expect(calibrationPointFromDto({ spl: 130, gain: 100 }).finalLevel).toBe(70)
  })

  it('前端表单写入键 gainOffset 优先于 gain', () => {
    const point = calibrationPointFromDto({
      spl: 65,
      gainOffset: -10,
      gain: 0,
    })
    expect(point.gainOffset).toBe(-10)
    expect(point.finalLevel).toBe(-40)
  })

  it('显式提供的 digitalGain/baseLevel/finalLevel 不被推导覆盖', () => {
    const dto: CalibrationPointDto = {
      spl: 65,
      gainOffset: 0,
      digitalGain: 3,
      baseLevel: -24,
      finalLevel: -12,
    }
    expect(calibrationPointFromDto(dto)).toMatchObject({
      digitalGain: 3,
      baseLevel: -24,
      finalLevel: -12,
    })
  })

  it('无增益键的点保持空值（不伪造电平）', () => {
    expect(calibrationPointFromDto({ spl: 40 })).toEqual({
      spl: 40,
      gainOffset: null,
      digitalGain: null,
      baseLevel: null,
      finalLevel: null,
    })
  })

  it('小数增益的浮点尾差收敛到 0.01 dB', () => {
    expect(calibrationPointFromDto({ spl: 40, gain: 0.1 }).finalLevel).toBe(-29.9)
  })
})

describe('calibrationDataFromDto', () => {
  it('后端 calibration_data.points（gain 键）整组可用，曲线过滤后不丢点', () => {
    const data = calibrationDataFromDto({
      points: [
        { spl: 40, gain: 1 },
        { spl: 50, gain: 10 },
      ],
    })
    expect(data?.points.map((point) => point.gainOffset)).toEqual([1, 10])
    expect(
      data?.points.filter((point) => point.spl != null && point.gainOffset != null)
    ).toHaveLength(2)
  })

  it('null 校准数据 → null', () => {
    expect(calibrationDataFromDto(null)).toBeNull()
  })
})
