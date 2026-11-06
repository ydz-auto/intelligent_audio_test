/**
 * INT-2368：设备页头统计「加载中显示 0」缺陷回归。
 * 口径：列表首载中/首载失败且无数据 → 统计未知（「在线 —/共 —」、隐藏分页）；
 * 取到数据（含刷新时保留的上一份）→ 按当前页签真实计数；真·空列表仍显示 0。
 */
import { describe, expect, it } from 'vitest'

import {
  getDeviceStatsBadgeText,
  isDeviceListUnknown,
} from '@/features/devices/lib/device-stats-badge'

describe('isDeviceListUnknown（INT-2368）', () => {
  it('首载加载中且无数据 → 未知（不把「未加载完」当 0 台）', () => {
    expect(
      isDeviceListUnknown({ isLoading: true, isError: false, hasRows: false })
    ).toBe(true)
  })

  it('首载失败且无数据 → 未知（INT-2330 原口径保留）', () => {
    expect(
      isDeviceListUnknown({ isLoading: false, isError: true, hasRows: false })
    ).toBe(true)
  })

  it('刷新中但保留上一份数据 → 不是未知，显示旧计数', () => {
    expect(
      isDeviceListUnknown({ isLoading: true, isError: false, hasRows: true })
    ).toBe(false)
  })

  it('加载完成且真·空列表 → 已知的 0，不是未知', () => {
    expect(
      isDeviceListUnknown({ isLoading: false, isError: false, hasRows: false })
    ).toBe(false)
  })
})

describe('getDeviceStatsBadgeText（INT-2368）', () => {
  it('加载中无数据 → 「在线 —/共 —」', () => {
    expect(
      getDeviceStatsBadgeText(
        { isLoading: true, isError: false, hasRows: false },
        { online: 0, total: 0 }
      )
    ).toBe('在线 —/共 —')
  })

  it('失败无数据 → 「在线 —/共 —」', () => {
    expect(
      getDeviceStatsBadgeText(
        { isLoading: false, isError: true, hasRows: false },
        { online: 0, total: 0 }
      )
    ).toBe('在线 —/共 —')
  })

  it('取到数据 → 当前页签真实计数', () => {
    expect(
      getDeviceStatsBadgeText(
        { isLoading: false, isError: false, hasRows: true },
        { online: 4, total: 6 }
      )
    ).toBe('在线 4/共 6')
  })

  it('加载完成真·空列表 → 「在线 0/共 0」', () => {
    expect(
      getDeviceStatsBadgeText(
        { isLoading: false, isError: false, hasRows: false },
        { online: 0, total: 0 }
      )
    ).toBe('在线 0/共 0')
  })
})
