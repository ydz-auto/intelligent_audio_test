/**
 * 算法详情弹窗「评估维度关联」维度名列单测（INT-1558）。
 * 后端 associated_dimensions 只回 dimension_id，名称须由前端 dimensions 解析；
 * 解析不到的（已删除 / 接口未返回）兜底 `已删除维度 #<id>`，不得空白。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { AlgorithmDefinition } from '@/domain/models/algorithmConfig'
import type { Dimension } from '@/domain/models/evaluationDimension'
import {
  AlgorithmDetailDialog,
  resolveDimensionName,
} from '@/features/algorithm-config/components/modals/algorithm-detail-dialog'

const dimensions = [
  { id: 134, name: '打断时延' },
  { id: '135', name: '响应准确率' },
] as Dimension[]

function makeAlgorithm(
  associatedDimensions: AlgorithmDefinition['associatedDimensions']
): AlgorithmDefinition {
  return {
    id: 1,
    type: 'voice_llm',
    name: '小艺语音大模型',
    groupId: null,
    groupName: null,
    category: null,
    description: null,
    status: 'online',
    icon: null,
    displayOrder: 0,
    deviceParams: [],
    apiParams: [],
    caseParams: [],
    referenceParams: [],
    mappings: { device: [], api: [], evaluation: [] },
    associatedDimensions,
    caseCount: null,
    createdAt: '2026-10-01T00:00:00Z',
    updatedAt: '2026-10-01T00:00:00Z',
  }
}

describe('resolveDimensionName', () => {
  it('后端回名称时优先使用', () => {
    expect(resolveDimensionName(dimensions, 134, '后端名称')).toBe('后端名称')
  })

  it('按 dimensionId 从维度全量解析名称（数字/字符串 id 均可）', () => {
    expect(resolveDimensionName(dimensions, 134)).toBe('打断时延')
    expect(resolveDimensionName(dimensions, 135)).toBe('响应准确率')
  })

  it('查不到的维度兜底已删除维度 #id', () => {
    expect(resolveDimensionName(dimensions, 999)).toBe('已删除维度 #999')
  })

  it('无 dimensionId 时显示 —', () => {
    expect(resolveDimensionName(dimensions, null)).toBe('—')
  })
})

describe('AlgorithmDetailDialog 评估维度关联', () => {
  it('92 条关联的维度列都不为空（可解析显示名称，缺失显示兜底）', () => {
    render(
      <AlgorithmDetailDialog
        open
        onOpenChange={() => undefined}
        algorithm={makeAlgorithm([
          { id: 1, dimensionId: 134, dimensionName: '', weight: 1, isDefault: true },
          { id: 2, dimensionId: 999, dimensionName: '', weight: 1, isDefault: false },
        ])}
        dimensions={dimensions}
      />
    )

    const heading = screen.getByText('评估维度关联')
    const table = heading.parentElement?.querySelector('table')
    expect(table).not.toBeNull()
    const cells = [...(table as HTMLTableElement).querySelectorAll('tbody tr')].map(
      (row) => row.querySelector('td')?.textContent
    )
    expect(cells).toEqual(['打断时延', '已删除维度 #999'])
  })
})
