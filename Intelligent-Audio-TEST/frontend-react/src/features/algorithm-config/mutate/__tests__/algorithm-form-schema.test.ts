/**
 * §6 编辑表单 zod schema 单测（features/algorithm-config/mutate）。
 * 必填校验 + 算法代码正则 + 参数代码同页签唯一性；INT-591 §6.2 双门槛：
 * 草稿宽松（algorithmDraftFormSchema：仅参数代码结构级）vs 发布严格（名称/分组必填 + 范围 min≤max）。
 */
import { describe, expect, it } from 'vitest'

import {
  algorithmDraftFormSchema,
  algorithmFormSchema,
} from '@/features/algorithm-config/mutate/algorithm-form-schema'
import type { AlgorithmFormValues } from '@/features/algorithm-config/types'

function validBase(): AlgorithmFormValues {
  return {
    type: 'asr_v3',
    name: '通用识别引擎',
    groupId: '1',
    displayOrder: 0,
    status: 'online',
    description: '',
    deviceParams: [],
    apiParams: [],
    caseParams: [],
    referenceParams: [],
    mappings: { device: [], api: [], evaluation: [] },
    associatedDimensions: [],
  }
}

describe('algorithmFormSchema', () => {
  it('通过合法算法定义表单', () => {
    const result = algorithmFormSchema.safeParse(validBase())
    expect(result.success).toBe(true)
  })

  it('算法代码必填且需小写字母开头（§6.2 正则）', () => {
    const missing = algorithmFormSchema.safeParse({ ...validBase(), type: '' })
    expect(missing.success).toBe(false)
    if (!missing.success) {
      expect(missing.error.issues.some((i) => i.path[0] === 'type')).toBe(true)
    }

    const invalid = algorithmFormSchema.safeParse({ ...validBase(), type: 'AsrV3' })
    expect(invalid.success).toBe(false)
  })

  it('显示名称必填；所属分组可空（V9.7.10 行为：未分组算法合法）', () => {
    const noName = algorithmFormSchema.safeParse({ ...validBase(), name: '' })
    expect(noName.success).toBe(false)
    const noGroup = algorithmFormSchema.safeParse({ ...validBase(), groupId: '' })
    expect(noGroup.success).toBe(true)
  })

  it('同页签参数代码重复报「参数代码重复」（§6.3 行级唯一）', () => {
    const duplicate = validBase()
    duplicate.deviceParams = [
      {
        key: 'd-1',
        paramCode: 'input_audio',
        paramName: '',
        direction: 'input',
        paramType: 'text',
        required: false,
        defaultValue: '',
        helpText: '',
      },
      {
        key: 'd-2',
        paramCode: 'input_audio',
        paramName: '',
        direction: 'input',
        paramType: 'text',
        required: false,
        defaultValue: '',
        helpText: '',
      },
    ]
    const result = algorithmFormSchema.safeParse(duplicate)
    expect(result.success).toBe(false)
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.message === '参数代码重复')
      expect(issue).toBeTruthy()
    }
  })

  it('不同页签同代码不视为重复（设备/API/用例各自唯一）', () => {
    const spread = validBase()
    spread.deviceParams = [
      {
        key: 'd-1',
        paramCode: 'input_audio',
        paramName: '',
        direction: 'input',
        paramType: 'text',
        required: false,
        defaultValue: '',
        helpText: '',
      },
    ]
    spread.apiParams = [
      {
        key: 'a-1',
        paramCode: 'input_audio',
        paramName: '',
        direction: 'input',
        paramType: 'text',
        required: false,
        defaultValue: '',
        helpText: '',
      },
    ]
    const result = algorithmFormSchema.safeParse(spread)
    expect(result.success).toBe(true)
  })

  it('参数代码为空标错（行级必填）', () => {
    const empty = validBase()
    empty.caseParams = [
      {
        key: 'c-1',
        paramCode: '',
        paramName: '',
        paramType: 'text',
        scope: 'common',
        required: false,
        defaultValue: '',
        minValue: '',
        maxValue: '',
        step: '',
        unit: '',
        annotationCode: '',
        fieldPath: '',
        helpText: '',
      },
    ]
    const result = algorithmFormSchema.safeParse(empty)
    expect(result.success).toBe(false)
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path[0] === 'caseParams')
      expect(issue).toBeTruthy()
    }
  })

  /* ───────── INT-591 §6.2 草稿宽松 vs 发布严格双门槛 ───────── */

  it('草稿宽松：算法代码/名称/分组可空（中间态暂存）', () => {
    const values = { ...validBase(), type: '', name: '', groupId: '' }
    const draft = algorithmDraftFormSchema.safeParse(values)
    expect(draft.success).toBe(true)
    // 发布严格：同值被拦
    const publish = algorithmFormSchema.safeParse(values)
    expect(publish.success).toBe(false)
  })

  it('草稿宽松：参数代码非空 + 同作用域唯一仍拦截（结构级门槛）', () => {
    const duplicate = validBase()
    duplicate.deviceParams = [
      { key: 'd-1', paramCode: '', paramName: '', direction: 'input', paramType: 'text', required: false, defaultValue: '', helpText: '' },
    ]
    expect(algorithmDraftFormSchema.safeParse(duplicate).success).toBe(false)

    const unique = validBase()
    unique.apiParams = [
      { key: 'a-1', paramCode: 'good_code', paramName: '', direction: 'input', paramType: 'text', required: false, defaultValue: '', helpText: '' },
      { key: 'a-2', paramCode: 'good_code', paramName: '', direction: 'input', paramType: 'text', required: false, defaultValue: '', helpText: '' },
    ]
    const result = algorithmDraftFormSchema.safeParse(unique)
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message === '参数代码重复')).toBe(true)
    }
  })

  it('发布严格：范围 min>max 拦截（草稿不校验范围）', () => {
    const badRange = validBase()
    badRange.caseParams = [
      {
        key: 'c-1',
        paramCode: 'volume',
        paramName: '音量',
        paramType: 'number',
        scope: 'common',
        required: false,
        defaultValue: '5',
        minValue: '10',
        maxValue: '1',
        step: '1',
        unit: '',
        annotationCode: '',
        fieldPath: '',
        helpText: '',
      },
    ]
    const publish = algorithmFormSchema.safeParse(badRange)
    expect(publish.success).toBe(false)
    if (!publish.success) {
      expect(
        publish.error.issues.some((i) => i.message.includes('最小'))
      ).toBe(true)
    }
    // 草稿宽松：范围不校验，可通过
    const draft = algorithmDraftFormSchema.safeParse(badRange)
    expect(draft.success).toBe(true)
  })

  it('草稿宽松：参数代码含连字符/大写 + 参数类型未选仍放行（§6.2 正则/类型草稿阶段不校验），发布严格双门槛拦截', () => {
    const values = validBase()
    values.deviceParams = [
      {
        key: 'd-1',
        paramCode: 'input-audio-V1', // 发布正则 ^[a-z][a-z0-9_]*$ 非法（连字符+大写）
        paramName: '',
        direction: 'input',
        paramType: '', // 发布类型必填拦截；草稿允许暂存
        required: false,
        defaultValue: '',
        helpText: '',
      },
    ]
    const draft = algorithmDraftFormSchema.safeParse(values)
    expect(draft.success).toBe(true)
    const publish = algorithmFormSchema.safeParse(values)
    expect(publish.success).toBe(false)
  })

  it('草稿宽松：映射/参考参数/关联维度未填完仍可暂存（§6.2 中间态），发布严格拦截', () => {
    const values = validBase()
    values.referenceParams = [
      {
        key: 'r-1',
        code: 'ref_code',
        name: '',
        type: '', // 参考类型未选：草稿放行
        annotationCode: '',
        annotationFormat: '',
        fieldPath: '',
        mergeMode: '',
        helpText: '',
      },
    ]
    values.mappings.device = [
      { key: 'md-1', sourceParam: 'input_audio', targetParam: '', transformType: '' },
    ]
    values.associatedDimensions = [
      { key: 'dim-1', dimensionId: '', dimensionName: '', weight: '', isDefault: false },
    ]
    const draft = algorithmDraftFormSchema.safeParse(values)
    expect(draft.success).toBe(true)
    const publish = algorithmFormSchema.safeParse(values)
    expect(publish.success).toBe(false)
  })
})
