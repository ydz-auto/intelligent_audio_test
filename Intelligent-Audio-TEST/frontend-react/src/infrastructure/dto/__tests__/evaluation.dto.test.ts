/**
 * 评估维度 DTO 读取映射测试（INT-1506）：锁定 dimension.llm_judge_config → Domain llmJudgeConfig。
 * 审计 P3 口径：读侧不补魔法默认值（maxTokens/temperature 未下发即留空，缺省只由维度表单层给），
 * 不支持真实算法模型字典之外的占位模型。
 */
import { describe, expect, it } from 'vitest'

import { toDimension, type DimensionItemDto } from '@/infrastructure/dto/evaluation.dto'

const dto = (over: Partial<DimensionItemDto>): DimensionItemDto => ({
  id: 1,
  name: '识别准确率',
  description: null,
  keywords: null,
  dimension_type: 'main',
  parent_dimension_id: null,
  task_type_code: null,
  category_id: null,
  api_url: null,
  api_endpoints: null,
  api_settings: null,
  api_status: null,
  score_unit: null,
  type: null,
  result_type: null,
  result_min: null,
  result_max: null,
  decimal_places: null,
  weight: null,
  sort_order: null,
  estimated_exec_time: null,
  rule: null,
  required_inputs: null,
  output_fields: null,
  statistic_method: null,
  agg_denominator: null,
  exclude_rounds: null,
  associated_algorithms: null,
  llm_judge_config: null,
  status: true,
  created_at: '2026-10-01 10:00:00',
  updated_at: '2026-10-01 10:00:00',
  ...over,
})

describe('evaluation.dto toDimension（llm_judge_config 读侧）', () => {
  it('未下发配置 → llmJudgeConfig 为 null（参数卡留空，不注入占位模型）', () => {
    expect(toDimension(dto({})).llmJudgeConfig).toBeNull()
  })

  it('全空对象也视为未配置', () => {
    expect(toDimension(dto({ llm_judge_config: { model: '', prompt_template: '' } })).llmJudgeConfig).toBeNull()
  })

  it('只下发 model 时不编造 maxTokens/temperature（缺省只由表单层给）', () => {
    const dimension = toDimension(dto({ llm_judge_config: { model: 'voice_llm' } }))
    expect(dimension.llmJudgeConfig).toEqual({
      model: 'voice_llm',
      promptTemplate: '',
      maxTokens: undefined,
      temperature: undefined,
    })
  })

  it('camelCase / snake_case 双口径同收，数值字段原样透传', () => {
    const camel = toDimension(
      dto({ llm_judge_config: { model: 'voice_llm', promptTemplate: '模板A', maxTokens: 2048, temperature: 0.3 } })
    ).llmJudgeConfig
    const snake = toDimension(
      dto({ llm_judge_config: { model: 'voice_llm', prompt_template: '模板A', max_tokens: 2048, temperature: 0.3 } })
    ).llmJudgeConfig
    expect(camel).toEqual({ model: 'voice_llm', promptTemplate: '模板A', maxTokens: 2048, temperature: 0.3 })
    expect(snake).toEqual(camel)
  })
})
