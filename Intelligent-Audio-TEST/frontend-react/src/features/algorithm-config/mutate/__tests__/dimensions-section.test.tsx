/**
 * §6.6 评估维度分节搜索筛选测试（INT-723 返修 P2-2）：
 * 搜索「搜索评估维度...」按维度名过滤 + 无匹配空态。
 * 照 V9.7.10 AlgorithmConfigModal.vue filteredDimensions 语义（按 availableDimensions 名称匹配）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'

import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import { DimensionsSection } from '../dimensions-section'

const DIMENSION_OPTIONS = [
  { id: 1, name: '识别准确率' },
  { id: 2, name: '响应延迟' },
  { id: 3, name: '噪声鲁棒性' },
]

function buildValues(): AlgorithmFormValues {
  return {
    type: 'asr_v3',
    name: '语音识别',
    groupId: '1',
    displayOrder: 0,
    status: 'online',
    description: '',
    deviceParams: [],
    apiParams: [],
    caseParams: [],
    referenceParams: [],
    mappings: { device: [], api: [], evaluation: [] },
    associatedDimensions: [
      { key: 'dim-1', dimensionId: '1', dimensionName: '识别准确率', weight: '0.5', isDefault: true },
      { key: 'dim-2', dimensionId: '2', dimensionName: '响应延迟', weight: '0.3', isDefault: false },
      { key: 'dim-3', dimensionId: '3', dimensionName: '噪声鲁棒性', weight: '0.2', isDefault: false },
    ],
  }
}

function Harness({ values = buildValues() }: { values?: AlgorithmFormValues }) {
  const form = useForm<AlgorithmFormValues>({ defaultValues: values })
  return <DimensionsSection form={form} dimensionOptions={DIMENSION_OPTIONS} />
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
})
