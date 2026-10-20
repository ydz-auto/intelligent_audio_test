/**
 * 评估策略适配器单测（INT-877 P2-2 接线真实 /evaluation-strategies）：
 * - evaluationStrategyFromDto：config 包裹 {dimensions, background_noise} 解出 Domain；
 * - evaluationStrategyToDto：POST 载荷 name/config 包裹（EvaluationStrategyCreateSchema）。
 */
import { describe, expect, it } from 'vitest'

import {
  evaluationStrategyFromDto,
  evaluationStrategyToDto,
} from '@/infrastructure/adapters/evaluationStrategyAdapter'

describe('evaluationStrategyAdapter（INT-590 后端策略契约）', () => {
  describe('evaluationStrategyFromDto', () => {
    it('config 包裹解出 dimensions/background_noise（snake_case → camelCase）', () => {
      const domain = evaluationStrategyFromDto({
        id: 'str-1',
        name: '全链路智能音箱回归',
        description: '说明',
        algorithm_type: null,
        enabled: true,
        config: {
          dimensions: [
            {
              id: 1,
              name: '识别准确率',
              weight: 50,
              threshold: 80,
              llmJudgeConfig: { model: 'claude-3-sonnet', prompt_template: 'accuracy' },
            },
          ],
          background_noise: {
            audio_id: 101,
            audio_name: '粉红噪声_94dB.wav',
            spl: 60,
            device_ids: ['3'],
            device_names: ['蓝牙音箱'],
            loop: true,
          },
        },
        referenced_case_count: 2,
      })
      expect(domain.id).toBe('str-1')
      expect(domain.name).toBe('全链路智能音箱回归')
      expect(domain.description).toBe('说明')
      expect(domain.dimensions).toEqual([
        {
          id: 1,
          name: '识别准确率',
          weight: 50,
          threshold: 80,
          llmJudgeConfig: { model: 'claude-3-sonnet', promptTemplate: 'accuracy' },
        },
      ])
      expect(domain.backgroundNoise).toEqual({
        audioId: 101,
        audioName: '粉红噪声_94dB.wav',
        spl: 60,
        deviceIds: ['3'],
        deviceNames: ['蓝牙音箱'],
        loop: true,
      })
    })

    it('空 config → 空维度 + 无背景噪声', () => {
      const domain = evaluationStrategyFromDto({
        id: 'str-2',
        name: '空策略',
        config: {},
      })
      expect(domain.dimensions).toEqual([])
      expect(domain.backgroundNoise).toBeNull()
    })
  })

  describe('evaluationStrategyToDto', () => {
    it('POST 载荷 name/config 包裹（EvaluationStrategyCreateSchema 口径）', () => {
      const dto = evaluationStrategyToDto({
        name: '新建策略',
        description: '描述',
        dimensions: [
          {
            id: 1,
            name: '识别准确率',
            weight: 50,
            threshold: 80,
            llmJudgeConfig: { model: 'claude-3-sonnet', promptTemplate: 'accuracy' },
          },
        ],
        backgroundNoise: { audioId: 101, audioName: '粉红噪声.wav', spl: 60, loop: true },
      })
      expect(dto).toEqual({
        name: '新建策略',
        description: '描述',
        algorithm_type: null,
        enabled: true,
        config: {
          dimensions: [
            {
              id: 1,
              name: '识别准确率',
              weight: 50,
              threshold: 80,
              llmJudgeConfig: { model: 'claude-3-sonnet', prompt_template: 'accuracy' },
            },
          ],
          background_noise: {
            audio_id: 101,
            audio_name: '粉红噪声.wav',
            spl: 60,
            device_ids: [],
            device_names: [],
            loop: true,
          },
        },
      })
    })

    it('无背景噪声 → background_noise null', () => {
      const dto = evaluationStrategyToDto({ name: '仅维度策略', dimensions: [] })
      expect(dto.config).toEqual({
        dimensions: [],
        background_noise: null,
      })
    })
  })
})
