/**
 * features/tasks/constants 状态/类型映射纯函数测试（对位 09_任务域.md §3.6.1/§9 文案）。
 */
import { describe, expect, it } from 'vitest'

import {
  deriveTaskType,
  getAlgorithmTypeLabel,
  getEvaluationStatusMeta,
  getExecutionStatusMeta,
  getTaskTypeLabel,
} from '@/features/tasks/constants'

describe('getExecutionStatusMeta', () => {
  it('已知执行状态映射为中文徽章', () => {
    expect(getExecutionStatusMeta('running')).toEqual({
      label: '执行中',
      variant: 'info',
      pulse: true,
    })
    expect(getExecutionStatusMeta('completed')).toEqual({
      label: '已完成',
      variant: 'success',
    })
    expect(getExecutionStatusMeta('failed')).toEqual({
      label: '执行失败',
      variant: 'danger',
    })
  })

  it('空值回退为中性占位，未知值原样透出', () => {
    expect(getExecutionStatusMeta(null)).toEqual({
      label: '—',
      variant: 'neutral',
    })
    expect(getExecutionStatusMeta('unknown_status').label).toBe(
      'unknown_status'
    )
  })
})

describe('getEvaluationStatusMeta', () => {
  it('已知评估状态映射为中文徽章', () => {
    expect(getEvaluationStatusMeta('evaluating')).toEqual({
      label: '评估中',
      variant: 'info',
      pulse: true,
    })
    expect(getEvaluationStatusMeta('completed')).toEqual({
      label: '已评估完成',
      variant: 'success',
    })
  })

  it('空值回退为中性占位', () => {
    expect(getEvaluationStatusMeta(null)).toEqual({
      label: '—',
      variant: 'neutral',
    })
  })
})

describe('getTaskTypeLabel', () => {
  it('已知任务类型映射中文', () => {
    expect(getTaskTypeLabel('e2e')).toBe('端到端测试')
    expect(getTaskTypeLabel('api')).toBe('API测试')
    expect(getTaskTypeLabel('mixed')).toBe('混合')
  })

  it('空值与未知值回退', () => {
    expect(getTaskTypeLabel(null)).toBe('—')
    expect(getTaskTypeLabel('unknown')).toBe('unknown')
  })
})

describe('deriveTaskType', () => {
  it('physical → e2e，http_api/websocket_api → api，兼有 → mixed', () => {
    expect(deriveTaskType(['physical'])).toBe('e2e')
    expect(deriveTaskType(['http_api'])).toBe('api')
    expect(deriveTaskType(['websocket_api'])).toBe('api')
    expect(deriveTaskType(['physical', 'http_api'])).toBe('mixed')
    expect(deriveTaskType(['physical', 'websocket_api'])).toBe('mixed')
  })

  it('空 device_types 按关联资源兜底：有实体设备判 e2e（INT-1241）', () => {
    // 任务 419 类旧任务：用例未派生 device_type，但有 1 台实体设备
    expect(deriveTaskType([], { device_count: 1, api_count: 0 })).toBe('e2e')
    expect(deriveTaskType(undefined, { device_count: 1, api_count: 0 })).toBe('e2e')
    expect(deriveTaskType(null, { device_count: 1, api_count: 0 })).toBe('e2e')
  })

  it('空 device_types 按关联资源兜底：有 API 判 api、兼有判 mixed、均无回退 api', () => {
    expect(deriveTaskType([], { device_count: 0, api_count: 2 })).toBe('api')
    expect(deriveTaskType([], { device_count: 1, api_count: 2 })).toBe('mixed')
    expect(deriveTaskType([], { device_count: 0, api_count: 0 })).toBe('api')
    expect(deriveTaskType([], undefined)).toBe('api')
  })

  it('非空 device_types 优先于资源计数（资源只作空集兜底）', () => {
    expect(deriveTaskType(['http_api'], { device_count: 1, api_count: 0 })).toBe(
      'api'
    )
    expect(deriveTaskType(['physical'], { device_count: 0, api_count: 2 })).toBe(
      'e2e'
    )
  })
})

describe('getAlgorithmTypeLabel', () => {
  it('已知算法类型映射中文', () => {
    expect(getAlgorithmTypeLabel('asr_streaming')).toBe('流式语音识别')
    expect(getAlgorithmTypeLabel('wakeword_detect')).toBe('唤醒词检测')
  })

  it('空值与未知值回退', () => {
    expect(getAlgorithmTypeLabel(null)).toBeNull()
    expect(getAlgorithmTypeLabel('custom_alg')).toBe('custom_alg')
  })
})
