/**
 * 评估维度表单 schema/转换器（11_用例域.md §5.5）单元测试。
 * 覆盖空表单初值、编辑反填（toDimensionFormValues）、保存载荷收敛
 * （toDimensionSaveInput：子维度不携带 API 配置、结果类型只发整数（INT-1681 / INT-1671 裁定 A）、
 * 所需输入/输出字段/API 端点随载荷提交——P3-2 收敛）。
 */
import { describe, expect, it } from 'vitest'

import type { Dimension } from '@/domain/models/evaluationDimension'
import {
  dimensionFormSchema,
  emptyDimensionFormValues,
  toDimensionFormValues,
  toDimensionSaveInput,
} from '@/features/evaluation/mutate/dimension-form-schema'
import { toDimensionInputDto } from '@/infrastructure/dto/evaluation.dto'

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

  it('所需输入/API 端点带默认行，输出字段默认空（P3-2 子编辑器收敛进表单）', () => {
    const values = emptyDimensionFormValues()
    expect(values.requiredInputs.length).toBeGreaterThan(0)
    expect(values.requiredInputs[0].paramCode).toBe('asr_result')
    expect(values.apiEndpoints.length).toBeGreaterThan(0)
    expect(values.apiEndpoints[0].priority).toBe(1)
  })

  it('默认不预填输出字段（INT-1816 P3-1：V9.7.10 newDimension 无 outputFields）', () => {
    const values = emptyDimensionFormValues()
    expect(values.outputFields).toEqual([])
  })

  it('默认评分规则 6 档对齐 V9.7.10 dimensionTemplate.rule（INT-1816 P3-2）', () => {
    const values = emptyDimensionFormValues()
    expect(values.rule).toEqual([
      { condition: '>=', value: 95, score: 10 },
      { condition: '>=', value: 90, score: 9 },
      { condition: '>=', value: 80, score: 8 },
      { condition: '>=', value: 70, score: 7 },
      { condition: '>=', value: 60, score: 6 },
      { condition: '<', value: 60, score: 0 },
    ])
  })

  it('默认 API 端点 URL 为空（INT-1732 P3-3：不再预填 api.example.com 假端点）', () => {
    const values = emptyDimensionFormValues()
    expect(values.apiEndpoints[0].url).toBe('')
    expect(values.apiEndpoints[0].name).toBe('')
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

  it('LLM Judge 维度按原整数结果类型反填（不是 llm_judge 字符串；INT-1681 / INT-1671）', () => {
    const values = toDimensionFormValues({
      ...mockDimension,
      resultType: 1,
      llmJudge: true,
    })
    expect(values.resultType).toBe('1')
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

  it('无输出字段的维度反填为空，不塞示例 score 行（INT-1816 P3-1）', () => {
    const values = toDimensionFormValues({ ...mockDimension, outputFields: [] })
    expect(values.outputFields).toEqual([])
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

  it('结果类型保存为整数且不携带 llmJudgeConfig（INT-1681：不发 llm_judge 字符串）', () => {
    const values = toDimensionFormValues({ ...mockDimension, llmJudge: true })
    const input = toDimensionSaveInput(values)
    expect(input.resultType).toBe(1)
    expect(input).not.toHaveProperty('llmJudgeConfig')
    const dto = toDimensionInputDto(input)
    expect(dto.result_type).toBe(1)
    expect(dto).not.toHaveProperty('llm_judge_config')
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

  it('编辑「输入显示标签」保存后写 DTO 的 param_name 为新值（INT-1690）', () => {
    const values = toDimensionFormValues(mockDimension)
    // 用户改「输入显示标签 1」：ASR识别结果 → 输入新标签C
    values.requiredInputs[0].paramName = '输入新标签C'
    const input = toDimensionSaveInput(values)
    expect(input.requiredInputs?.[0].paramName).toBe('输入新标签C')
    // label 不得再压过可见的 paramName（同一份数据单一口径）
    expect(input.requiredInputs?.[0].label).toBe('输入新标签C')
    const dto = toDimensionInputDto(input)
    const requiredInputs = dto.required_inputs as Array<Record<string, unknown>>
    // 后端按 param_name 优先，缺了它就会被旧 label 覆盖 → 编辑不落库
    expect(requiredInputs[0].param_name).toBe('输入新标签C')
    expect(requiredInputs[0].label).toBe('输入新标签C')
  })

  it('旧数据 param_name 为空时回显仍回退 label（INT-1690 兼容）', () => {
    const values = toDimensionFormValues({
      ...mockDimension,
      requiredInputs: [
        {
          paramCode: 'q_text',
          paramName: '',
          label: '输入原标签B',
          fieldType: 'text',
          required: true,
          uiOrder: 1,
        },
      ],
    })
    expect(values.requiredInputs[0].paramName).toBe('输入原标签B')
  })

  it('输出字段 param_name 仍随编辑更新（INT-1690 不回归）', () => {
    const values = toDimensionFormValues(mockDimension)
    values.outputFields[0].paramName = '输出新标签C'
    const dto = toDimensionInputDto(toDimensionSaveInput(values))
    const outputFields = dto.output_fields as Array<Record<string, unknown>>
    expect(outputFields[0].param_name).toBe('输出新标签C')
  })
})

describe('INT-1732 评分规则不再被默认模板顶替', () => {
  it('编辑空规则维度：反填不留默认 5 条，原样保存 rule 仍为 {rules:[], defaultScore}', () => {
    const dimension: Dimension = {
      ...mockDimension,
      resultType: 0,
      rule: { rules: [], defaultScore: 7 },
    }
    const values = toDimensionFormValues(dimension)
    expect(values.rule).toEqual([])
    const input = toDimensionSaveInput(values)
    expect(input.rule).toEqual({ rules: [], defaultScore: 7 })
    expect(input.resultType).toBe(0)
  })

  it('rule 里的其它键（defaultScore 之外）也在保存时保留', () => {
    const dimension: Dimension = {
      ...mockDimension,
      rule: { rules: [], defaultScore: 0, type: 'threshold', min: 0, max: 1 },
    }
    const input = toDimensionSaveInput(toDimensionFormValues(dimension))
    expect(input.rule).toEqual({
      rules: [],
      defaultScore: 0,
      type: 'threshold',
      min: 0,
      max: 1,
    })
  })

  it('已有规则的维度：编辑保存后规则原样，增 1 条 / 删 1 条均生效', () => {
    const values = toDimensionFormValues({
      ...mockDimension,
      rule: {
        rules: [
          { condition: '>=', value: 95, score: 10 },
          { condition: '<', value: 95, score: 0 },
        ],
        defaultScore: 3,
      },
    })
    values.rule.splice(0, 1)
    values.rule.push({ condition: '>=', value: 60, score: 6 })
    const input = toDimensionSaveInput(values)
    expect(input.rule).toEqual({
      defaultScore: 3,
      rules: [
        { condition: '<', value: 95, score: 0 },
        { condition: '>=', value: 60, score: 6 },
      ],
    })
  })

  it('rule 是 JSON 字符串（历史数据）时同样可反填并保留未知键', () => {
    const values = toDimensionFormValues({
      ...mockDimension,
      rule: JSON.stringify({
        rules: [{ condition: '>=', value: 90, score: 9 }],
        defaultScore: 5,
      }),
    })
    expect(values.rule).toEqual([{ condition: '>=', value: 90, score: 9 }])
    expect(toDimensionSaveInput(values).rule).toEqual({
      rules: [{ condition: '>=', value: 90, score: 9 }],
      defaultScore: 5,
    })
  })

  it('空规则可通过表单校验（去掉「至少一条」）', () => {
    const values = { ...emptyDimensionFormValues(), name: '接线测试_空规则' }
    values.rule = []
    expect(dimensionFormSchema.safeParse(values).success).toBe(true)
  })
})

describe('dimensionFormSchema 结果区间校验（INT-1551）', () => {
  it('结果最小值 ≥ 结果最大值时在 resultMax 上给出中文错误', () => {
    const values = { ...emptyDimensionFormValues(), name: '接线测试_区间' }
    values.resultMin = 100
    values.resultMax = 50
    const result = dimensionFormSchema.safeParse(values)
    expect(result.success).toBe(false)
    if (result.success) return
    const issue = result.error.issues.find((i) => i.path[0] === 'resultMax')
    expect(issue?.message).toBe('结果最大值必须大于最小值')
  })

  it('清空数值输入（NaN）给出中文文案而非 zod 默认英文', () => {
    const values = { ...emptyDimensionFormValues(), name: '接线测试_区间' }
    values.resultMin = Number.NaN
    const result = dimensionFormSchema.safeParse(values)
    expect(result.success).toBe(false)
    if (result.success) return
    const issue = result.error.issues.find((i) => i.path[0] === 'resultMin')
    expect(issue?.message).toBe('结果最小值请输入数字')
  })

  it('区间合法时整表通过校验', () => {
    const values = { ...emptyDimensionFormValues(), name: '接线测试_区间' }
    values.resultMin = 0
    values.resultMax = 100
    expect(dimensionFormSchema.safeParse(values).success).toBe(true)
  })
})
