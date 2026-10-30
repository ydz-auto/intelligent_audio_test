/**
 * 算法详情弹窗只读渲染单测。
 * - INT-1558：后端 associated_dimensions 只回 dimension_id，名称须由前端 dimensions 解析；
 *   解析不到的（已删除 / 接口未返回）兜底 `已删除维度 #<id>`，不得空白。
 * - INT-1644：评估参数映射按目标维度分组（组头主/子徽章 + 计数 + 折叠）；
 *   评估维度关联按主/子维度成组相邻，已删除维度排末尾按 id 升序。
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { AlgorithmDefinition, ParamMapping } from '@/domain/models/algorithmConfig'
import type { Dimension } from '@/domain/models/evaluationDimension'
import {
  AlgorithmDetailDialog,
  groupEvaluationMappings,
  orderAssociatedDimensions,
  resolveDimensionName,
  resolveMappingDimensionName,
} from '@/features/algorithm-config/components/modals/algorithm-detail-dialog'

const dimensions = [
  { id: 134, name: '打断时延' },
  { id: '135', name: '响应准确率' },
] as Dimension[]

/** 主/子层级维度（INT-1644） */
const hierarchyDimensions = [
  { id: 1, name: '识别准确率', dimensionType: 'main', parentDimensionId: null },
  { id: 2, name: '响应延迟', dimensionType: 'main', parentDimensionId: null },
  { id: 11, name: '字准率', dimensionType: 'sub', parentDimensionId: 1 },
  { id: 12, name: '句准率', dimensionType: 'sub', parentDimensionId: 1 },
] as Dimension[]

function mapping(
  id: number,
  dimensionId: number | null,
  dimensionName: string | null = null
): ParamMapping {
  return {
    id,
    source: 'case',
    sourceDirection: 'output',
    sourceParam: `p${id}`,
    paramName: `参数${id}`,
    dimensionId,
    dimensionName,
    targetParam: `t${id}`,
    targetParamName: null,
    transformType: 'none',
  }
}

function makeAlgorithm(
  associatedDimensions: AlgorithmDefinition['associatedDimensions'],
  evaluation: ParamMapping[] = []
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
    caseParams: [],
    referenceParams: [],
    mappings: { device: [], evaluation },
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

describe('resolveMappingDimensionName（INT-1644 已删除维度口径）', () => {
  it('维度全量命中时用维度名', () => {
    expect(resolveMappingDimensionName(dimensions, 134, '存量旧名')).toBe('打断时延')
  })

  it('维度全量查不到时兜底已删除维度 #id，不采信行内存量名称', () => {
    expect(resolveMappingDimensionName(dimensions, 999, '存量旧名')).toBe('已删除维度 #999')
  })

  it('维度列表尚未加载时退回行内 dimensionName', () => {
    expect(resolveMappingDimensionName([], 999, '存量旧名')).toBe('存量旧名')
  })

  it('无维度时返回空串（渲染为 —）', () => {
    expect(resolveMappingDimensionName(dimensions, null)).toBe('')
  })
})

describe('groupEvaluationMappings', () => {
  it('按 dimensionId 分组，组序按维度名中文排序，空维度归未指定维度', () => {
    const groups = groupEvaluationMappings(
      [
        mapping(1, 11),
        mapping(2, 2),
        mapping(3, null),
        mapping(4, 1),
        mapping(5, 11),
      ],
      hierarchyDimensions
    )
    expect(groups.map((group) => group.name)).toEqual([
      '识别准确率',
      '未指定维度',
      '响应延迟',
      '字准率',
    ])
    expect(groups.find((group) => group.name === '字准率')?.rows).toHaveLength(2)
    expect(groups.find((group) => group.name === '未指定维度')?.key).toBe('__none__')
  })

  it('dimensions 查不到的维度归已删除维度 #id 组', () => {
    const groups = groupEvaluationMappings([mapping(1, 999, '旧维度名')], hierarchyDimensions)
    expect(groups).toHaveLength(1)
    expect(groups[0].name).toBe('已删除维度 #999')
    expect(groups[0].dimension).toBeUndefined()
  })
})

describe('orderAssociatedDimensions', () => {
  it('主维度在前、子维度紧随其后，已删除维度排末尾按 id 升序', () => {
    const ordered = orderAssociatedDimensions(
      [
        { id: 1, dimensionId: 11, dimensionName: '', weight: 1, isDefault: false },
        { id: 2, dimensionId: 999, dimensionName: '', weight: 1, isDefault: false },
        { id: 3, dimensionId: 2, dimensionName: '', weight: 1, isDefault: false },
        { id: 4, dimensionId: 12, dimensionName: '', weight: 1, isDefault: false },
        { id: 5, dimensionId: 1, dimensionName: '', weight: 1, isDefault: true },
        { id: 6, dimensionId: 134, dimensionName: '', weight: 1, isDefault: false },
      ],
      [...hierarchyDimensions, ...dimensions]
    )
    expect(ordered.map((item) => item.relation.dimensionId)).toEqual([
      2, 1, 11, 12, 134, 999,
    ])
  })

  it('父维度未关联到本算法的子维度不丢行', () => {
    const ordered = orderAssociatedDimensions(
      [
        { id: 1, dimensionId: 11, dimensionName: '', weight: 1, isDefault: false },
        { id: 2, dimensionId: 2, dimensionName: '', weight: 1, isDefault: false },
      ],
      hierarchyDimensions
    )
    expect(ordered.map((item) => item.relation.dimensionId)).toEqual([2, 11])
  })
})

describe('AlgorithmDetailDialog 评估维度关联', () => {
  it('维度列都不为空，子维度带「子」徽章与父维度名，已删除维度兜底', () => {
    render(
      <AlgorithmDetailDialog
        open
        onOpenChange={() => undefined}
        algorithm={makeAlgorithm([
          { id: 1, dimensionId: 134, dimensionName: '', weight: 1, isDefault: true },
          { id: 2, dimensionId: 999, dimensionName: '', weight: 1, isDefault: false },
          { id: 3, dimensionId: 11, dimensionName: '', weight: 0.5, isDefault: false },
        ])}
        dimensions={[...dimensions, ...hierarchyDimensions]}
      />
    )

    const heading = screen.getByText('评估维度关联')
    const table = heading.parentElement?.querySelector('table')
    expect(table).not.toBeNull()
    const cells = [...(table as HTMLTableElement).querySelectorAll('tbody tr')].map(
      (row) => row.querySelector('td')?.textContent
    )
    expect(cells).toEqual([
      '打断时延主',
      '字准率子（识别准确率）',
      '已删除维度 #999',
    ])
  })
})

describe('AlgorithmDetailDialog 评估参数分组视图', () => {
  it('按评估维度分组，组头带主/子徽章、父维度名与组内行数，可折叠', async () => {
    const user = userEvent.setup()
    render(
      <AlgorithmDetailDialog
        open
        onOpenChange={() => undefined}
        algorithm={makeAlgorithm(
          [],
          [mapping(1, 11), mapping(2, 11), mapping(3, 1), mapping(4, null)]
        )}
        dimensions={hierarchyDimensions}
      />
    )

    await user.click(screen.getByRole('tab', { name: /评估参数（4）/ }))
    const panel = screen
      .getAllByRole('tabpanel')
      .find((node) => node.textContent?.includes('未指定维度')) as HTMLElement
    expect(panel).toBeDefined()
    const headers = [...panel.querySelectorAll('tbody tr button')].map((button) =>
      button.textContent
    )
    expect(headers).toEqual([
      '识别准确率主1 条',
      '未指定维度1 条',
      '字准率子（识别准确率）2 条',
    ])

    // 默认展开：各组的行都在
    expect(within(panel).getByText('参数1')).not.toBeNull()
    expect(within(panel).getByText('参数3')).not.toBeNull()
    expect(within(panel).getByText('参数4')).not.toBeNull()

    // 折叠「识别准确率」组：只有该组的行消失，其它组不受影响
    const header = [...panel.querySelectorAll('tbody tr button')].find((button) =>
      button.textContent?.startsWith('识别准确率')
    ) as HTMLButtonElement
    await user.click(header)
    expect(within(panel).queryByText('参数3')).toBeNull()
    expect(within(panel).getByText('参数1')).not.toBeNull()
    expect(within(panel).getByText('参数4')).not.toBeNull()
  })

  it('无评估参数映射时显示空态文案', async () => {
    const user = userEvent.setup()
    render(
      <AlgorithmDetailDialog
        open
        onOpenChange={() => undefined}
        algorithm={makeAlgorithm([])}
        dimensions={hierarchyDimensions}
      />
    )
    await user.click(screen.getByRole('tab', { name: /评估参数（0）/ }))
    expect(screen.getByText('无评估参数映射')).not.toBeNull()
  })
})
