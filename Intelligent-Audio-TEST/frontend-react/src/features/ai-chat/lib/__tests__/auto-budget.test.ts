/**
 * Auto 预算草稿单测（INT-2474 §9.4）。
 * 关注点：留空 = 不收紧、非法输入不进入请求、分钟/MB 换算、外部预算同步判定。
 */
import { describe, expect, it } from 'vitest'

import {
  EMPTY_AUTO_BUDGET_DRAFT,
  budgetsEqual,
  buildAutoBudget,
  invalidBudgetFields,
  parseBudgetField,
  toAutoBudgetDraft,
} from '@/features/ai-chat/lib/auto-budget'

describe('parseBudgetField', () => {
  it('空串 / 空白 → undefined（不收紧）', () => {
    expect(parseBudgetField('')).toBeUndefined()
    expect(parseBudgetField('   ')).toBeUndefined()
  })

  it('正整数 → 数值', () => {
    expect(parseBudgetField('12')).toBe(12)
    expect(parseBudgetField(' 7 ')).toBe(7)
  })

  it('0 / 负数 / 小数 / 非数字 → null（非法，不静默截断）', () => {
    for (const text of ['0', '-3', '1.5', 'abc', '1e3', '+4']) {
      expect(parseBudgetField(text)).toBeNull()
    }
  })
})

describe('buildAutoBudget', () => {
  it('全部留空 → undefined（完全用服务端默认）', () => {
    expect(buildAutoBudget(EMPTY_AUTO_BUDGET_DRAFT)).toBeUndefined()
  })

  it('分钟 → 秒、MB → 字节；非法项被剔除', () => {
    const budget = buildAutoBudget({
      ...EMPTY_AUTO_BUDGET_DRAFT,
      maxRounds: '20',
      maxDurationMinutes: '10',
      maxOutputMegabytes: '2',
      maxTokens: 'xxx',
    })
    expect(budget).toEqual({
      maxRounds: 20,
      maxToolCalls: undefined,
      maxTokens: undefined,
      maxDurationSeconds: 600,
      maxOutputBytes: 2 * 1024 * 1024,
    })
  })

  it('只有非法输入 → undefined（不发出非法预算，避免后端 400）', () => {
    expect(
      buildAutoBudget({ ...EMPTY_AUTO_BUDGET_DRAFT, maxRounds: '0' })
    ).toBeUndefined()
  })
})

describe('toAutoBudgetDraft / invalidBudgetFields', () => {
  it('领域预算 → 草稿（秒 → 分钟、字节 → MB 取整）', () => {
    expect(
      toAutoBudgetDraft({
        maxRounds: 30,
        maxDurationSeconds: 1800,
        maxOutputBytes: 20 * 1024 * 1024,
      })
    ).toEqual({
      maxRounds: '30',
      maxToolCalls: '',
      maxTokens: '',
      maxDurationMinutes: '30',
      maxOutputMegabytes: '20',
    })
  })

  it('非法字段只标自身，不误伤其他项', () => {
    const invalid = invalidBudgetFields({
      ...EMPTY_AUTO_BUDGET_DRAFT,
      maxRounds: '0',
      maxTokens: '5',
    })
    expect([...invalid]).toEqual(['maxRounds'])
  })
})

describe('budgetsEqual', () => {
  it('只比较显式维度（undefined 与缺省等价）', () => {
    expect(budgetsEqual({ maxRounds: 5 }, { maxRounds: 5 })).toBe(true)
    expect(budgetsEqual(undefined, {})).toBe(true)
    expect(budgetsEqual({ maxRounds: 5 }, { maxRounds: 6 })).toBe(false)
    expect(budgetsEqual({ maxRounds: 5 }, undefined)).toBe(false)
  })
})
