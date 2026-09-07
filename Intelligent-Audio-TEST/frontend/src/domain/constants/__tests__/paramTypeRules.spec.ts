/**
 * paramTypeRules 单元测试 —— 参数键名 → 字段类型推断（领域纯函数）
 * 与后端 report_helpers.py 的 _PARAM_TYPE_KEYWORD_RULES 保持一致
 */
import { describe, it, expect } from 'vitest'
import { inferParamType, PARAM_TYPE_KEYWORD_RULES, TIMELINE_PARAM_TYPES } from '../paramTypeRules'
import { FieldType } from '@/domain/enums'

describe('PARAM_TYPE_KEYWORD_RULES', () => {
  it('规则按关键词顺序定义（rttm/stm/audio/time）', () => {
    expect(PARAM_TYPE_KEYWORD_RULES.map(r => r.keyword)).toEqual(['rttm', 'stm', 'audio', 'time'])
  })
})

describe('inferParamType', () => {
  it('按关键词命中字段类型', () => {
    expect(inferParamType('rttm_output')).toBe(FieldType.RTTM)
    expect(inferParamType('stm_file')).toBe(FieldType.STM)
    expect(inferParamType('audio_file_path')).toBe(FieldType.AUDIO)
    // 'timestamp' 含 'time' → TIMESTAMP
    expect(inferParamType('timestamp')).toBe(FieldType.TIMESTAMP)
    expect(inferParamType('start_time')).toBe(FieldType.TIMESTAMP)
  })

  it('大小写不敏感', () => {
    expect(inferParamType('AUDIO_FILE')).toBe(FieldType.AUDIO)
    expect(inferParamType('Start_Time')).toBe(FieldType.TIMESTAMP)
  })

  it('rttm 优先于 audio（若同时包含）', () => {
    // 'audio_rttm' 同时命中 audio 与 rttm，规则顺序决定 rttm 优先
    expect(inferParamType('audio_rttm')).toBe(FieldType.RTTM)
  })

  it('未命中返回 TEXT', () => {
    expect(inferParamType('transcript')).toBe(FieldType.TEXT)
    expect(inferParamType('similarity')).toBe(FieldType.TEXT)
    expect(inferParamType('')).toBe(FieldType.TEXT)
  })
})

describe('TIMELINE_PARAM_TYPES', () => {
  it('包含时间轴可展示的字段类型', () => {
    expect(TIMELINE_PARAM_TYPES).toEqual([FieldType.RTTM, FieldType.STM, FieldType.JSON])
  })
})