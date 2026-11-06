/**
 * 算法选项 DTO 映射测试（接线·壳 INT-607）：
 * 锁定 GET /algorithm/options 真实契约（实测 2026-10-17）——
 * data.algorithms: [{ value, name, group_id, group_name, icon }]；
 * value=算法类型码 → Domain AlgorithmSwitchOption.value（全局算法 store 同源）。
 */
import { describe, expect, it } from 'vitest'

import { toAlgorithmOption } from '@/infrastructure/dto/algorithm.dto'

describe('algorithm.dto toAlgorithmOption', () => {
  it('value/name 平移 → Domain AlgorithmSwitchOption（真实契约）', () => {
    const option = toAlgorithmOption({
      value: 'voice_llm',
      name: '小艺语音大模型',
      group_id: 1,
      group_name: '语音识别',
      icon: null,
    })
    expect(option).toEqual({
      value: 'voice_llm',
      name: '小艺语音大模型',
    })
  })

  it('缺省字段容错：仅 value/name 也能映射', () => {
    const option = toAlgorithmOption({
      value: 'eval_ensemble',
      name: '多维评估集成',
    })
    expect(option.value).toBe('eval_ensemble')
    expect(option.name).toBe('多维评估集成')
  })
})
