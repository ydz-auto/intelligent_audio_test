/**
 * 维度 requiresAudio 合并单测（INT-1843）。
 * `/evaluation/dimensions` 列表端点不下发 requires_audio，标记表取自
 * `/evaluation/dimensions/options`（真实库 63 条里 30 条为 true，全部是主维度）。
 */
import { describe, expect, it } from 'vitest'

import {
  buildAlgorithmAssociationIndex,
  mergeDimensionAssociations,
  mergeDimensionRequiresAudio,
} from '@/application/evaluation/use-dimensions'
import type { Dimension } from '@/domain/models/evaluationDimension'

const dim = (over: Partial<Dimension>): Dimension => ({
  id: 1,
  name: '识别准确率',
  ...over,
})

describe('mergeDimensionRequiresAudio', () => {
  it('按 id 合并标记表：命中 true 的维度 requiresAudio=true', () => {
    const merged = mergeDimensionRequiresAudio(
      [dim({ id: 121, name: '拒识成功数量' }), dim({ id: 1 })],
      new Map([[121, true]])
    )
    expect(merged[0].requiresAudio).toBe(true)
    // 标记表未命中且维度自身无标记 → false（不出音乐图标）
    expect(merged[1].requiresAudio).toBe(false)
  })

  it('标记表显式 false 覆盖维度自身标记', () => {
    const merged = mergeDimensionRequiresAudio(
      [dim({ id: 124, requiresAudio: true })],
      new Map([[124, false]])
    )
    expect(merged[0].requiresAudio).toBe(false)
  })

  it('标记表未命中时保留维度自身 requiresAudio', () => {
    const merged = mergeDimensionRequiresAudio(
      [dim({ id: 72, requiresAudio: true })],
      new Map([[121, true]])
    )
    expect(merged[0].requiresAudio).toBe(true)
  })

  it('维度 id 为字符串时按数值对齐标记表', () => {
    const merged = mergeDimensionRequiresAudio(
      [dim({ id: '1192', name: '环境理解准确率' })],
      new Map([[1192, true]])
    )
    expect(merged[0].requiresAudio).toBe(true)
  })

  it('标记表不可用（options 端点失败）时原样返回列表', () => {
    const dimensions = [dim({ id: 121 })]
    expect(mergeDimensionRequiresAudio(dimensions, undefined)).toBe(dimensions)
  })
})

/**
 * 关联算法索引（INT-2252）：列表端点恒下发 associated_algorithms: []，
 * 页面按算法从 GET /algorithm/dimensions/{algo} 批量补关联后再筛选 / 出列。
 */
describe('buildAlgorithmAssociationIndex', () => {
  it('按维度 id 聚合多算法的关联项（含 isDefault / weight）', () => {
    const index = buildAlgorithmAssociationIndex([
      { dimensionId: 121, algorithmType: 'voice_llm', isDefault: true, weight: 2 },
      { dimensionId: 121, algorithmType: 'asr-v3', isDefault: false, weight: 1 },
      { dimensionId: 122, algorithmType: 'voice_llm', isDefault: false, weight: 1 },
    ])
    expect(index.get(121)).toEqual([
      { algorithmType: 'voice_llm', isDefault: true, weight: 2 },
      { algorithmType: 'asr-v3', isDefault: false, weight: 1 },
    ])
    expect(index.get(122)).toEqual([
      { algorithmType: 'voice_llm', isDefault: false, weight: 1 },
    ])
    expect(index.get(999)).toBeUndefined()
  })

  it('无关联时返回空索引', () => {
    expect(buildAlgorithmAssociationIndex([]).size).toBe(0)
  })
})

describe('mergeDimensionAssociations', () => {
  it('按 id 把关联算法合并进维度行（字符串 id 也能对齐）', () => {
    const merged = mergeDimensionAssociations(
      [dim({ id: '121', name: '环境理解准确率' }), dim({ id: 1 })],
      new Map([
        [121, [{ algorithmType: 'voice_llm', isDefault: false, weight: 1 }]],
      ])
    )
    expect(merged[0].associatedAlgorithms).toEqual([
      { algorithmType: 'voice_llm', isDefault: false, weight: 1 },
    ])
    // 索引未命中的行原样保留（列表端点下发的是 []，不编造关联）
    expect(merged[1].associatedAlgorithms ?? []).toEqual([])
  })

  it('索引为空（未取到 / 取失败）时原样返回列表，不改变行对象', () => {
    const dimensions = [dim({ id: 121 })]
    expect(mergeDimensionAssociations(dimensions, new Map())).toBe(dimensions)
  })
})
