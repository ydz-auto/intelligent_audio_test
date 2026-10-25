/**
 * INT-1868 裁定 A：LLM Judge 口径契约测试。
 *
 * - 维度列表 / 维度选项接口的后端派生布尔 llm_judge → Domain llmJudge
 * - 维度保存载荷不再写 llm_judge_config（历史值不随维度保存重写）
 */
import { describe, expect, it } from 'vitest'
import { toDimension, toDimensionDto, toDimensionOptions } from '../evaluationAdapter'

describe('evaluationAdapter llmJudge（INT-1868）', () => {
  it('toDimension：后端派生 llm_judge → llmJudge，缺失回落 false', () => {
    const llm = toDimension({ id: 164, name: '频次 LLM 判分', result_type: 1, llm_judge: true })
    expect(llm.llmJudge).toBe(true)
    expect(llm.resultType).toBe(1)

    const normal = toDimension({ id: 121, name: '拒识成功数量', result_type: 1 })
    expect(normal.llmJudge).toBe(false)
  })

  it('toDimensionOptions：选项接口同样映射 llm_judge', () => {
    const result = toDimensionOptions({
      dimensions: [
        { id: 164, name: '频次 LLM 判分', llm_judge: true },
        { id: 121, name: '拒识成功数量', llm_judge: false },
      ],
    })
    expect(result.dimensions[0].llmJudge).toBe(true)
    expect(result.dimensions[1].llmJudge).toBe(false)
  })

  it('toDimensionDto：不再提交 llm_judge_config（历史残留也不重写）', () => {
    const dto = toDimensionDto({
      id: 164,
      name: '频次 LLM 判分',
      resultType: 1,
      llmJudgeConfig: { model: 'gpt-4', promptTemplate: 'default', maxTokens: 1024, temperature: 0.7 },
    })
    expect(dto.result_type).toBe(1)
    expect(dto).not.toHaveProperty('llm_judge_config')
  })
})
