/**
 * 算法选项 DTO 映射测试（接线·壳 INT-607）：
 * 锁定 GET /algorithm/options 真实契约（实测 2026-10-17）——
 * data.algorithms: [{ value, name, group_id, group_name, icon }]；
 * value=算法类型码 → Domain id（业务列表 algorithm_type 过滤参数同源）。
 */
import { describe, expect, it } from 'vitest'

import { toAlgorithmOption } from '@/infrastructure/dto/algorithm.dto'

describe('algorithm.dto toAlgorithmOption', () => {
  it('value 落 Domain id、name 平移、group_name 作 description（真实契约）', () => {
    const option = toAlgorithmOption({
      value: 'voice_llm',
      name: '小艺语音大模型',
      group_id: 1,
      group_name: '语音识别',
      icon: null,
    })
    expect(option).toEqual({
      id: 'voice_llm',
      name: '小艺语音大模型',
      version: '',
      description: '语音识别',
      enabled: true,
    })
  })

  it('group_name 缺省为空串（未分组选项不破坏副行渲染）', () => {
    const option = toAlgorithmOption({
      value: 'eval_ensemble',
      name: '多维评估集成',
    })
    expect(option.id).toBe('eval_ensemble')
    expect(option.description).toBe('')
    expect(option.enabled).toBe(true)
  })
})
