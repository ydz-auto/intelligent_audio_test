/**
 * INT-1778：只读页签 DTO 单测（snake_case → camelCase）。
 * 锁定 GET /algorithm/params（含 C2 的 field_path）与 GET /algorithm/mappings 行契约。
 */
import { describe, expect, it } from 'vitest'

import {
  rowsFromPayload,
  toAlgorithmApiMapping,
  toAlgorithmApiParam,
} from '../api-algorithm-readonly.dto'

describe('toAlgorithmApiParam（GET /algorithm/params?param_type=api）', () => {
  it('全字段映射，field_path 未落库为 null（界面显示「—」）', () => {
    expect(
      toAlgorithmApiParam({
        id: 9,
        algorithm_type: 'voice_llm',
        param_code: 'response_audio',
        param_name: '回复音频',
        label: null,
        param_type: 'audio_file',
        direction: 'output',
        required: false,
        field_path: null,
        ui_order: 21,
        hidden: false,
      })
    ).toEqual({
      id: 9,
      deviceId: null,
      paramCode: 'response_audio',
      paramName: '回复音频',
      label: null,
      paramType: 'audio_file',
      direction: 'output',
      required: false,
      defaultValue: null,
      helpText: null,
      validationRules: null,
      uiOrder: 21,
      hidden: false,
      fieldPath: null,
    })
  })

  it('validation_rules 读到后透传（无编辑控件，保存时按原值回写）', () => {
    expect(
      toAlgorithmApiParam({ id: 2, param_code: 'asr_text', validation_rules: '{"min_length":1}' })
        .validationRules
    ).toBe('{"min_length":1}')
    // 后端 `_po_to_dict` 的另一套键名 `validation`
    expect(
      toAlgorithmApiParam({ id: 3, param_code: 'asr_text', validation: '{"max_length":9}' })
        .validationRules
    ).toBe('{"max_length":9}')
  })

  it('field_path 落库后透传（C2/INT-1747）', () => {
    expect(toAlgorithmApiParam({ id: 1, field_path: 'data.items[0].text' }).fieldPath).toBe(
      'data.items[0].text'
    )
  })

  it('validation_rules 透传（后端 _serialize_params 键名），旧键 validation 兼容（INT-2281）', () => {
    expect(
      toAlgorithmApiParam({ id: 2, validation_rules: '{"min":1}' }).validationRules
    ).toBe('{"min":1}')
    expect(toAlgorithmApiParam({ id: 3, validation: '{"max":9}' }).validationRules).toBe(
      '{"max":9}'
    )
    expect(toAlgorithmApiParam({ id: 4, validation_rules: null, validation: '' }).validationRules)
      .toBeNull()
  })
})

describe('rowsFromPayload（/algorithm/params 与 /algorithm/mappings 的 data 形态）', () => {
  it('裸数组（现有 gRPC 返回值）直接透传', () => {
    expect(rowsFromPayload([{ id: 1 }])).toEqual([{ id: 1 }])
  })

  it('兼容统一分页信封 { items, total }', () => {
    expect(rowsFromPayload({ items: [{ id: 2 }], total: 1 })).toEqual([{ id: 2 }])
  })

  it('未知形态返回空数组（不抛错）', () => {
    expect(rowsFromPayload(null)).toEqual([])
    expect(rowsFromPayload({ total: 3 })).toEqual([])
  })
})

describe('toAlgorithmApiMapping（GET /algorithm/mappings?source_type=evaluation）', () => {
  it('映射行转 camelCase；后端不下发 dimension_name 时为 null', () => {
    expect(
      toAlgorithmApiMapping({
        id: 7,
        algorithm_type: 'voice_llm',
        source: 'api',
        source_param: 'response_audio',
        source_direction: 'output',
        dimension_id: 72,
        target_param: 'audio_file',
        transform_type: 'base64',
      })
    ).toEqual({
      id: 7,
      source: 'api',
      sourceDirection: 'output',
      sourceParam: 'response_audio',
      paramName: null,
      dimensionId: 72,
      dimensionName: null,
      targetParam: 'audio_file',
      targetParamName: null,
      transformType: 'base64',
      deviceId: null,
      apiId: null,
    })
  })

  it('api_id 透传（区分算法级 / 本 API 覆盖行；INT-2281）', () => {
    expect(toAlgorithmApiMapping({ source: 'device', api_id: 7 }).apiId).toBe(7)
    expect(toAlgorithmApiMapping({ source: 'device', api_id: null }).apiId).toBeNull()
  })

  it('未知 transform_type 收敛为 none（不让脏值进界面）', () => {
    expect(toAlgorithmApiMapping({ transform_type: 'weird' }).transformType).toBe('none')
  })
})
