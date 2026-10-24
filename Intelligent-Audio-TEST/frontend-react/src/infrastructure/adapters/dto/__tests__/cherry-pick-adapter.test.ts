/**
 * infrastructure/adapters/dto/cherry-pick-adapter 购物车条目转换测试（18 规范 §7.3/§11-5，INT-790 返工 P2-1）。
 * 对位 cherry_pick_service.cart_get 实测响应：cart_get 已返 source_case_name/source_device_name/
 * source_result_type（source_api_name 缺省 undefined）——adapter 优先直取，name map 兜底。
 */
import { describe, expect, it } from 'vitest'

import {
  fromCartEntryDto,
  fromSourceTraceDto,
} from '@/infrastructure/adapters/dto/cherry-pick-adapter'
import type {
  CherryPickCartItemDto,
  CherryPickSourceTraceDto,
} from '@/infrastructure/dto/cherry-pick.dto'

function baseItem(overrides: Partial<CherryPickCartItemDto> = {}): CherryPickCartItemDto {
  return {
    item_id: 1,
    result_id: 101,
    source_task_id: 1042,
    source_task_name: '任务A',
    source_case_id: 'c1',
    source_device_id: 1,
    source_api_id: null,
    source_case_name: null,
    source_device_name: null,
    source_api_name: null,
    source_result_type: 'real-time',
    execution_status: 'completed',
    created_at: '2026-10-19T04:00:00',
    invalid: false,
    ...overrides,
  }
}

describe('fromCartEntryDto', () => {
  it('cart_get 返回 source_*_name 时优先直取真实名（P2-1 修复）', () => {
    expect(
      fromCartEntryDto(
        baseItem({
          source_case_name: '用例001',
          source_device_name: 'pura90豆包',
          source_api_name: '语音识别API',
        })
      )
    ).toMatchObject({
      sourceCaseName: '用例001',
      sourceDeviceName: 'pura90豆包',
      sourceApiName: '语音识别API',
    })
  })

  it('source_*_name 缺省时回退 name map 兜底（设备/API map 已预取）', () => {
    const names = {
      devices: new Map([[1, '设备-01']]),
      apis: new Map([[9, 'API-09']]),
      cases: new Map([['c1', '用例-map']]),
    }
    expect(
      fromCartEntryDto(
        baseItem({ source_device_id: 1, source_api_id: null, source_case_name: null }),
        names
      )
    ).toMatchObject({
      sourceCaseName: '用例-map',
      sourceDeviceName: '设备-01',
      sourceApiName: null,
    })
    // api 分支：source_api_id 有值且 source_api_name 缺省 → apis map
    expect(
      fromCartEntryDto(
        baseItem({
          source_device_id: null,
          source_api_id: 9,
          source_device_name: null,
          source_api_name: null,
        }),
        names
      )
    ).toMatchObject({
      sourceDeviceName: null,
      sourceApiName: 'API-09',
    })
  })

  it('双缺省时保持 null，由树层 caseDisplayName 降级（不裸显 UUID）', () => {
    expect(
      fromCartEntryDto(
        baseItem({ source_case_name: null, source_device_name: null, source_api_name: null }),
        { devices: new Map(), apis: new Map(), cases: new Map() }
      )
    ).toMatchObject({
      sourceCaseName: null,
      sourceDeviceName: null,
      sourceApiName: null,
    })
  })

  it('source_result_type 空白 → null（result_type 级折叠「结果类型待补充」）', () => {
    expect(fromCartEntryDto(baseItem({ source_result_type: '  ' })).sourceResultType).toBeNull()
  })
})

describe('fromSourceTraceDto（INT-1711 容器溯源；审计 P2-1 回归）', () => {
  const dto: CherryPickSourceTraceDto = {
    task_id: 595,
    is_cherry_pick: true,
    total: 1,
    groups: [
      {
        source_task_id: 419,
        source_task_name: '任务419',
        results: [
          {
            result_id: 5714,
            source_task_id: 419,
            source_task_name: '任务419',
            source_case_id: 'c1',
            source_device_id: 9,
            source_api_id: null,
            missing: false,
            // 关系行时间 = 并入容器的时间，实测 5 条叶行同值（= 容器 created_at）
            created_at: '2026-10-24T03:41:47.289098',
          },
        ],
      },
    ],
  }

  it('关系行 created_at 不得映射为源结果时间（§11-8 字段未返 → null，叶行不渲染时间）', () => {
    expect(fromSourceTraceDto(dto).groups[0].results[0].resultCreatedAt).toBeNull()
  })

  it('§11-8 的 result_created_at 返值后直取真值', () => {
    const withResultTime: CherryPickSourceTraceDto = {
      ...dto,
      groups: [
        {
          ...dto.groups[0],
          results: [
            {
              ...dto.groups[0].results[0],
              result_created_at: '2026-10-14T09:27:22',
            },
          ],
        },
      ],
    }
    expect(fromSourceTraceDto(withResultTime).groups[0].results[0].resultCreatedAt).toBe(
      '2026-10-14T09:27:22'
    )
  })
})
