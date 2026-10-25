/**
 * INT-1778：只读页签 DTO 单测（snake_case → camelCase）。
 * 锁定 GET /algorithm/params（含 C2 的 field_path）与 GET /algorithm/mappings 行契约。
 */
import { describe, expect, it } from 'vitest'

import {
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
      paramCode: 'response_audio',
      paramName: '回复音频',
      label: null,
      paramType: 'audio_file',
      direction: 'output',
      required: false,
      defaultValue: null,
      helpText: null,
      uiOrder: 21,
      hidden: false,
      fieldPath: null,
    })
  })

  it('field_path 落库后透传（C2/INT-1747）', () => {
    expect(toAlgorithmApiParam({ id: 1, field_path: 'data.items[0].text' }).fieldPath).toBe(
      'data.items[0].text'
    )
  })
})

describe('toAlgorithmApiMapping（GET /algorithm/mappings?source_type=api）', () => {
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
    })
  })

  it('未知 transform_type 收敛为 none（不让脏值进界面）', () => {
    expect(toAlgorithmApiMapping({ transform_type: 'weird' }).transformType).toBe('none')
  })
})
