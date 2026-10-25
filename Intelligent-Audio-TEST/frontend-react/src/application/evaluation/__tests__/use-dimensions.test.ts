/**
 * 维度 requiresAudio 合并单测（INT-1843）。
 * `/evaluation/dimensions` 列表端点不下发 requires_audio，标记表取自
 * `/evaluation/dimensions/options`（真实库 63 条里 30 条为 true，全部是主维度）。
 */
import { describe, expect, it } from 'vitest'

import { mergeDimensionRequiresAudio } from '@/application/evaluation/use-dimensions'
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
