/**
 * 回滚 toast 文案（INT-2341）：后端 API 作用域只回 paramsRestored/mappingsRestored，
 * 只读 created/updated 会误报「无变化」。
 */
import { describe, expect, it } from 'vitest'

import { restoreSummary } from '../param-history-dialog'

describe('restoreSummary', () => {
  it('API 作用域：有恢复总数时显示恢复条数（0 也显示）', () => {
    expect(restoreSummary({ paramsRestored: 1, mappingsRestored: 0 })).toBe(
      '恢复参数 1，恢复映射 0'
    )
  })

  it('设备作用域：按增删改计数只列发生的动作', () => {
    expect(
      restoreSummary({
        paramsCreated: 1,
        paramsUpdated: 2,
        paramsDeleted: 0,
        mappingsCreated: 0,
        mappingsUpdated: 0,
        mappingsDeleted: 0,
      })
    ).toBe('新增参数 1，更新参数 2')
  })

  it('没有任何计数 → 无变化', () => {
    expect(restoreSummary({})).toBe('无变化')
  })
})
