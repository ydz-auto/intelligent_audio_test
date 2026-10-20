/**
 * INT-810：DimensionOutputField passThreshold ↔ pass_threshold 映射契约测试。
 * 覆盖 evaluationAdapter 读方向 toOutputField / 写方向 toOutputFieldDto：
 * 后端回显 pass_threshold → 前端 passThreshold；保存时 passThreshold → pass_threshold。
 */
import { describe, it, expect } from 'vitest'
import { toDimension, toDimensionDto } from '../evaluationAdapter'
import type { DimensionItemDto } from '../../dto/evaluationDto'
import type { Dimension } from '../../../domain/model/dimension'

const RAW_DTO = {
  id: 1,
  name: '测试维度',
  dimension_type: 'main',
  output_fields: [
    {
      id: 100,
      dimension_id: 1,
      param_code: 'wer',
      param_name: 'WER值',
      field_path: 'wer',
      field_type: 'number',
      output_role: 'main',
      agg_role: 'pass_le',
      pass_threshold: 0.1,
      default_value: '',
      visible_in_report: true,
    },
    {
      id: 101,
      dimension_id: 1,
      param_code: 'err',
      field_path: 'err',
      field_type: 'number',
      output_role: 'main',
      agg_role: 'value',
      default_value: '',
      visible_in_report: true,
    },
  ],
} as unknown as DimensionItemDto

describe('evaluationAdapter pass_threshold', () => {
  it('toDimension：后端 pass_threshold → 前端 passThreshold（缺失回落 null）', () => {
    const dim = toDimension(RAW_DTO)
    const fields = dim.outputFields ?? []
    expect(fields).toHaveLength(2)
    expect(fields[0].passThreshold).toBe(0.1)
    // 非 pass_* 角色且无阈值 → null
    expect(fields[1].passThreshold).toBeNull()
  })

  it('toDimensionDto：前端 passThreshold → 请求体 pass_threshold', () => {
    const domain: Dimension = {
      id: 1,
      name: '测试维度',
      dimensionType: 'main',
      outputFields: [
        {
          paramCode: 'wer',
          paramName: 'WER值',
          fieldPath: 'wer',
          fieldType: 'number',
          outputRole: 'main',
          aggRole: 'pass_ge',
          passThreshold: 0.5,
          defaultValue: '',
          visibleInReport: true,
        },
        {
          paramCode: 'err',
          fieldPath: 'err',
          fieldType: 'number',
          outputRole: 'main',
          aggRole: 'value',
          defaultValue: '',
          visibleInReport: true,
        },
      ],
    }
    const dto = toDimensionDto(domain)
    const fields = dto.output_fields as Record<string, any>[]
    expect(fields).toHaveLength(2)
    expect(fields[0].pass_threshold).toBe(0.5)
    expect(fields[1].pass_threshold).toBeUndefined()
  })
})
