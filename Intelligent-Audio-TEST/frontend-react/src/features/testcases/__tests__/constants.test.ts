/**
 * 用例域常量测试（11_用例域.md §8 中文文案源）：时长格式化、算法标签映射、视图白名单。
 */
import { describe, expect, it } from 'vitest'

import {
  formatCaseDuration,
  getAlgorithmLabel,
  TEST_CASES_TAB_WHITELIST,
} from '@/features/testcases/constants'

describe('testcases constants', () => {
  it('formatCaseDuration：秒 → {x}m {y}s，0/null 显 —', () => {
    expect(formatCaseDuration(156)).toBe('2m 36s')
    expect(formatCaseDuration(48)).toBe('48s')
    expect(formatCaseDuration(120)).toBe('2m')
    expect(formatCaseDuration(0)).toBe('—')
    expect(formatCaseDuration(null)).toBe('—')
    expect(formatCaseDuration(undefined)).toBe('—')
  })

  it('getAlgorithmLabel：真实选项表 value→name 命中返回中文名；未命中/无表返回 null（不回落类型码）', () => {
    const labels = { voice_llm: '小艺语音大模型', asr_v3: '通用识别引擎' }
    expect(getAlgorithmLabel('voice_llm', labels)).toBe('小艺语音大模型')
    expect(getAlgorithmLabel('asr_v3', labels)).toBe('通用识别引擎')
    // 未登记 / 选项未加载 / 空类型：一律 null，由调用方隐藏徽章（INT-1687）
    expect(getAlgorithmLabel('unknown-algo', labels)).toBeNull()
    expect(getAlgorithmLabel('voice_llm')).toBeNull()
    expect(getAlgorithmLabel('voice_llm', {})).toBeNull()
    expect(getAlgorithmLabel(null, labels)).toBeNull()
  })

  it('视图白名单仅含 by-group / by-tag', () => {
    expect(TEST_CASES_TAB_WHITELIST).toEqual(['by-group', 'by-tag'])
  })
})
