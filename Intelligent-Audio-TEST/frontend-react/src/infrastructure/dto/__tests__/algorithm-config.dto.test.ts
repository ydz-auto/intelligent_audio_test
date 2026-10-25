/**
 * 算法配置 DTO 参数映射 source 透传测试（INT-1160 返工 P3）：
 * 存量脏数据 source='evaluation' 读侧保留字符串原值、写侧原样提交，不读时丢弃、
 * 保存时归一为 'case'（后端 upsert 自然键含 source，否则旧行软删+新行重建）。
 */
import { describe, expect, it } from 'vitest'

import {
  toAlgorithmDefinitionDto,
  toParamMapping,
} from '@/infrastructure/dto/algorithm-config.dto'

describe('algorithm-config.dto toParamMapping（读侧）', () => {
  it('已知五值照常映射为枚举', () => {
    const mapping = toParamMapping({
      id: 1,
      source: 'reference',
      source_param: 'ref_text',
      transform_type: 'none',
    })
    expect(mapping.source).toBe('reference')
  })

  it('未知存量 source（evaluation）保留字符串原值（数据保全）', () => {
    const mapping = toParamMapping({
      id: 2,
      source: 'evaluation',
      source_param: 'wer',
      transform_type: 'none',
    })
    expect(mapping.source).toBe('evaluation')
  })

  it('缺省 source 为 null', () => {
    const mapping = toParamMapping({
      id: 3,
      source_param: 'x',
      transform_type: 'none',
    })
    expect(mapping.source).toBeNull()
  })
})

describe('algorithm-config.dto toMappingItemDto（写侧）', () => {
  it('evaluation 未知 source 原样提交（不归一为 case）', () => {
    const dto = toAlgorithmDefinitionDto(
      {
        type: 'asr_v3',
        name: '语音识别',
        groupId: null,
        displayOrder: 0,
        status: 'online',
        description: '',
        deviceParams: [],
        apiParams: [],
        caseParams: [],
        referenceParams: [],
        mappings: {
          device: [],
          api: [],
          evaluation: [
            {
              source: 'evaluation',
              sourceParam: 'wer',
              dimensionId: '26',
              targetParam: '',
              transformType: 'none',
            },
          ],
        },
        associatedDimensions: [],
      },
      new Map()
    )
    const item = (
      dto.mappings as { evaluation: Array<Record<string, unknown>> }
    ).evaluation[0]
    expect(item.source).toBe('evaluation')
  })

  it('evaluation 已知 source 照常提交', () => {
    const dto = toAlgorithmDefinitionDto(
      {
        type: 'asr_v3',
        name: '语音识别',
        groupId: null,
        displayOrder: 0,
        status: 'online',
        description: '',
        deviceParams: [],
        apiParams: [],
        caseParams: [],
        referenceParams: [],
        mappings: {
          device: [],
          api: [],
          evaluation: [{ source: 'case', sourceParam: 'wer', transformType: 'none' }],
        },
        associatedDimensions: [],
      },
      new Map()
    )
    const item = (
      dto.mappings as { evaluation: Array<Record<string, unknown>> }
    ).evaluation[0]
    expect(item.source).toBe('case')
  })
})
