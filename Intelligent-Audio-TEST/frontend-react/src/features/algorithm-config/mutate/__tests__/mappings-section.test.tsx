/**
 * §6.5 评估参数映射视图切换测试（INT-1030 返工：负责人「参数映射没照 V9.7.10，仍平铺」）：
 * 默认「评估维度视图」按目标评估维度分组（组头=维度名 + 主/子徽章 + 计数，空行归「未指定维度」）；
 * 「平铺视图」回到全量平铺表；组尾「添加映射」预填该维度。
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'

import type { AlgorithmFormValues } from '@/features/algorithm-config/types'
import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import { MappingsSection } from '../mappings-section'

const DIMENSIONS: Dimension[] = [
  { id: 1, name: '识别准确率', dimensionType: 'main', parentDimensionId: null, categoryId: 1 },
  { id: 2, name: '响应延迟', dimensionType: 'main', parentDimensionId: null, categoryId: 1 },
  { id: 11, name: '字准率', dimensionType: 'sub', parentDimensionId: 1, categoryId: 1 },
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
    apiParams: [],
    caseParams: [],
    referenceParams: [],
    mappings: {
      device: [],
      api: [],
      evaluation: [
        { key: 'me-1', sourceParam: 'asr_result', targetParam: '识别准确率', transformType: 'none' },
        { key: 'me-2', sourceParam: 'tts_text', targetParam: '识别准确率', transformType: 'uppercase' },
        { key: 'me-3', sourceParam: 'audios', targetParam: '响应延迟', transformType: 'none' },
        { key: 'me-4', sourceParam: 'other', targetParam: '', transformType: 'none' },
        { key: 'me-5', sourceParam: 'char', targetParam: '字准率', transformType: 'none' },
      ],
    },
    associatedDimensions: [],
  }
}

function Harness() {
  const form = useForm<AlgorithmFormValues>({ defaultValues: buildValues() })
  return (
    <MappingsSection
      form={form}
      dimensions={DIMENSIONS}
      categories={CATEGORIES}
    />
  )
}

/** 展开「评估参数映射」折叠分区（MappingCollapsible 默认收起） */
async function expandEvaluationMapping(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /评估参数映射/ }))
}

/** 维度分组组头按钮（名称以维度名开头 + 含计数「条」；避开子维度组头的父名提示与行内触发器） */
function groupHeader(name: string) {
  return screen.getByRole('button', { name: new RegExp(`^${name}.*条`) })
}

/** 点击指定维度组尾的「添加映射」 */
async function clickGroupAdd(user: ReturnType<typeof userEvent.setup>, name: string) {
  const header = groupHeader(name)
  const tr = header.closest('tr')
  expect(tr).not.toBeNull()
  let sibling = tr!.nextElementSibling
  while (sibling) {
    const btn = sibling.querySelector('button')
    if (btn && /添加映射/.test(btn.textContent ?? '')) {
      await user.click(btn as HTMLElement)
      return
    }
    sibling = sibling.nextElementSibling
  }
  throw new Error(`未找到「${name}」组的添加映射按钮`)
}

describe('评估参数映射 视图切换（INT-1030 返工）', () => {
  it('默认「评估维度视图」：按目标维度分组，组头=维度名+计数，空行归「未指定维度」', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await expandEvaluationMapping(user)
    expect(groupHeader('识别准确率')).toBeInTheDocument()
    expect(groupHeader('响应延迟')).toBeInTheDocument()
    expect(groupHeader('字准率')).toBeInTheDocument()
    expect(groupHeader('未指定维度')).toBeInTheDocument()
    // 组头计数徽章（识别准确率 2 条；其余各组 1 条）
    expect(screen.getByText('2 条')).toBeInTheDocument()
    expect(screen.getAllByText('1 条').length).toBeGreaterThanOrEqual(3)
  })

  it('维度组头展示主/子徽章与子维度父名', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await expandEvaluationMapping(user)
    // 识别准确率为主维度 → 主徽章
    const mainGroup = groupHeader('识别准确率')
    expect(within(mainGroup).getByText('主')).toBeInTheDocument()
    // 响应延迟也是主维度 → 主徽章
    const delayGroup = groupHeader('响应延迟')
    expect(within(delayGroup).getByText('主')).toBeInTheDocument()
    // 字准率子维度 → 子徽章 + 父名提示
    const subGroup = groupHeader('字准率')
    expect(within(subGroup).getByText('子')).toBeInTheDocument()
    expect(within(subGroup).getByText(/识别准确率/)).toBeInTheDocument()
  })

  it('组尾「添加映射」预填该维度（识别准确率组）', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await expandEvaluationMapping(user)
    await clickGroupAdd(user, '识别准确率')
    // 新增一行 targetParam=识别准确率 → 该组计数 2 → 3 条
    expect(within(groupHeader('识别准确率')).getByText('3 条')).toBeInTheDocument()
  })

  it('切换「平铺视图」回到全量平铺（无分组头）', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await expandEvaluationMapping(user)
    // ToggleGroupItem 渲染为带文本的按钮；按文本定位
    await user.click(screen.getByText('平铺视图'))
    expect(screen.queryByRole('button', { name: /识别准确率.*条/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /未指定维度.*条/ })).not.toBeInTheDocument()
  })
})
