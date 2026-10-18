/**
 * 评估策略节值序列化单测（11_用例域.md §5.1.3 用例承载契约）。
 * serializeEvaluationStrategy：none→清空；reference→{strategy_id, overrides?}；create→存量直载。
 */
import { describe, expect, it } from 'vitest'

import {
  serializeEvaluationStrategy,
  type EvaluationStrategyEditorValue,
} from '@/features/testcases/modals/strategy/evaluation-strategy-editor'

const dims = [
  { id: 1, name: '识别准确率', weight: 50, threshold: 80 },
  { id: 2, name: '语义理解', weight: 50, threshold: 80, llmJudgeConfig: { model: 'claude-3-sonnet', promptTemplate: 'accuracy' } },
]

const noise = {
  audioId: 'au-n1',
  audioName: '粉红噪声_94dB.wav',
  spl: 60,
  deviceIds: ['dev-1'],
  deviceNames: ['音频接口 A'],
  loop: true,
}

describe('serializeEvaluationStrategy（§5.1.3 契约）', () => {
  it('null / none → 清空 evaluationStrategy 与存量直载字段', () => {
    expect(serializeEvaluationStrategy(null)).toEqual({
      evaluationStrategy: null,
      dimensions: [],
      backgroundNoise: null,
    })
    expect(serializeEvaluationStrategy({ mode: 'none' })).toEqual({
      evaluationStrategy: null,
      dimensions: [],
      backgroundNoise: null,
    })
  })

  it('引用无覆盖 → evaluationStrategy = { strategy_id }，overrides 缺省', () => {
    const value: EvaluationStrategyEditorValue = {
      mode: 'reference',
      strategyId: 'str-1',
      overrides: null,
    }
    expect(serializeEvaluationStrategy(value)).toEqual({
      evaluationStrategy: { strategyId: 'str-1' },
      dimensions: [],
      backgroundNoise: null,
    })
  })

  it('引用+覆盖 → overrides 仅含覆盖字段', () => {
    const value: EvaluationStrategyEditorValue = {
      mode: 'reference',
      strategyId: 'str-1',
      overrides: { dimensions: dims },
    }
    const payload = serializeEvaluationStrategy(value)
    expect(payload.evaluationStrategy?.strategyId).toBe('str-1')
    expect(payload.evaluationStrategy?.overrides).toEqual({ dimensions: dims })
    expect(payload.dimensions).toEqual([])
  })

  it('引用+覆盖背景噪声 → overrides.background_noise', () => {
    const value: EvaluationStrategyEditorValue = {
      mode: 'reference',
      strategyId: 'str-3',
      overrides: { backgroundNoise: noise },
    }
    const payload = serializeEvaluationStrategy(value)
    expect(payload.evaluationStrategy?.overrides).toEqual({ backgroundNoise: noise })
  })

  it('新建（内联未存为策略）→ config.dimensions / config.background_noise 直载（无 strategy_id，向后兼容）', () => {
    const value: EvaluationStrategyEditorValue = {
      mode: 'create',
      inlineDimensions: dims,
      inlineBackgroundNoise: noise,
    }
    const payload = serializeEvaluationStrategy(value)
    expect(payload.evaluationStrategy).toBeNull()
    expect(payload.dimensions).toEqual(dims)
    expect(payload.backgroundNoise).toEqual(noise)
  })

  it('create 空内容 → 清空（等价未配置）', () => {
    expect(serializeEvaluationStrategy({ mode: 'create' })).toEqual({
      evaluationStrategy: null,
      dimensions: [],
      backgroundNoise: null,
    })
  })
})
