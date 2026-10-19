/**
 * 算法配置页常量单测（features/algorithm-config）。
 * 校验状态元数据/枚举选项与文案口径（17_配置运维.md §8/§10）。
 */
import { describe, expect, it } from 'vitest'

import {
  ALGORITHM_STATUS_META,
  ALGORITHM_STATUS_OPTIONS,
  CASE_PARAM_SCOPE_OPTIONS,
  CASE_PARAM_TYPE_OPTIONS,
  DEVICE_PARAM_TYPE_OPTIONS,
  PARAM_DIRECTION_OPTIONS,
  REFERENCE_PARAM_MERGE_OPTIONS,
  REFERENCE_PARAM_TYPE_OPTIONS,
  TRANSFORM_TYPE_OPTIONS,
  DEFAULT_PAGE_SIZE,
} from '@/features/algorithm-config/constants'

describe('algorithm-config constants', () => {
  it('状态元数据覆盖 online/offline 且文案中文', () => {
    expect(ALGORITHM_STATUS_META.online.label).toBe('上线')
    expect(ALGORITHM_STATUS_META.offline.label).toBe('下线')
    expect(ALGORITHM_STATUS_META.online.badgeVariant).toBe('success')
    expect(ALGORITHM_STATUS_META.offline.badgeVariant).toBe('neutral')
  })

  it('状态筛选选项与元数据一一对应', () => {
    expect(ALGORITHM_STATUS_OPTIONS).toHaveLength(2)
    for (const option of ALGORITHM_STATUS_OPTIONS) {
      expect(ALGORITHM_STATUS_META[option.value].label).toBe(option.label)
    }
  })

  it('设备/API 参数类型包含音频流/音频文件等核心形态', () => {
    const values = DEVICE_PARAM_TYPE_OPTIONS.map((o) => o.value)
    expect(values).toContain('audio_stream')
    expect(values).toContain('audio_file')
    expect(values).toContain('json')
  })

  it('用例参数类型覆盖数字/滑块/开关/音频选择', () => {
    const values = CASE_PARAM_TYPE_OPTIONS.map((o) => o.value)
    expect(values).toEqual(
      expect.arrayContaining(['text', 'number', 'slider', 'switch', 'audio_select'])
    )
  })

  it('用例参数适用范围含通用/API/E2E 中文文案', () => {
    expect(CASE_PARAM_SCOPE_OPTIONS).toEqual([
      { value: 'common', label: '通用' },
      { value: 'api', label: 'API' },
      { value: 'e2e', label: 'E2E' },
    ])
  })

  it('转换类型枚举覆盖 none/uppercase/lowercase/json_parse', () => {
    const values = TRANSFORM_TYPE_OPTIONS.map((o) => o.value)
    expect(values).toEqual(['none', 'uppercase', 'lowercase', 'json_parse'])
  })

  it('参考参数类型与合并方式中文文案齐备', () => {
    const types = REFERENCE_PARAM_TYPE_OPTIONS.map((o) => o.value)
    expect(types).toEqual(expect.arrayContaining(['text', 'audio', 'rttm', 'stm']))
    const merges = REFERENCE_PARAM_MERGE_OPTIONS.map((o) => o.value)
    expect(merges).toEqual(['join', 'collect', 'first'])
  })

  it('方向选项为输入/输出', () => {
    expect(PARAM_DIRECTION_OPTIONS).toEqual([
      { value: 'input', label: '输入' },
      { value: 'output', label: '输出' },
    ])
  })

  it('默认每页 20 条（§3.2 catch 20）', () => {
    expect(DEFAULT_PAGE_SIZE).toBe(20)
  })
})
