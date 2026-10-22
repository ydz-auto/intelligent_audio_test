/**
 * INT-1387：评估维度 scoreUnit ↔ score_unit 双向映射契约测试。
 * 读方向 toDimension：后端回显 score_unit → 前端 scoreUnit（此前漏映射，
 * 导致编辑弹窗「分数单位」回显恒空、不动该字段保存会把库值清空）。
 * 写方向 toDimensionDto：scoreUnit → 请求体 score_unit。
 */
import { describe, it, expect } from 'vitest'
import { toDimension, toDimensionDto } from '../evaluationAdapter'
import type { DimensionItemDto } from '../../dto/evaluationDto'
import type { Dimension } from '../../../domain/model/dimension'

const RAW_DTO = {
  id: 1,
  name: '测试维度',
  dimension_type: 'main',
  score_unit: '分',
} as unknown as DimensionItemDto

describe('evaluationAdapter scoreUnit', () => {
  it('toDimension：后端 score_unit → 前端 scoreUnit（缺失回落空串）', () => {
    const dim = toDimension(RAW_DTO)
    expect(dim.scoreUnit).toBe('分')
    // 缺失 score_unit 时回落空串，避免编辑弹窗 undefined 导致回显空 + 保存 null 覆盖库值
    expect(toDimension({ id: 2, name: '无单位维度' } as unknown as DimensionItemDto).scoreUnit).toBe('')
  })

  it('toDimensionDto：前端 scoreUnit → 请求体 score_unit', () => {
    const domain: Dimension = {
      id: 1,
      name: '测试维度',
      dimensionType: 'main',
      scoreUnit: '分',
    }
    const dto = toDimensionDto(domain)
    expect(dto.score_unit).toBe('分')
  })
})
