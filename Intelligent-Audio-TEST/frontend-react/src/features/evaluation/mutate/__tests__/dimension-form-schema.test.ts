/**
 * 评估维度表单 schema/转换器（11_用例域.md §5.5）单元测试。
 * 覆盖空表单初值、编辑反填（toDimensionFormValues）、保存载荷收敛
 * （toDimensionSaveInput：子维度不携带 API 配置、LLM Judge 结果类型映射、
 * 所需输入/输出字段/API 端点随载荷提交——P3-2 收敛）。
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
  requiredInputs: [
    { paramCode: 'asr_result', paramName: 'ASR识别结果', label: 'ASR识别结果', fieldType: 'text', required: true, helpText: 'ASR算法识别出的文本', uiOrder: 1 },
  ],
  outputFields: [
    { paramCode: 'score', paramName: '评分结果', label: '评分结果', fieldPath: 'score', fieldType: 'number', outputRole: 'main', aggRole: 'value', visibleInReport: true, uiOrder: 1 },
  ],
  apiEndpoints: [
    { url: 'https://api.example.com/evaluation/accuracy', name: '主评估端点', priority: 1, maxProcess: 5, maxTimeout: 30, maxAudioDuration: 60 },
  ],
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

  it('所需输入/输出字段/API 端点带默认行（P3-2 子编辑器收敛进表单）', () => {
    const values = emptyDimensionFormValues()
    expect(values.requiredInputs.length).toBeGreaterThan(0)
    expect(values.requiredInputs[0].paramCode).toBe('asr_result')
    expect(values.outputFields.length).toBeGreaterThan(0)
    expect(values.apiEndpoints.length).toBeGreaterThan(0)
    expect(values.apiEndpoints[0].priority).toBe(1)
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

  it('所需输入/输出字段/API 端点反填（P3-2）', () => {
    const values = toDimensionFormValues(mockDimension)
    expect(values.requiredInputs).toHaveLength(1)
    expect(values.requiredInputs[0]).toMatchObject({
      paramCode: 'asr_result',
      paramName: 'ASR识别结果',
      required: true,
    })
    expect(values.outputFields[0]).toMatchObject({
      paramCode: 'score',
      outputRole: 'main',
      aggRole: 'value',
    })
    expect(values.apiEndpoints[0]).toMatchObject({
      url: 'https://api.example.com/evaluation/accuracy',
      priority: 1,
    })
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

  it('主维度携带所需输入/输出字段/API 端点（P3-2）', () => {
    const input = toDimensionSaveInput(toDimensionFormValues(mockDimension))
    expect(input.requiredInputs).toEqual([
      {
        paramCode: 'asr_result',
        paramName: 'ASR识别结果',
        label: 'ASR识别结果',
        fieldType: 'text',
        required: true,
        defaultValue: undefined,
        helpText: 'ASR算法识别出的文本',
        uiOrder: 1,
      },
    ])
    expect(input.outputFields?.[0].paramCode).toBe('score')
    expect(input.apiEndpoints?.[0].priority).toBe(1)
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
    expect(input.requiredInputs).toBeUndefined()
    expect(input.outputFields).toBeUndefined()
    expect(input.apiEndpoints).toBeUndefined()
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

  it('输出字段 passThreshold 反填与保存往返（INT-1350 三轮 P1）', () => {
    const dim: Dimension = {
      ...mockDimension,
      outputFields: [
        {
          paramCode: 'wer',
          paramName: 'WER值',
          label: 'WER值',
          fieldPath: 'wer',
          fieldType: 'number',
          outputRole: 'main',
          aggRole: 'pass_le',
          defaultValue: 0,
          passThreshold: 0.15,
          visibleInReport: true,
          uiOrder: 1,
        },
      ],
    }
    const values = toDimensionFormValues(dim)
    expect(values.outputFields[0].passThreshold).toBe('0.15')
    const input = toDimensionSaveInput(values)
    expect(input.outputFields?.[0].passThreshold).toBe(0.15)
    expect(input.outputFields?.[0].defaultValue).toBe(0)
  })

  it('default_value 按 field_type 还原类型（INT-1350 三轮 P2）', () => {
    const dim: Dimension = {
      ...mockDimension,
      requiredInputs: [
        { paramCode: 'n', paramName: 'n', label: 'n', fieldType: 'number', required: false, defaultValue: 0, uiOrder: 1 },
        { paramCode: 'b', paramName: 'b', label: 'b', fieldType: 'boolean', required: false, defaultValue: false, uiOrder: 2 },
        { paramCode: 'j', paramName: 'j', label: 'j', fieldType: 'json', required: false, defaultValue: { k: 1 }, uiOrder: 3 },
        { paramCode: 't', paramName: 't', label: 't', fieldType: 'text', required: false, defaultValue: 'hello', uiOrder: 4 },
      ],
      outputFields: [
        {
          paramCode: 'score',
          paramName: '评分结果',
          label: '评分结果',
          fieldPath: 'score',
          fieldType: 'number',
          outputRole: 'main',
          aggRole: 'value',
          defaultValue: 0,
          visibleInReport: true,
          uiOrder: 1,
        },
      ],
    }
    const input = toDimensionSaveInput(toDimensionFormValues(dim))
    // 表单 String(0)='0' → number 字段还原为数值 0
    expect(input.requiredInputs?.[0].defaultValue).toBe(0)
    expect(input.outputFields?.[0].defaultValue).toBe(0)
    // boolean 'false' → false
    expect(input.requiredInputs?.[1].defaultValue).toBe(false)
    // json '{"k":1}' → 对象
    expect(input.requiredInputs?.[2].defaultValue).toEqual({ k: 1 })
    // text 原样
    expect(input.requiredInputs?.[3].defaultValue).toBe('hello')
  })

  it('空默认值/空达标阈值不上送（undefined/null）', () => {
    const input = toDimensionSaveInput(toDimensionFormValues(mockDimension))
    expect(input.requiredInputs?.[0].defaultValue).toBeUndefined()
    expect(input.outputFields?.[0].defaultValue).toBeUndefined()
    expect(input.outputFields?.[0].passThreshold).toBeNull()
  })
})

