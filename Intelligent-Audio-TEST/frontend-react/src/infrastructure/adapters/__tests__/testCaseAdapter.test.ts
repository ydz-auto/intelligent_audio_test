/**
 * infrastructure/adapters/testCaseAdapter 纯函数测试（10 规范 §5.2 / §9，INT-1066）。
 * 对位 task_bp.py get_case_detail 实测响应：case_name（无 name 字段）+ algorithm_results 扁平项
 * + devices。返工 P1：case_name → name 映射；P2：algorithm_results → 领域模型消费。
 */
import { describe, expect, it } from 'vitest'

import { caseDetailFromDto } from '@/infrastructure/adapters/testCaseAdapter'

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
