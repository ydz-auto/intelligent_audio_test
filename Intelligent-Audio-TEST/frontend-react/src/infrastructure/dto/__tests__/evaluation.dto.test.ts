/**
 * 评估维度 DTO 读取映射测试（INT-1506）：锁定 dimension.llm_judge_config → Domain llmJudgeConfig。
 * 审计 P3 口径：读侧不补魔法默认值（maxTokens/temperature 未下发即留空，缺省只由维度表单层给），
 * 不支持真实算法模型字典之外的占位模型。
 */
import { describe, expect, it } from 'vitest'

import {
  toDimension,
  toDimensionOptionsList,
  type DimensionItemDto,
} from '@/infrastructure/dto/evaluation.dto'

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

describe('evaluation.dto api_settings / api_endpoints 归一（INT-2248）', () => {
  it('body_template → bodyTemplate（后端/运行时只认 snake 键，表单只认 camel）', () => {
    const dimension = toDimension(
      dto({
        api_settings: {
          method: 'POST',
          timeout: 30000,
          body_template: { rounds: [{ answer: '{{answer}}' }], model: '{{model}}' },
        },
      })
    )
    expect(dimension.apiSettings).toEqual({
      method: 'POST',
      timeout: 30000,
      bodyTemplate: { rounds: [{ answer: '{{answer}}' }], model: '{{model}}' },
    })
  })

  it('api_endpoints 的 snake 键归一为 camel，未知端点字段原样保留', () => {
    const dimension = toDimension(
      dto({
        api_endpoints: [
          {
            url: 'https://api.example.com/eval',
            name: '主端点',
            priority: 1,
            max_process: 2,
            max_timeout: 30,
            max_audio_duration: 60,
            status: 'online',
            health_score: 99,
          },
        ],
      })
    )
    expect(dimension.apiEndpoints).toEqual([
      {
        url: 'https://api.example.com/eval',
        name: '主端点',
        priority: 1,
        maxProcess: 2,
        maxTimeout: 30,
        maxAudioDuration: 60,
        status: 'online',
        health_score: 99,
      },
    ])
  })

  it('端点只有 endpoint 别名时回填为 url（与后端 get_endpoint_url 同口径）', () => {
    const dimension = toDimension(
      dto({ api_endpoints: [{ endpoint: 'https://api.example.com/alias', max_process: 2 }] })
    )
    expect(dimension.apiEndpoints?.[0].url).toBe('https://api.example.com/alias')
    expect(dimension.apiEndpoints?.[0].maxProcess).toBe(2)
  })

  it('api_settings 为 JSON 字符串（历史数据）时也能解析回 bodyTemplate', () => {
    const dimension = toDimension(
      dto({ api_settings: JSON.stringify({ method: 'POST', body_template: { rounds: [] } }) })
    )
    expect(dimension.apiSettings).toEqual({
      method: 'POST',
      bodyTemplate: { rounds: [] },
    })
  })
})

describe('evaluation.dto requires_audio → requiresAudio（INT-1843）', () => {
  it('列表端点下发 requires_audio 时映射为 requiresAudio', () => {
    expect(toDimension(dto({ requires_audio: true })).requiresAudio).toBe(true)
    expect(toDimension(dto({ requires_audio: false })).requiresAudio).toBe(false)
  })

  it('列表端点未下发 requires_audio（实测 63 条均无该键）时 requiresAudio=false', () => {
    expect(toDimension(dto({})).requiresAudio).toBe(false)
  })

  it('options 端点 requires_audio → EvaluationDimensionItem.requiresAudio', () => {
    const items = toDimensionOptionsList({
      dimensions: [
        { id: 121, name: '拒识成功数量', dimension_type: 'main', requires_audio: true },
        { id: 1, name: '识别准确率', dimension_type: 'main', requires_audio: false },
      ],
    })
    expect(items.map((d) => d.requiresAudio)).toEqual([true, false])
  })

  it('options 端点 parent_dimension_id/category_id 映射主/子层级与分类', () => {
    const items = toDimensionOptionsList({
      dimensions: [
        { id: 1, name: '识别准确率', dimension_type: 'main', category_id: 2 },
        {
          id: 11,
          name: '字准率',
          dimension_type: 'sub',
          parent_dimension_id: 1,
          category_id: 2,
        },
      ],
    })
    expect(items[0].categoryId).toBe(2)
    expect(items[0].parentDimensionId).toBeNull()
    expect(items[1].parentDimensionId).toBe(1)
    expect(items[1].dimensionType).toBe('sub')
  })
})
