/**
 * features/tasks/constants 状态/算法类型映射纯函数测试（对位 09_任务域.md §3.6.1/§9 文案）。
 * 任务类型（API测试/端到端测试）概念已移除（INT-1241，负责人 2026-10-22 口径），无对应用例。
 */
import { describe, expect, it } from 'vitest'

import {
  getAlgorithmTypeLabel,
  getEvaluationStatusMeta,
  getExecutionStatusMeta,
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
