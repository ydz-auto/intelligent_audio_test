/**
 * 标签管理页常量测试（11_用例域.md §4.2/§5.4/§8 中文文案与交互常量源）：
 * 色板 8 色、未分类固定色、搜索防抖毫秒、滚动阈值、时间格式化。
 */
import { describe, expect, it } from 'vitest'

import {
  DEFAULT_CATEGORY_COLOR,
  DEFAULT_TAG_COLOR,
  SCROLL_LOAD_MORE_THRESHOLD,
  TAG_DESC_MAX_LENGTH,
  TAG_NAME_MAX_LENGTH,
  TAG_PALETTE,
  TAG_SEARCH_DEBOUNCE_MS,
  UNCATEGORIZED_COLOR,
  formatDateTime,
} from '@/features/tags/constants'

describe('tags constants', () => {
  it('色板 8 色 + 默认色与未分类固定色', () => {
    expect(TAG_PALETTE).toHaveLength(8)
    for (const color of TAG_PALETTE) {
      expect(color).toMatch(/^#[0-9a-f]{6}$/i)
    }
    expect(DEFAULT_TAG_COLOR).toBe('#10b981')
    expect(DEFAULT_CATEGORY_COLOR).toBe('#6366f1')
    expect(UNCATEGORIZED_COLOR).toBe('#94a3b8')
  })

  it('交互常量：搜索 300ms / 触底 100px / 名称 50 / 描述 500', () => {
    expect(TAG_SEARCH_DEBOUNCE_MS).toBe(300)
    expect(SCROLL_LOAD_MORE_THRESHOLD).toBe(100)
    expect(TAG_NAME_MAX_LENGTH).toBe(50)
    expect(TAG_DESC_MAX_LENGTH).toBe(500)
  })

  it('formatDateTime：裸 UTC 转本地 YYYY-MM-DD HH:mm，null 显 —', () => {
    // 断言以本地时区换算为基准，不写死 +08:00（INT-2211 起走共享口径）
    const date = new Date('2026-09-01T10:05:00Z')
    const pad = (value: number) => String(value).padStart(2, '0')
    const expected = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
      date.getDate()
    )} ${pad(date.getHours())}:${pad(date.getMinutes())}`
    expect(formatDateTime('2026-09-01T10:05:00')).toBe(expected)
    expect(formatDateTime('2026-09-01 10:00')).toBe(
      formatDateTime('2026-09-01T10:00:00')
    )
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime(undefined)).toBe('—')
  })
})
