/**
 * 评估维度行内启停 / 复制 API 单测（INT-2247）：
 * 列表端点把 required_inputs / output_fields / associated_algorithms 固定下发空数组
 * （evaluation_query_service 省 N+1 的占位），整行 PUT/POST 会被后端当「用户显式清空」
 * → 删输出参数与 output ParamMapping。因此：
 *   1. 行内启停只发变更字段 { status }；
 *   2. 复制必须先取详情，以详情配置作载荷（副本保留输入/输出字段与算法关联）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Dimension } from '@/domain/models/evaluationDimension'
import {
  duplicateDimension,
  updateDimensionStatus,
} from '@/infrastructure/api/evaluation-api'

const requestMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/client', () => ({ request: requestMock }))

/** 列表行（与列表端点同口径：配置字段是占位空数组） */
const LIST_ROW: Dimension = {
  id: 5,
  name: '拒识成功率',
  dimensionType: 'main',
  type: 'auto',
  resultType: 1,
  status: true,
  requiredInputs: [],
  outputFields: [],
  associatedAlgorithms: [],
}

/** GET /evaluation/dimensions/5 真实详情（snake_case wire） */
const DETAIL_DTO = {
  id: 5,
  name: '拒识成功率',
  dimension_type: 'main',
  type: 'auto',
  result_type: 1,
  status: true,
  required_inputs: [
    {
      param_code: 'asr_result',
      param_name: '识别结果',
      field_type: 'text',
      required: true,
    },
  ],
  output_fields: [
    {
      param_code: 'reject_rate',
      param_name: '拒识率',
      field_path: 'data.reject_rate',
      field_type: 'number',
      output_role: 'main',
      agg_role: 'value',
      pass_threshold: 0.9,
    },
  ],
  associated_algorithms: [
    { algorithm_type: 'voice_llm', is_default: true, weight: 3 },
  ],
}

describe('updateDimensionStatus（行内启用/禁用）', () => {
  beforeEach(() => {
    requestMock.mockReset()
  })

  it('只提交 { status }，不整行上送列表占位空配置', async () => {
    requestMock.mockResolvedValue({ success: true })

    await expect(updateDimensionStatus(5, false)).resolves.toEqual({
      success: true,
    })

    expect(requestMock).toHaveBeenCalledTimes(1)
    expect(requestMock).toHaveBeenCalledWith('PUT', '/evaluation/dimensions/5', {
      status: false,
    })
    // 不得出现列表占位字段（后端按「显式清空」删参数）
    const body = requestMock.mock.calls[0][2] as Record<string, unknown>
    expect(body).not.toHaveProperty('output_fields')
    expect(body).not.toHaveProperty('required_inputs')
    expect(body).not.toHaveProperty('associated_algorithms')
  })
})

describe('duplicateDimension（复制维度）', () => {
  beforeEach(() => {
    requestMock.mockReset()
  })

  it('先取详情再 POST，副本携带真实输入/输出字段与算法关联', async () => {
    requestMock.mockImplementation((method: string) =>
      Promise.resolve(method === 'GET' ? DETAIL_DTO : { success: true })
    )

    await expect(duplicateDimension(LIST_ROW)).resolves.toEqual({
      success: true,
    })

    expect(requestMock.mock.calls[0]).toEqual([
      'GET',
      '/evaluation/dimensions/5',
    ])
    expect(requestMock.mock.calls[1][0]).toBe('POST')
    expect(requestMock.mock.calls[1][1]).toBe('/evaluation/dimensions')

    const body = requestMock.mock.calls[1][2] as Record<string, unknown>
    expect(body.name).toBe('拒识成功率（副本）')
    // 输入侧 wire 键为 key（对齐 toDimensionInputDto / 抽屉保存同口径）
    expect(body.required_inputs).toEqual([
      expect.objectContaining({ key: 'asr_result', param_name: '识别结果' }),
    ])
    expect(body.output_fields).toEqual([
      expect.objectContaining({
        param_code: 'reject_rate',
        field_path: 'data.reject_rate',
        pass_threshold: 0.9,
      }),
    ])
    expect(body.associated_algorithms).toEqual([
      { algorithmType: 'voice_llm', isDefault: true, weight: 3 },
    ])
  })
})
