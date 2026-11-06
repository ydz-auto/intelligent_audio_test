/**
 * INT-2267：参数策略「整份保存」回环单测。
 *
 * 锁定两件事：
 * 1. 读侧把 required / default_value / help_text / hidden / label / validation
 *    与映射 source / source_direction 完整读成 camelCase；
 * 2. 写侧按草稿原值回落成 snake_case —— 未展示的字段（label / validation_rules /
 *    config 快照）必须透传，不能用常量兜底把后端列清空。
 */
import { describe, expect, it } from 'vitest'

import type { ParamProfileInput } from '@/domain/models/paramProfile'
import {
  toParamProfile,
  toParamProfileDto,
} from '@/infrastructure/dto/param-profile.dto'

/** 后端 `_po_to_dict` + params/mappings 的真实响应形状 */
const PROFILE_RAW = {
  id: 7,
  scope: 'api',
  algorithm_type: 'voice_llm',
  name: '接线测试_回环策略',
  description: '回环用例',
  status: 'online',
  cloned_from: null,
  config: {
    protocol: 'http',
    streaming: true,
    vendorAdapter: 'openai',
    audioConfig: { sampleRate: 16000 },
    meta: { request_template: '{}' },
  },
  params: [
    {
      id: 11,
      param_code: 'input_text',
      param_name: '输入文本',
      label: '问题',
      param_type: 'text',
      direction: 'input',
      required: true,
      default_value: '你好',
      validation: '{"max":200}',
      help_text: '用户问题',
      ui_order: 3,
      hidden: true,
      field_path: null,
    },
    {
      id: 12,
      param_code: 'answer',
      param_name: '回复文本',
      label: null,
      param_type: 'text',
      direction: 'output',
      required: false,
      default_value: null,
      validation: null,
      help_text: null,
      ui_order: 20,
      hidden: false,
      field_path: 'data.answer',
    },
  ],
  mappings: [
    {
      id: 31,
      source: 'api',
      source_direction: 'output',
      source_param: 'answer',
      target_param: 'text',
      dimension_id: 72,
      transform_type: 'none',
    },
    {
      id: 32,
      source: 'case',
      source_direction: 'input',
      source_param: 'input_text',
      target_param: 'question',
      dimension_id: null,
      transform_type: 'uppercase',
    },
  ],
}

/** 与表单 toInput 同口径：把读到的详情原样收成写侧草稿 */
function inputOf(profile: ReturnType<typeof toParamProfile>): ParamProfileInput {
  return {
    scope: profile.scope,
    algorithmType: profile.algorithmType,
    name: profile.name,
    description: profile.description,
    status: profile.status,
    config: profile.config,
    params: profile.params.map((param) => ({
      paramCode: param.paramCode,
      paramName: param.paramName,
      paramType: param.paramType,
      direction: param.direction,
      required: param.required,
      defaultValue: param.defaultValue,
      helpText: param.helpText,
      uiOrder: param.uiOrder,
      hidden: param.hidden,
      fieldPath: param.fieldPath,
      label: param.label,
      validationRules: param.validationRules,
    })),
    mappings: profile.mappings.map((mapping) => ({
      source: mapping.source,
      sourceDirection: mapping.sourceDirection,
      sourceParam: mapping.sourceParam,
      targetParam: mapping.targetParam,
      dimensionId: mapping.dimensionId,
      transformType: mapping.transformType,
    })),
  }
}

describe('参数策略读写回环（INT-2267）', () => {
  it('读侧保留 required / default / help / hidden / label / validation', () => {
    const profile = toParamProfile(PROFILE_RAW)
    expect(profile.params[0]).toMatchObject({
      required: true,
      defaultValue: '你好',
      helpText: '用户问题',
      hidden: true,
      label: '问题',
      validationRules: '{"max":200}',
    })
  })

  it('读侧保留映射来源与方向（case/device 不被归一成 api/output）', () => {
    const profile = toParamProfile(PROFILE_RAW)
    expect(profile.mappings.map((m) => [m.source, m.sourceDirection])).toEqual([
      ['api', 'output'],
      ['case', 'input'],
    ])
  })

  it('写侧原值回落：保存体与读到的字段逐字段一致', () => {
    const profile = toParamProfile(PROFILE_RAW)
    const dto = toParamProfileDto(inputOf(profile))

    expect(dto.params[0]).toEqual({
      param_code: 'input_text',
      param_name: '输入文本',
      param_type: 'text',
      direction: 'input',
      required: true,
      default_value: '你好',
      help_text: '用户问题',
      ui_order: 3,
      hidden: true,
      field_path: null,
      label: '问题',
      validation_rules: '{"max":200}',
    })
    expect(dto.params[1]).toMatchObject({
      param_code: 'answer',
      required: false,
      default_value: null,
      help_text: null,
      hidden: false,
      field_path: 'data.answer',
    })
    expect(dto.mappings[1]).toMatchObject({
      source: 'case',
      source_direction: 'input',
      source_param: 'input_text',
      target_param: 'question',
      transform_type: 'uppercase',
    })
  })

  it('写侧透传 config 快照（编辑不能抹掉既有快照）', () => {
    const profile = toParamProfile(PROFILE_RAW)
    const dto = toParamProfileDto(inputOf(profile))
    expect(dto.config).toEqual({
      protocol: 'http',
      streaming: true,
      vendorAdapter: 'openai',
      audioConfig: { sampleRate: 16000 },
      meta: { request_template: '{}' },
    })
  })

  it('草稿未带 label / validationRules 时请求体不含该键（而非写 null）', () => {
    const dto = toParamProfileDto({
      scope: 'api',
      algorithmType: 'voice_llm',
      name: 'x',
      description: null,
      status: 'online',
      params: [
        {
          paramCode: 'p',
          paramName: null,
          paramType: 'text',
          direction: 'output',
          required: false,
          defaultValue: null,
          helpText: null,
          uiOrder: 1,
          hidden: false,
          fieldPath: null,
        },
      ],
      mappings: [],
    })
    expect(dto.params[0]).not.toHaveProperty('label')
    expect(dto.params[0]).not.toHaveProperty('validation_rules')
  })
})
