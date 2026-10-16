/**
 * §6 编辑表单 zod schema 单测（features/algorithm-config/mutate）。
 * 必填校验 + 算法代码正则 + 参数代码同页签唯一性。
 */
import { describe, expect, it } from 'vitest'

import { algorithmFormSchema } from '@/features/algorithm-config/mutate/algorithm-form-schema'
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

  it('显示名称与所属分组必填', () => {
    const noName = algorithmFormSchema.safeParse({ ...validBase(), name: '' })
    expect(noName.success).toBe(false)
    const noGroup = algorithmFormSchema.safeParse({ ...validBase(), groupId: '' })
    expect(noGroup.success).toBe(false)
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
        helpText: '',
      },
      {
        key: 'd-2',
        paramCode: 'input_audio',
        paramName: '',
        direction: 'input',
        paramType: 'text',
        required: false,
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
})
