/**
 * 报告筛选分类归属（15_报告域.md §3.3.7 标签两级树，INT-2101）。
 * 只测纯函数 buildTagSections——阶梯①快照分类 → 阶梯② by-category 兜底 → 阶梯③未分类尾组。
 */
import { describe, expect, it } from 'vitest'

import {
  buildTagSections,
  UNCATEGORIZED_SECTION_KEY,
  UNCATEGORIZED_SECTION_NAME,
} from '@/application/report-view/use-report-filter-taxonomy'
import type { ReportTag } from '@/domain/models/report'

const TAGS = (
  list: Array<[string, string?]>
): ReportTag[] =>
  list.map(([tagName, categoryName]) => ({ tag_name: tagName, category_name: categoryName }))

describe('buildTagSections', () => {
  it('阶梯①：快照自带 category_name 时按分类分组，「未分类」尾组置末', () => {
    const tags = TAGS([
      ['拨测', '功能'],
      ['回归', '功能'],
      ['压测', '性能'],
      ['手工', '手工'],
    ])
    const sections = buildTagSections(
      ['回归', '拨测', '手工', '压测'],
      tags
    )
    expect(sections.map((s) => s.name)).toEqual(['功能', '手工', '性能'])
    expect(sections.map((s) => s.key)).not.toContain(UNCATEGORIZED_SECTION_KEY)
    expect(sections[0].tags).toEqual(['回归', '拨测'])
    expect(sections[1].tags).toEqual(['手工'])
    expect(sections[2].tags).toEqual(['压测'])
  })

  it('阶梯②：快照无分类字段时用 by-category 兜底分组', () => {
    const tags = TAGS([
      ['拨测'],
      ['回归'],
      ['压测'],
    ])
    const byCategory = new Map([
      ['回归', '功能'],
      ['拨测', '功能'],
      ['压测', '性能'],
    ])
    const sections = buildTagSections(['回归', '拨测', '压测'], tags, byCategory)
    expect(sections.map((s) => s.name)).toEqual(['功能', '性能'])
    expect(sections[0].tags).toEqual(['回归', '拨测'])
    expect(sections[1].tags).toEqual(['压测'])
  })

  it('阶梯①>②：快照分类优先，by-category 只补缺', () => {
    const tags = TAGS([
      ['回归', '功能'],
      ['压测'], // 快照无分类 → 由 by-category 补
      ['手工'], // 快照与 by-category 都无 → 未分类
    ])
    const byCategory = new Map([
      ['回归', '回归大类'], // 与快照冲突，快照优先
      ['压测', '性能'],
    ])
    const sections = buildTagSections(['回归', '压测', '手工'], tags, byCategory)
    const func = sections.find((s) => s.name === '功能')
    const perf = sections.find((s) => s.name === '性能')
    const uncat = sections.find((s) => s.key === UNCATEGORIZED_SECTION_KEY)
    expect(func?.tags).toEqual(['回归'])
    expect(perf?.tags).toEqual(['压测'])
    expect(uncat?.name).toBe(UNCATEGORIZED_SECTION_NAME)
    expect(uncat?.tags).toEqual(['手工'])
    // 「未分类」恒为尾组
    expect(sections[sections.length - 1].key).toBe(UNCATEGORIZED_SECTION_KEY)
  })

  it('全未分类时只出「未分类」单组；by-category 空映射不报错', () => {
    const tags = TAGS([['孤立'], ['无家']])
    const sections = buildTagSections(['孤立', '无家'], tags, new Map())
    expect(sections).toHaveLength(1)
    expect(sections[0].key).toBe(UNCATEGORIZED_SECTION_KEY)
    expect(sections[0].tags).toEqual(['孤立', '无家'])
  })
})
