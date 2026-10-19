/**
 * 用例列表项适配器单测（接线卡 INT-922 P2-1）：
 * testCaseListItemFromDto 携带 config / algorithm_params / reference_params
 * 原样透传（编辑回填与保存合并的数据源），轮次数/音频数由 config.rounds 派生。
 */
import { describe, expect, it } from 'vitest'

import { testCaseListItemFromDto } from '@/infrastructure/adapters/testCaseAdapter'
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
