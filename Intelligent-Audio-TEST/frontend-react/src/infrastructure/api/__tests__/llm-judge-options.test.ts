/**
 * LLM Judge 可选值来源（INT-1658）：候选集收敛在 infrastructure 层（后端口径，当前留桩待接线），
 * 组件不再自持模型/Prompt 枚举；存量值不在候选集时须并入保证回显。
 */
import { describe, expect, it } from 'vitest'

import {
  getLlmJudgeOptions,
  withCurrentOption,
} from '@/infrastructure/api/llm-judge-options'

describe('llm-judge-options', () => {
  it('候选集由 infrastructure 层提供（模型 + Prompt 模板均非空）', () => {
    const options = getLlmJudgeOptions()
    expect(options.models.length).toBeGreaterThan(0)
    expect(options.promptTemplates.length).toBeGreaterThan(0)
    // 契约形态：下拉项即字符串数组（后端枚举端点落地后同形态）
    expect(options.models.every((m) => typeof m === 'string' && m.length > 0)).toBe(true)
    expect(
      options.promptTemplates.every((t) => typeof t === 'string' && t.length > 0)
    ).toBe(true)
  })

  it('存量值不在候选集 → 并入首位（Select 回显不空白）；已在集内/空值 → 原样', () => {
    expect(withCurrentOption(['a', 'b'], 'legacy-model')).toEqual(['legacy-model', 'a', 'b'])
    expect(withCurrentOption(['a', 'b'], 'a')).toEqual(['a', 'b'])
    expect(withCurrentOption(['a', 'b'], '')).toEqual(['a', 'b'])
    expect(withCurrentOption(['a', 'b'], null)).toEqual(['a', 'b'])
    expect(withCurrentOption(['a', 'b'], undefined)).toEqual(['a', 'b'])
  })
})
