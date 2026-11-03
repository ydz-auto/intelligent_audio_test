/**
 * INT-2378：报告展示页（/reports）计数「加载中显示 0」缺陷回归。
 * 口径：列表首载中 / 首载失败且无数据 → 计数未知（「共 — 个已发布报告」）；
 * 取到数据（含刷新时保留的上一份）→ 真实总数；真·空列表仍显示 0。
 */
import { describe, expect, it } from 'vitest'

import {
  getShowcaseCountText,
  isShowcaseCountUnknown,
} from '@/features/reports-showcase/lib/showcase-count'

describe('isShowcaseCountUnknown（INT-2378）', () => {
  it('首载加载中且无数据 → 未知（不把「未加载完」当 0 份）', () => {
    expect(
      isShowcaseCountUnknown({ isLoading: true, isError: false, hasData: false })
    ).toBe(true)
  })

  it('首载失败且无数据 → 未知（INT-2330 错误态口径保留）', () => {
    expect(
      isShowcaseCountUnknown({ isLoading: false, isError: true, hasData: false })
    ).toBe(true)
  })

  it('刷新中但保留上一份数据 → 不是未知，按旧计数展示', () => {
    expect(
      isShowcaseCountUnknown({ isLoading: true, isError: false, hasData: true })
    ).toBe(false)
  })

  it('加载完成且真·空列表 → 已知的 0，不是未知', () => {
    expect(
      isShowcaseCountUnknown({ isLoading: false, isError: false, hasData: false })
    ).toBe(false)
  })
})

describe('getShowcaseCountText（INT-2378）', () => {
  it('加载中无数据 → 「共 — 个已发布报告」', () => {
    expect(
      getShowcaseCountText(
        { isLoading: true, isError: false, hasData: false },
        0
      )
    ).toBe('共 — 个已发布报告')
  })

  it('失败无数据 → 「共 — 个已发布报告」', () => {
    expect(
      getShowcaseCountText(
        { isLoading: false, isError: true, hasData: false },
        0
      )
    ).toBe('共 — 个已发布报告')
  })

  it('取到数据 → 真实总数', () => {
    expect(
      getShowcaseCountText(
        { isLoading: false, isError: false, hasData: true },
        5
      )
    ).toBe('共 5 个已发布报告')
  })

  it('加载完成真·空列表 → 「共 0 个已发布报告」', () => {
    expect(
      getShowcaseCountText(
        { isLoading: false, isError: false, hasData: false },
        0
      )
    ).toBe('共 0 个已发布报告')
  })
})
