/**
 * 用例轮次配置序列化单测（INT-877/INT-996 合流）：
 * - defaultRounds：三组字段（audios + algorithmParams + noise）；
 * - roundDraftFromConfig / audioDraftFromConfig：真实音频回填 + 算法参数/噪声草稿；
 * - roundsFromConfig：按轮读独立列 algorithmParams；
 * - roundsToConfig：音频草稿保存生效（config.rounds[].audios），噪声段写入
 *   segment 级 audios[0].background_noise/interferers，新选维度补 name；
 * - toStrategyOverridesDto：覆盖键 backgroundNoise → background_noise。
 */
import { describe, expect, it } from 'vitest'

import {
  audioDraftFromConfig,
  defaultRounds,
  roundDraftFromConfig,
  roundsFromConfig,
  roundsToConfig,
  toStrategyOverridesDto,
} from '@/domain/lib/testcase-round-config'
import { emptyRoundNoise } from '@/domain/models/testCaseRound'
import type { RoundDraft } from '@/domain/models/testCaseRound'

describe('testcase round config 序列化（INT-877/996 合流）', () => {
  describe('defaultRounds', () => {
    it('新建态默认单轮空评估 + 空音频 + 空算法参数/噪声', () => {
      expect(defaultRounds()).toEqual([
        {
          number: 1,
          audioCount: 0,
          dimensionCount: 0,
          evaluation: { enabled: true, selectedIds: [], params: {} },
          audios: [],
          algorithmParams: [],
          noise: emptyRoundNoise(),
        },
      ])
    })
  })

  describe('audioDraftFromConfig', () => {
    it('真实音频字段回填（audio_id/audio_name/spl/playback_device_id/name/play_order）', () => {
      const draft = audioDraftFromConfig(
        {
          audio_id: 101,
          audio_name: '客厅_中文_命令集.wav',
          spl: 72,
          playback_device_id: 3,
          playback_device_name: '蓝牙音箱',
          play_order: 1,
        },
        0
      )
      expect(draft).toMatchObject({
        id: 'backfill-0',
        audioId: 101,
        audioName: '客厅_中文_命令集.wav',
        spl: 72,
        deviceId: '3',
        deviceName: '蓝牙音箱',
        playOrder: 1,
      })
    })

    it('缺省字段回退（spl 默认 65、无设备 deviceId 空串）', () => {
      const draft = audioDraftFromConfig({ audio_name: '仅文件名.wav' }, 2)
      expect(draft).toMatchObject({
        id: 'backfill-2',
        audioId: null,
        audioName: '仅文件名.wav',
        spl: 65,
        deviceId: '',
        deviceName: null,
      })
    })
  })

  describe('roundDraftFromConfig', () => {
    it('回填轮次数 + 音频摘要 + 评估维度（含 llmJudgeConfig）', () => {
      const draft = roundDraftFromConfig(
        {
          round_number: 2,
          audios: [{ audio_id: 1, audio_name: 'a.wav' }],
          evaluation: {
            enabled: true,
            dimensions: [
              { id: 2, name: '语义理解', weight: 40, threshold: 90, llmJudgeConfig: { model: 'claude-3-sonnet', promptTemplate: 'accuracy' } },
            ],
          },
        },
        1,
        []
      )
      expect(draft.number).toBe(2)
      expect(draft.audioCount).toBe(1)
      expect(draft.audios).toHaveLength(1)
      expect(draft.audios[0].audioId).toBe(1)
      expect(draft.dimensionCount).toBe(1)
      expect(draft.evaluation.selectedIds).toEqual([2])
      expect(draft.evaluation.params[2]).toMatchObject({
        weight: 40,
        threshold: 90,
        model: 'claude-3-sonnet',
        promptTemplate: 'accuracy',
      })
    })

    it('INT-996 算法参数独立列 + 噪声草稿按轮读取', () => {
      const draft = roundDraftFromConfig(
        {
          round_number: 1,
          background_noise: { audio_name: '粉红噪声.wav', spl: 60, device_ids: [1] },
          interferers: [{ audio_name: '干扰人1', spl: 70 }],
        },
        0,
        [{ field_code: 'asr', field_value: 'wer' }]
      )
      expect(draft.algorithmParams).toEqual([{ field_code: 'asr', field_value: 'wer' }])
      expect(draft.noise.backgroundNoise).toMatchObject({
        audioName: '粉红噪声.wav',
        spl: 60,
        deviceIds: [1],
      })
      expect(draft.noise.interferers).toHaveLength(1)
      expect(draft.noise.interferers[0]).toMatchObject({ audioName: '干扰人1', spl: 70 })
    })
  })

  describe('roundsFromConfig', () => {
    it('空 config.rounds → 默认轮次', () => {
      expect(roundsFromConfig(null, undefined)).toEqual(defaultRounds())
      expect(roundsFromConfig({ rounds: [] }, undefined)).toEqual(defaultRounds())
    })

    it('按轮读独立列 algorithmParams（round_number 匹配）', () => {
      const drafts = roundsFromConfig(
        {
          rounds: [{ round_number: 1, audios: [{ audio_id: 1 }] }, { round_number: 2 }],
        },
        [
          { round_number: 1, params: [{ field_code: 'asr', field_value: 'wer' }] },
          { round_number: 2, params: [{ field_code: 'topn', field_value: 5 }] },
        ]
      )
      expect(drafts).toHaveLength(2)
      expect(drafts[0].algorithmParams).toEqual([{ field_code: 'asr', field_value: 'wer' }])
      expect(drafts[1].algorithmParams).toEqual([{ field_code: 'topn', field_value: 5 }])
      expect(drafts[0].audios[0]).toMatchObject({ audioId: 1 })
    })
  })

  describe('roundsToConfig', () => {
    const dimNameById = new Map<number, string>([
      [1, '识别准确率'],
      [9, 'LLM复核测试维度'],
    ])

    it('音频草稿保存生效（config.rounds[].audios 序列化真实字段）', () => {
      const drafts: RoundDraft[] = [
        {
          number: 1,
          audioCount: 1,
          dimensionCount: 0,
          evaluation: { enabled: true, selectedIds: [], params: {} },
          audios: [
            {
              id: 'backfill-0',
              audioId: 101,
              audioName: '客厅_中文_命令集.wav',
              spl: 72,
              deviceId: '3',
              deviceName: '蓝牙音箱',
              playOrder: 1,
            },
          ],
          algorithmParams: [],
          noise: emptyRoundNoise(),
        },
      ]
      const config = roundsToConfig(drafts, null, dimNameById)
      expect(config).toHaveLength(1)
      expect(config[0].audios).toEqual([
        {
          audio_id: 101,
          audio_name: '客厅_中文_命令集.wav',
          spl: 72,
          playback_device_id: '3',
          playback_device_name: '蓝牙音箱',
          play_order: 1,
        },
      ])
    })

    it('合并原始轮次：音频编辑字段覆盖 + noise 草稿写 segment 级（INT-996）', () => {
      const drafts: RoundDraft[] = [
        {
          number: 1,
          audioCount: 1,
          dimensionCount: 0,
          evaluation: { enabled: true, selectedIds: [], params: {} },
          audios: [
            {
              id: 'backfill-0',
              audioId: 101,
              audioName: '客厅_中文_命令集.wav',
              spl: 72,
              deviceId: '3',
              deviceName: '蓝牙音箱',
              playOrder: 1,
            },
          ],
          algorithmParams: [],
          noise: {
            backgroundNoise: {
              audioId: 7,
              audioName: '粉红噪声.wav',
              spl: 60,
              deviceIds: [1],
              loop: true,
            },
            voiceprint: { enabled: false, audioId: null, audioName: null, playbackDeviceId: null, spl: 75, waitSec: 5 },
            interferers: [{ id: 'ifr-1', audioId: null, audioName: '干扰人1', playbackDeviceId: null, spl: 70, startDelay: 0, loop: false }],
          },
        },
      ]
      const originalRounds = [
        {
          round_number: 1,
          audios: [{ audio_id: 101, spl: 60, interferers: [{ name: '旧干扰人' }] }],
          background_noise: { audio_name: '旧粉红噪声.wav' },
        },
      ]
      const config = roundsToConfig(drafts, originalRounds, dimNameById)
      expect(config[0]).toMatchObject({ round_number: 1 })
      // 音频编辑字段覆盖（spl 60 → 72），噪声段按 noise 草稿写 segment 级
      expect((config[0] as { audios?: unknown[] }).audios).toEqual([
        {
          audio_id: 101,
          audio_name: '客厅_中文_命令集.wav',
          spl: 72,
          playback_device_id: '3',
          playback_device_name: '蓝牙音箱',
          play_order: 1,
          background_noise: {
            audio_id: 7,
            audio_name: '粉红噪声.wav',
            spl: 60,
            device_ids: [1],
            loop: true,
          },
          interferers: [
            { audio_name: '干扰人1', spl: 70, start_delay: 0, loop: false },
          ],
        },
      ])
    })

    it('轮次内新选维度序列化补 name（P3-3），存量维度保留原 name', () => {
      const drafts: RoundDraft[] = [
        {
          number: 1,
          audioCount: 0,
          dimensionCount: 1,
          evaluation: {
            enabled: true,
            selectedIds: [9],
            params: { 9: { weight: 50, threshold: 80 } },
          },
          audios: [],
          algorithmParams: [],
          noise: emptyRoundNoise(),
        },
      ]
      const originalRounds = [
        {
          round_number: 1,
          evaluation: { enabled: true, dimensions: [{ id: 9, name: 'LLM复核测试维度' }] },
        },
      ]
      const config = roundsToConfig(drafts, originalRounds, dimNameById)
      expect((config[0].evaluation as { dimensions?: unknown[] }).dimensions).toEqual([
        { id: 9, name: 'LLM复核测试维度', weight: 50, threshold: 80 },
      ])
      // 新维度不在原始轮（dimNameById 解析补 name，不回退 dim-9）
      const freshDraft = { ...drafts[0], evaluation: { ...drafts[0].evaluation, selectedIds: [9] } }
      const configFresh = roundsToConfig([freshDraft], null, dimNameById)
      expect((configFresh[0].evaluation as { dimensions?: unknown[] }).dimensions).toEqual([
        { id: 9, name: 'LLM复核测试维度', weight: 50, threshold: 80 },
      ])
    })
  })

  describe('toStrategyOverridesDto（P3-1）', () => {
    it('backgroundNoise → background_noise（后端读 raw dict snake_case 键）', () => {
      const overrides = {
        backgroundNoise: { audioId: 7, spl: 60 },
      }
      expect(toStrategyOverridesDto(overrides)).toEqual({
        background_noise: { audioId: 7, spl: 60 },
      })
    })

    it('dimensions 条目保持 llmJudgeConfig（后端覆盖字段同 camelCase）', () => {
      const overrides = {
        dimensions: [
          { id: 1, name: '识别准确率', weight: 70, threshold: 80, llmJudgeConfig: { model: 'x', promptTemplate: 'y' } },
        ],
      }
      expect(toStrategyOverridesDto(overrides)).toEqual({
        dimensions: [
          { id: 1, name: '识别准确率', weight: 70, threshold: 80, llmJudgeConfig: { model: 'x', promptTemplate: 'y' } },
        ],
      })
    })

    it('null / 空覆盖 → null', () => {
      expect(toStrategyOverridesDto(null)).toBeNull()
      expect(toStrategyOverridesDto({})).toBeNull()
    })
  })
})
