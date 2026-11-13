/**
 * features/ai-chat/lib/approval 纯函数测试（INT-2472 审计返修 P3-2/3/4）：
 * 轮次 0 起转 1 起、内部步骤 UUID 截断、决策人只解析当前用户为「我」。
 */
import { describe, expect, it } from 'vitest'

import {
  formatApprovalApprover,
  formatApprovalStepId,
  formatApprovalTurn,
} from '@/features/ai-chat/lib/approval'

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
