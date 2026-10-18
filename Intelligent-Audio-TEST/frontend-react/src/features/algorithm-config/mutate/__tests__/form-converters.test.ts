/**
 * 算法编辑表单 领域模型 ↔ RHF 值 转换单测（features/algorithm-config/mutate）。
 * 覆盖 toFormValues / cloneFormValues（INT-211 副本命名）/ toSaveInput 聚合载荷（剔除 key）。
 */
import { describe, expect, it } from 'vitest'

import type { AlgorithmDefinition } from '@/domain/models/algorithmConfig'
import {
  cloneFormValues,
  emptyFormValues,
  toFormValues,
  toSaveInput,
  __resetFormKeyCounter,
} from '@/features/algorithm-config/mutate/form-converters'

const SAMPLE: AlgorithmDefinition = {
  id: 1,
  type: 'asr-v3',
  name: '通用识别引擎',
  groupId: 1,
  groupName: '语音识别',
  category: null,
  description: '基线模型',
  status: 'online',
  icon: null,
  displayOrder: 1,
  deviceParams: [
    {
      id: 101,
      paramCode: 'input_audio',
      paramName: '输入音频',
      label: '输入音频',
      paramType: 'audio_file',
      direction: 'input',
      required: true,
      defaultValue: null,
      helpText: '',
      uiOrder: 101,
      hidden: false,
    },
  ],
  apiParams: [],
  caseParams: [
    {
      id: 301,
      paramCode: 'source_language',
      paramName: '源语言',
      label: '源语言',
      paramType: 'select',
      scope: 'common',
      required: false,
      defaultValue: 'zh',
      helpText: '',
      uiOrder: 301,
      hidden: false,
      minValue: null,
      maxValue: null,
      step: null,
      unit: null,
      annotationCode: null,
      fieldPath: null,
    },
  ],
  referenceParams: [
    {
      id: 401,
      code: 'ref_text',
      name: '参考文本',
      type: 'text',
      annotationCode: null,
      annotationFormat: null,
      fieldPath: null,
      mergeMode: 'join',
      helpText: null,
    },
  ],
  mappings: {
    device: [
      { id: 501, sourceParam: 'audio_file', targetParam: 'input_audio', transformType: 'none' },
    ],
    api: [],
    evaluation: [
      { id: 504, sourceParam: 'output_text', targetParam: '识别准确率', transformType: 'none' },
    ],
  },
  associatedDimensions: [{ id: 601, dimensionId: 3, dimensionName: '识别准确率', weight: 1, isDefault: true }],
  caseCount: 50,
  createdAt: '2026-08-10T08:30:00Z',
  updatedAt: '2026-10-12T16:40:00Z',
}

describe('form-converters', () => {
  it('toFormValues 将领域模型完整映射为表单值（含字段数组与映射）', () => {
    __resetFormKeyCounter()
    const values = toFormValues(SAMPLE)
    expect(values.type).toBe('asr-v3')
    expect(values.name).toBe('通用识别引擎')
    expect(values.groupId).toBe('1')
    expect(values.status).toBe('online')
    expect(values.deviceParams).toHaveLength(1)
    expect(values.deviceParams[0]).toMatchObject({
      paramCode: 'input_audio',
      direction: 'input',
      required: true,
    })
    expect(values.caseParams[0]).toMatchObject({ defaultValue: 'zh', scope: 'common' })
    expect(values.referenceParams[0]).toMatchObject({ mergeMode: 'join' })
    expect(values.mappings.device[0].targetParam).toBe('input_audio')
    expect(values.mappings.evaluation[0].targetParam).toBe('识别准确率')
    expect(values.associatedDimensions[0].isDefault).toBe(true)
  })

  it('cloneFormValues 追加 _copy 与「(副本)」（§7.4 副本命名）', () => {
    __resetFormKeyCounter()
    const values = cloneFormValues(SAMPLE)
    expect(values.type).toBe('asr-v3_copy')
    expect(values.name).toBe('通用识别引擎 (副本)')
    expect(values.deviceParams).toHaveLength(1)
  })

  it('emptyFormValues 默认状态上线、分组与代码为空（§6.1 create 初始载荷）', () => {
    const values = emptyFormValues()
    expect(values.type).toBe('')
    expect(values.groupId).toBe('')
    expect(values.status).toBe('online')
    expect(values.deviceParams).toEqual([])
    expect(values.mappings).toEqual({ device: [], api: [], evaluation: [] })
  })

  it('toSaveInput 剔除行级 key 并保留聚合字段（§6.3 聚合提交载荷）', () => {
    __resetFormKeyCounter()
    const values = toFormValues(SAMPLE)
    const input = toSaveInput(values)
    expect(input.type).toBe('asr-v3')
    expect(input.groupId).toBe(1)
    expect(input.deviceParams).toHaveLength(1)
    expect(input.deviceParams[0]).not.toHaveProperty('key')
    expect(input.deviceParams[0]).toMatchObject({ paramCode: 'input_audio' })
    expect(input.mappings.device).toHaveLength(1)
    expect(input.associatedDimensions[0]).toMatchObject({ dimensionId: '3' })
  })
})
