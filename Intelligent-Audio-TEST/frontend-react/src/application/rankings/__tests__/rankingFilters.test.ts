/**
 * rankingFilters 单测（14_benchmark排行.md §9 实施清单 #2）：
 * URL search ↔ 筛选状态；非法值回退默认；重置可见性判定。
 */
import { describe, expect, it } from 'vitest'

import {
  DEFAULT_RANKING_SEARCH,
  hasActiveFilters,
  rankingSearchSchema,
  searchToFilters,
} from '@/application/rankings/rankingFilters'

describe('rankingSearchSchema', () => {
  it('缺省字段为 optional：parse({}) 键缺失不抛错（默认合并由页面层承担）', () => {
    const parsed = rankingSearchSchema.parse({})
    expect(parsed).toEqual({})
  })

  it('合法值原样保留', () => {
    const parsed = rankingSearchSchema.parse({
      category: 'asr',
      suite: 'general',
      metricCode: 'wer',
      source: 'platform_test',
      subjectName: '远场',
      algorithm: 'asr-v3',
    })
    expect(parsed.category).toBe('asr')
    expect(parsed.suite).toBe('general')
    expect(parsed.metricCode).toBe('wer')
    expect(parsed.source).toBe('platform_test')
    expect(parsed.subjectName).toBe('远场')
    expect(parsed.algorithm).toBe('asr-v3')
  })

  it('非法值类型 catch 回退默认（不抛 400）', () => {
    const parsed = rankingSearchSchema.parse({ category: 123 as unknown as string })
    expect(parsed.category).toBe('')
  })
})

describe('searchToFilters', () => {
  it('algorithm 不入排行筛选（页内 store 字段）', () => {
    const filters = searchToFilters({ ...DEFAULT_RANKING_SEARCH, algorithm: 'asr-v3' })
    expect(filters).not.toHaveProperty('algorithm')
    expect(filters.subjectName).toBe('')
  })
})

describe('hasActiveFilters', () => {
  it('全默认 → false；任一非默认 → true', () => {
    expect(hasActiveFilters(searchToFilters(DEFAULT_RANKING_SEARCH))).toBe(false)
    expect(
      hasActiveFilters(
        searchToFilters({ ...DEFAULT_RANKING_SEARCH, category: 'tts' })
      )
    ).toBe(true)
  })
})
