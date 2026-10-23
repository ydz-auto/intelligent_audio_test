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

  it('getAlgorithmLabel：真实算法字典 id → 中文名，未登记/无字典原样返回', () => {
    const labels = { voice_llm: '小样本分类模型', asr: '通用识别引擎' }
    expect(getAlgorithmLabel('voice_llm', labels)).toBe('小样本分类模型')
    expect(getAlgorithmLabel('asr', labels)).toBe('通用识别引擎')
    expect(getAlgorithmLabel('unknown-algo', labels)).toBe('unknown-algo')
    expect(getAlgorithmLabel('voice_llm')).toBe('voice_llm')
    expect(getAlgorithmLabel(null, labels)).toBe('—')
  })

  it('视图白名单仅含 by-group / by-tag', () => {
    expect(TEST_CASES_TAB_WHITELIST).toEqual(['by-group', 'by-tag'])
  })
})
