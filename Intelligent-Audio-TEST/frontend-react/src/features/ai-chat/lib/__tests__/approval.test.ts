/**
 * features/ai-chat/lib/approval 纯函数测试（INT-2472 审计返修 P3-2/3/4 + P2 §9.4）：
 * 轮次 0 起转 1 起、内部步骤 UUID 截断、决策人只解析当前用户为「我」、
 * 提案影响对象数统计（>20 对象必须单条审批）。
 */
import { describe, expect, it } from 'vitest'

import {
  formatApprovalApprover,
  formatApprovalStepId,
  formatApprovalTurn,
  summarizeApprovalTargets,
} from '@/features/ai-chat/lib/approval'

/** 只带 proposal 的最小审批单（统计函数只读 proposal.arguments） */
function approvalWith(argumentsValue: Record<string, unknown>) {
  return { proposal: { tool: 'x', arguments: argumentsValue } }
}

describe('formatApprovalTurn', () => {
  it('后端 turn 从 0 起，展示 1 起', () => {
    expect(formatApprovalTurn(0)).toBe('第 1 轮')
    expect(formatApprovalTurn(2)).toBe('第 3 轮')
  })

  it('缺失 / 非数字不展示', () => {
    expect(formatApprovalTurn(undefined)).toBeNull()
    expect(formatApprovalTurn(Number.NaN)).toBeNull()
  })
})

describe('formatApprovalStepId', () => {
  it('长 UUID 截断到前 8 位，短 id 原样展示', () => {
    expect(formatApprovalStepId('8dd2ee8d-1c4e-4b7a-9f00-112233445566')).toBe(
      '8dd2ee8d…'
    )
    expect(formatApprovalStepId('step-1')).toBe('step-1')
  })

  it('缺失 / 空白返回 null', () => {
    expect(formatApprovalStepId(undefined)).toBeNull()
    expect(formatApprovalStepId('   ')).toBeNull()
  })
})

describe('formatApprovalApprover', () => {
  it('当前用户显示「我」，其他用户不直出数字 id', () => {
    expect(formatApprovalApprover(7, '7')).toBe('我')
    expect(formatApprovalApprover(7, '8')).toBe('其他用户')
  })

  it('当前用户未知时按其他用户处理；决策人缺失返回 null', () => {
    expect(formatApprovalApprover(7, undefined)).toBe('其他用户')
    expect(formatApprovalApprover(undefined, '7')).toBeNull()
  })
})

describe('summarizeApprovalTargets（§9.4 批量粒度）', () => {
  it('顶层 *_ids 数组：按元素个数计，超过 20 判 overLimit', () => {
    const summary = summarizeApprovalTargets(
      approvalWith({ action: 'batch', device_ids: Array.from({ length: 21 }, (_, i) => i + 1) })
    )
    expect(summary.count).toBe(21)
    expect(summary.overLimit).toBe(true)
    expect(summary.fields).toEqual(['device_ids'])
    expect(summary.targets).toHaveLength(21)
    expect(summary.targets[0]).toBe('1')
  })

  it('嵌套 body.task_ids 同样识别；正好 20 个不超限', () => {
    const summary = summarizeApprovalTargets(
      approvalWith({
        action: 'merge',
        body: { task_ids: Array.from({ length: 20 }, (_, i) => i + 1) },
      })
    )
    expect(summary.count).toBe(20)
    expect(summary.overLimit).toBe(false)
    expect(summary.fields).toEqual(['body.task_ids'])
  })

  it('多个数组并存取最大值（不重复计数），对象数组按对象个数计', () => {
    const summary = summarizeApprovalTargets(
      approvalWith({
        device_ids: [1, 2, 3],
        body: { cases: [{ id: 'c-1' }, { id: 'c-2' }, { id: 'c-3' }, { id: 'c-4' }] },
      })
    )
    expect(summary.count).toBe(4)
    expect(summary.overLimit).toBe(false)
    expect(summary.fields).toEqual(['device_ids', 'body.cases'])
    expect(summary.targets).toEqual(['c-1', 'c-2', 'c-3', 'c-4'])
  })

  it('无对象数组 / 无参数：计数 0，不触发逐项核对', () => {
    expect(
      summarizeApprovalTargets(approvalWith({ section: 'USER_PROFILE', content: 'x' }))
    ).toMatchObject({ count: 0, overLimit: false, fields: [] })
    expect(summarizeApprovalTargets({ proposal: { tool: 'x' } })).toMatchObject({
      count: 0,
      overLimit: false,
    })
  })
})
