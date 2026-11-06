/**
 * §6.6 评估维度分节搜索筛选测试（INT-723 返修 P2-2 + INT-1030 分组选择）：
 * 搜索「搜索评估维度...」按维度名过滤 + 无匹配空态；
 * 评估维度选择按 分组→主维度→子维度 展示（分类组头 + 主/子徽章）。
 * 照 V9.7.10 AlgorithmConfigModal.vue filteredDimensions 语义（按 availableDimensions 名称匹配）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'

import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import { DimensionsSection } from '../dimensions-section'

const DIMENSIONS: Dimension[] = [
  { id: 1, name: '识别准确率', dimensionType: 'main', parentDimensionId: null, categoryId: 1, associatedAlgorithms: [] },
  { id: 2, name: '响应延迟', dimensionType: 'main', parentDimensionId: null, categoryId: 1, associatedAlgorithms: [] },
  { id: 3, name: '噪声鲁棒性', dimensionType: 'main', parentDimensionId: null, categoryId: 1, associatedAlgorithms: [] },
  // 子维度（INT-1030 分组下拉：主维度下展示子维度）
  { id: 11, name: '字准率', dimensionType: 'sub', parentDimensionId: 1, categoryId: 1, associatedAlgorithms: [] },
]

const CATEGORIES: EvaluationCategory[] = [{ id: 1, name: '基础质量' }]

function buildValues(): AlgorithmFormValues {
  return {
    type: 'asr_v3',
    name: '语音识别',
    groupId: '1',
    displayOrder: 0,
    status: 'online',
    description: '',
    deviceParams: [],
    caseParams: [],
    referenceParams: [],
    mappings: { device: [], evaluation: [] },
    associatedDimensions: [
      { key: 'dim-1', dimensionId: '1', dimensionName: '识别准确率', weight: '0.5', isDefault: true },
      { key: 'dim-2', dimensionId: '2', dimensionName: '响应延迟', weight: '0.3', isDefault: false },
      { key: 'dim-3', dimensionId: '3', dimensionName: '噪声鲁棒性', weight: '0.2', isDefault: false },
    ],
  }
}

function Harness({ values = buildValues() }: { values?: AlgorithmFormValues }) {
  const form = useForm<AlgorithmFormValues>({ defaultValues: values })
  return (
    <DimensionsSection
      form={form}
      dimensions={DIMENSIONS}
      categories={CATEGORIES}
    />
  )
}

describe('DimensionsSection 评估维度搜索（§6.6）', () => {
  it('搜索输入 + 添加关联维度按钮渲染', () => {
    render(<Harness />)
    expect(screen.getByPlaceholderText('搜索评估维度...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '添加关联维度' })).toBeInTheDocument()
  })

  it('搜索关键词按维度名过滤行', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    // 三行初始都在（Select 触发钮显示维度名）
    expect(screen.getByText('识别准确率')).toBeInTheDocument()
    expect(screen.getByText('响应延迟')).toBeInTheDocument()
    expect(screen.getByText('噪声鲁棒性')).toBeInTheDocument()

    await user.type(screen.getByPlaceholderText('搜索评估维度...'), '准确率')
    expect(screen.getByText('识别准确率')).toBeInTheDocument()
    expect(screen.queryByText('响应延迟')).not.toBeInTheDocument()
    expect(screen.queryByText('噪声鲁棒性')).not.toBeInTheDocument()
  })

  it('无匹配 → 显示「未找到匹配评估维度」空态', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(screen.getByPlaceholderText('搜索评估维度...'), '不存在的维度xyz')
    expect(screen.getByText('未找到匹配评估维度，换个关键词试试')).toBeInTheDocument()
  })

  it('评估维度选择按 分组→主维度→子维度 展示（INT-1030）', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const triggers = screen.getAllByRole('combobox', { name: '评估维度' })
    await user.click(triggers[0])

    // 分类组头（基础质量）+ 主维度（识别准确率 主徽章）+ 其子维度（字准率 子徽章）
    expect(screen.getByText('基础质量')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /识别准确率/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /字准率/ })).toBeInTheDocument()
  })
})
