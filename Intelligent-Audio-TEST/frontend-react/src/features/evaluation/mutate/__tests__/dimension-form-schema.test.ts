/**
 * 评估维度表单 schema/转换器（11_用例域.md §5.5）单元测试。
 * 覆盖空表单初值、编辑反填（toDimensionFormValues）、保存载荷收敛
 * （toDimensionSaveInput：子维度不携带 API 配置、LLM Judge 结果类型映射）。
 */
import { describe, expect, it } from 'vitest'

import type { Dimension } from '@/domain/models/evaluationDimension'
import {
  emptyDimensionFormValues,
  toDimensionFormValues,
  toDimensionSaveInput,
} from '@/features/evaluation/mutate/dimension-form-schema'

const mockDimension: Dimension = {
  id: 1,
  name: '识别准确率',
  description: '语音识别整体准确率',
  keywords: '准确,精度',
  dimensionType: 'main',
  parentDimensionId: null,
  categoryId: 1,
  apiUrl: 'https://api.example.com/evaluation/accuracy',
  apiStatus: 'online',
  scoreUnit: '%',
  type: 'auto',
  resultType: 1,
  resultMin: 0,
  resultMax: 100,
  decimalPlaces: 2,
  weight: 9,
  estimatedExecTime: 5,
  rule: {
    rules: [
      { condition: '>=', value: 95, score: 10 },
      { condition: '<', value: 95, score: 0 },
    ],
  },
  statisticMethod: 'average',
  aggDenominator: 'case',
  excludeRounds: [],
  associatedAlgorithms: [{ algorithmType: 'asr-v3', isDefault: true, weight: 9 }],
  status: true,
}

describe('emptyDimensionFormValues', () => {
  it('默认主维度/启用/权重 5/结果类型数值', () => {
    const values = emptyDimensionFormValues()
    expect(values.name).toBe('')
    expect(values.dimensionType).toBe('main')
    expect(values.status).toBe(true)
    expect(values.weight).toBe(5)
    expect(values.resultType).toBe('1')
    expect(values.rule.length).toBeGreaterThan(0)
  })
})

describe('toDimensionFormValues', () => {
  it('编辑态 Dimension 反填主维度字段', () => {
    const values = toDimensionFormValues(mockDimension)
    expect(values.name).toBe('识别准确率')
    expect(values.dimensionType).toBe('main')
    expect(values.categoryId).toBe('1')
    expect(values.weight).toBe(9)
    expect(values.associatedAlgorithms).toEqual(['asr-v3'])
    expect(values.rule[0]).toEqual({ condition: '>=', value: 95, score: 10 })
  })

  it('LLM Judge 结果类型映射为 llm_judge 字符串', () => {
    const values = toDimensionFormValues({
      ...mockDimension,
      resultType: 'llm_judge',
      llmJudgeConfig: { model: 'gpt-4o-mini', promptTemplate: '', maxTokens: 1024, temperature: 0.7 },
    })
    expect(values.resultType).toBe('llm_judge')
    expect(values.llmModel).toBe('gpt-4o-mini')
  })
})

describe('toDimensionSaveInput', () => {
  it('主维度收敛为 Partial<Dimension>（含 rule/关联算法/权重）', () => {
    const values = toDimensionFormValues(mockDimension)
    const input = toDimensionSaveInput(values)
    expect(input.name).toBe('识别准确率')
    expect(input.dimensionType).toBe('main')
    expect(input.categoryId).toBe(1)
    expect(input.weight).toBe(9)
    expect(input.rule).toEqual({ rules: values.rule })
    expect(input.associatedAlgorithms).toEqual([
      { algorithmType: 'asr-v3', isDefault: false, weight: 9 },
    ])
  })

  it('子维度不携带 API 配置（继承父维度）', () => {
    const values = toDimensionFormValues({
      ...mockDimension,
      dimensionType: 'sub',
      parentDimensionId: 1,
      keywords: null,
    })
    const input = toDimensionSaveInput(values)
    expect(input.dimensionType).toBe('sub')
    expect(input.parentDimensionId).toBe(1)
    expect(input.apiUrl).toBeNull()
    expect(input.apiSettings).toBeUndefined()
    expect(input.keywords).toBeNull()
  })

  it('LLM Judge 保存载荷携带 llmJudgeConfig', () => {
    const values = toDimensionFormValues({
      ...mockDimension,
      resultType: 'llm_judge',
      llmJudgeConfig: { model: 'gpt-4o-mini', promptTemplate: 'p', maxTokens: 512, temperature: 0.5 },
    })
    const input = toDimensionSaveInput(values)
    expect(input.resultType).toBe('llm_judge')
    expect(input.llmJudgeConfig).toEqual({
      model: 'gpt-4o-mini',
      promptTemplate: 'p',
      maxTokens: 512,
      temperature: 0.5,
    })
  })
})
