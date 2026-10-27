/**
 * 用例标签两级树分页（15_报告域.md §3.3.7，INT-2101）。
 * paginateSections 整节同页：「未分类」尾组不跨页截断（单节 > pageSize 时自然跨页）。
 */
import { describe, expect, it } from 'vitest'

import { paginateSections } from '@/features/report-view/components/task-report-panel/filter-tag-tree'
import { UNCATEGORIZED_SECTION_KEY } from '@/application/report-view/use-report-filter-taxonomy'

interface FlatTag {
  sectionKey: string
  sectionName: string
  name: string
}

const sec = (sectionKey: string, sectionName: string, names: string[]): FlatTag[] =>
  names.map((name) => ({ sectionKey, sectionName, name }))

describe('paginateSections', () => {
  it('未分类尾组较小且放不进当前页剩余位时整节翻页，不跨页截断', () => {
    const flat = [
      ...sec('功能', '功能', ['a1', 'a2', 'a3', 'a4', 'a5', 'a6']),
      ...sec(UNCATEGORIZED_SECTION_KEY, '未分类', ['u1', 'u2', 'u3']),
    ]
    const pages = paginateSections(flat, 8)
    expect(pages).toHaveLength(2)
    // 第 1 页：功能整节；第 2 页：未分类整节（不被上一页余位拆散）
    expect(pages[0].map((t) => t.name)).toEqual(['a1', 'a2', 'a3', 'a4', 'a5', 'a6'])
    expect(pages[1].map((t) => t.name)).toEqual(['u1', 'u2', 'u3'])
    expect(pages[1][0].sectionKey).toBe(UNCATEGORIZED_SECTION_KEY)
  })

  it('单节恰好占满整页时不拆分', () => {
    const flat = [
      ...sec('功能', '功能', ['a1', 'a2', 'a3', 'a4']),
      ...sec('性能', '性能', ['b1', 'b2', 'b3', 'b4']),
    ]
    const pages = paginateSections(flat, 8)
    expect(pages).toHaveLength(1)
    expect(pages[0]).toHaveLength(8)
  })

  it('单节超过 pageSize 时自然跨页，但页内仍是该节连续块', () => {
    const flat = [
      ...sec('功能', '功能', ['a1', 'a2', 'a3']),
      ...sec(UNCATEGORIZED_SECTION_KEY, '未分类', ['u1', 'u2', 'u3', 'u4', 'u5', 'u6', 'u7', 'u8', 'u9', 'u10']),
    ]
    const pages = paginateSections(flat, 8)
    expect(pages).toHaveLength(2)
    expect(pages[0].map((t) => t.name)).toEqual(['a1', 'a2', 'a3', 'u1', 'u2', 'u3', 'u4', 'u5'])
    expect(pages[1].map((t) => t.name)).toEqual(['u6', 'u7', 'u8', 'u9', 'u10'])
  })

  it('pageSize 缺省/<=0 时不分页', () => {
    const flat = sec('A', 'A', ['x1', 'x2'])
    expect(paginateSections(flat, 0)).toHaveLength(1)
    expect(paginateSections(flat, 0)[0]).toHaveLength(2)
  })
})
