/**
 * 用例列表项适配器单测（接线卡 INT-922 P2-1）：
 * testCaseListItemFromDto 携带 config / algorithm_params / reference_params
 * 原样透传（编辑回填与保存合并的数据源），轮次数/音频数由 config.rounds 派生。
 */
import { describe, expect, it } from 'vitest'

import {
  caseDetailFromDto,
  testCaseListItemFromDto,
} from '@/infrastructure/adapters/testCaseAdapter'
import type { TestCaseListItemDto } from '@/infrastructure/dto/testcase.dto'

const DTO: TestCaseListItemDto = {
  id: 'tc-1',
  name: '客厅_中文_命令集',
  description: '描述',
  group_id: 'g-1',
  group_name: '客厅',
  type: 'api',
  tags: ['客厅', '中文'],
  algorithm_type: 'voice_llm',
  total_duration: 120,
  config: {
    rounds: [
      {
        round_number: 1,
        audios: [
          { audio_id: 101, audio_name: '客厅_中文_命令集.wav', spl: 65 },
          { audio_id: 102, audio_name: '车内_导航_1人.wav', spl: 70 },
        ],
        evaluation: {
          enabled: true,
          dimensions: [
            { id: 5, name: 'LLM语义评分', weight: 50, threshold: 80 },
            { id: 11, name: '语音活动检测', weight: 50, threshold: 80 },
          ],
        },
      },
      {
        round_number: 2,
        audios: [{ audio_id: 103, audio_name: '会议室_多人_中文.wav', spl: 65 }],
        evaluation: { enabled: false, dimensions: [] },
      },
    ],
    dimensions: [],
  },
  algorithm_params: [
    { round_number: 1, params: [{ field_code: 'voiceprint', field_value: { audio_id: 101 } }] },
  ],
  reference_params: [{ round_number: 1, reference_params_path: 'refs/客厅/1.txt' }],
}

describe('testCaseListItemFromDto（INT-922）', () => {
  it('config / algorithmParams / referenceParams 原样透传，轮次/音频数派生', () => {
    const item = testCaseListItemFromDto(DTO)
    expect(item).toMatchObject({
      id: 'tc-1',
      groupId: 'g-1',
      algorithmType: 'voice_llm',
      rounds: 2,
      audioCount: 3,
    })
    // config 值内 snake_case 契约原样保留（编辑回填数据源）
    const configRounds = (item.config?.rounds ?? []) as Array<Record<string, unknown>>
    expect(configRounds).toHaveLength(2)
    expect(configRounds[0]).toMatchObject({
      round_number: 1,
      evaluation: { enabled: true, dimensions: [{ id: 5 }, { id: 11 }] },
    })
    expect(configRounds[0].audios as Array<{ audio_id: number }>).toHaveLength(2)
    expect(item.algorithmParams).toEqual(DTO.algorithm_params)
    expect(item.referenceParams).toEqual(DTO.reference_params)
  })

  it('config 缺省时透传 null，轮次默认 1', () => {
    const item = testCaseListItemFromDto({
      ...DTO,
      config: { rounds: null, dimensions: [] },
    })
    expect(item.config).toEqual({ rounds: null, dimensions: [] })
    expect(item.rounds).toBe(1)
    expect(item.audioCount).toBe(0)
  })
})

/**
 * infrastructure/adapters/testCaseAdapter 纯函数测试（10 规范 §5.2 / §9，INT-1066）。
 * 对位 task_bp.py get_case_detail 实测响应：case_name（无 name 字段）+ algorithm_results 扁平项
 * + devices。返工 P1：case_name → name 映射；P2：algorithm_results → 领域模型消费。
 */
describe('caseDetailFromDto', () => {
  it('后端返回 case_name（无 name 字段）→ 领域 name 正确映射（P1）', () => {
    const detail = caseDetailFromDto({
      test_case_id: '5412e6d4-be58-4446-9dc0-d40f739e919f',
      task_id: 1257,
      case_name: 'API用例',
      execution_status: 'failed',
      evaluation_status: 'completed',
      duration: null,
      score: null,
      algorithm_type: 'voice_llm',
      algorithm_results: [],
      devices: [],
    })
    expect(detail.name).toBe('API用例')
    expect(detail.caseId).toBe('5412e6d4-be58-4446-9dc0-d40f739e919f')
    expect(detail.taskId).toBe(1257)
    // P3：duration null 保持 null（头部不渲染「耗时」，旧 Vue 同口径），不做 ?? 0 兜底
    expect(detail.duration).toBeNull()
    expect(detail.algorithmType).toBe('voice_llm')
  })

  it('case_name 缺省时回退 name 字段（兼容留底）', () => {
    const detail = caseDetailFromDto({
      test_case_id: 'case-x',
      task_id: 1,
      name: '旧字段用例',
      execution_status: 'completed',
      evaluation_status: 'completed',
      duration: 5,
      score: 90,
      algorithm_type: null,
      algorithm_results: [],
      devices: [],
    } as never)
    expect(detail.name).toBe('旧字段用例')
  })

  it('algorithm_results snake_case 扁平项 → camelCase 领域数组（P2）', () => {
    const detail = caseDetailFromDto({
      test_case_id: 'case-y',
      task_id: 2,
      case_name: 'API用例二',
      execution_status: 'completed',
      evaluation_status: 'completed',
      duration: 10,
      score: null,
      algorithm_type: 'voice_llm',
      algorithm_results: [
        {
          param_code: 'round_count',
          param_type: 'number',
          label: 'round count',
          value: 2,
        },
        {
          param_code: 'rounds',
          param_type: 'json',
          label: 'round results',
          value: [{ round_number: 1, success: true }],
        },
      ],
      devices: [],
    })
    expect(detail.algorithmResults).toEqual([
      { paramCode: 'round_count', paramType: 'number', label: 'round count', value: 2 },
      { paramCode: 'rounds', paramType: 'json', label: 'round results', value: [{ round_number: 1, success: true }] },
    ])
  })

  it('devices 非空 → 设备结果行照常映射', () => {
    const detail = caseDetailFromDto({
      test_case_id: 'case-z',
      task_id: 3,
      case_name: 'E2E用例',
      execution_status: 'completed',
      evaluation_status: 'completed',
      duration: 8,
      score: 85,
      algorithm_type: null,
      algorithm_results: [],
      devices: [
        {
          device_id: 10,
          device_name: 'pura90豆包',
          status: 'pass',
          duration: 8,
          score: 85,
          metrics: [{ dimension: '清晰度', round: null, value: '0.55' }],
          asr_reference: null,
          translation_reference: null,
          audio_results: [],
        },
      ],
    })
    expect(detail.devices).toHaveLength(1)
    expect(detail.devices[0]).toMatchObject({
      deviceId: 10,
      deviceName: 'pura90豆包',
      status: 'pass',
      metrics: [{ dimension: '清晰度', value: '0.55' }],
    })
  })
})
