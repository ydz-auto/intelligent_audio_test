/**
 * 报告具体用例分组客户端聚合纯函数测试（15_报告域.md §3.3.7「用例卡片分组」，INT-1049）。
 * groupReportCasesByCategory：按分类聚合、未分类→「未分类」桶（末尾）、按用例数降序。
 * groupReportCasesByTag：多标签多卡、无标签→「未设置标签」桶（末尾）、按用例数降序、色值/分类角标解析。
 */
import { describe, expect, it } from 'vitest'

import {
  groupReportCasesByCategory,
  groupReportCasesByTag,
  type ReportCaseSubGroup,
} from '../specific-case-grouping'
import type { ReportCaseItem } from '@/domain/models/report'
import type { TagItem } from '@/domain/models/testTag'

const MOCK_TAGS: TagItem[] = [
  { id: 11, name: '1人', description: null, color: '#f97316', categoryId: 1, categoryName: '人数', createdAt: null, updatedAt: null },
  { id: 21, name: '客厅', description: null, color: '#06b6d4', categoryId: 2, categoryName: '场景', createdAt: null, updatedAt: null },
]

const base = (id: string, patch: Partial<ReportCaseItem>): ReportCaseItem => ({
  id,
  name: `用例 ${id}`,
  tags: [],
  metrics: {},
  results: [],
  audios: [],
  ...patch,
})

describe('groupReportCasesByCategory', () => {
  it('按分类聚合，组头取分类名', () => {
    const cases = [
      base('tc-1', { category: '智能音箱功能测试' }),
      base('tc-2', { category: '智能音箱功能测试' }),
      base('tc-3', { category: '车载语音交互' }),
    ]
    const groups = groupReportCasesByCategory(cases)
    expect(groups).toHaveLength(2)
    const g1 = groups.find((g) => g.key === '智能音箱功能测试')
    expect(g1?.label).toBe('智能音箱功能测试')
    expect(g1?.cases.map((c) => c.id)).toEqual(['tc-1', 'tc-2'])
  })

  it('无分类用例归入「未分类」桶且置于末尾', () => {
    const cases = [
      base('tc-1', { category: '分组一' }),
      base('tc-2', {}),
      base('tc-3', {}),
    ]
    const groups = groupReportCasesByCategory(cases)
    const last = groups[groups.length - 1]
    expect(last.label).toBe('未分类')
    expect(last.key).toBe('__uncategorized__')
    expect(last.cases.map((c) => c.id)).toEqual(['tc-2', 'tc-3'])
  })

  it('全部未分类时仅返回「未分类」桶', () => {
    const groups = groupReportCasesByCategory([base('tc-1', {})])
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('未分类')
  })

  it('子组默认按用例数降序（同数按名称升序稳定）', () => {
    const cases = [
      base('tc-a', { category: 'B 组', name: '用例 a' }),
      base('tc-b', { category: 'A 组', name: '用例 b' }),
      base('tc-c', { category: 'A 组', name: '用例 c' }),
    ]
    const groups = groupReportCasesByCategory(cases)
    // A 组 2 条 → B 组 1 条
    expect(groups[0].label).toBe('A 组')
    expect(groups[0].cases.map((c) => c.id)).toEqual(['tc-b', 'tc-c'])
    expect(groups[1].label).toBe('B 组')
  })

  it('空分类字符串按未分类处理', () => {
    const cases = [base('tc-1', { category: '' })]
    const groups = groupReportCasesByCategory(cases)
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('未分类')
  })

  it('后端哨兵「未分类」与真实组名共存时归兜底桶且置于末尾（不把哨兵当真实组名）', () => {
    const cases = [
      base('tc-1', { category: '智能音箱功能测试' }),
      base('tc-2', { category: '未分类' }),
      base('tc-3', { category: '未分类' }),
    ]
    const groups = groupReportCasesByCategory(cases)
    const last = groups[groups.length - 1]
    expect(groups).toHaveLength(2)
    expect(groups[0].label).toBe('智能音箱功能测试')
    expect(last.label).toBe('未分类')
    expect(last.key).toBe('__uncategorized__')
    expect(last.cases.map((c) => c.id)).toEqual(['tc-2', 'tc-3'])
  })
})

describe('groupReportCasesByTag', () => {
  it('多标签用例在每个命中的标签子组各呈现一次；色值/分类角标从登记表解析', () => {
    const cases = [
      base('tc-1', { tags: ['1人', '客厅'] }),
      base('tc-2', { tags: ['1人'] }),
    ]
    const groups = groupReportCasesByTag(cases, MOCK_TAGS)
    expect(groups).toHaveLength(2)
    const onePerson = groups.find((g) => g.label === '1人')
    const living = groups.find((g) => g.label === '客厅')
    expect(onePerson?.cases.map((c) => c.id)).toEqual(['tc-1', 'tc-2'])
    expect(onePerson?.color).toBe('#f97316')
    expect(onePerson?.categoryName).toBe('人数')
    expect(living?.cases.map((c) => c.id)).toEqual(['tc-1'])
    // 子组默认按用例数降序（1人 2 条 → 客厅 1 条）
    expect(groups[0].label).toBe('1人')
  })

  it('登记表无该标签时色值/分类角标为 null', () => {
    const groups = groupReportCasesByTag([base('tc-1', { tags: ['未知标签'] })], MOCK_TAGS)
    expect(groups).toHaveLength(1)
    expect(groups[0].color).toBeNull()
    expect(groups[0].categoryName).toBeNull()
  })

  it('无标签用例归入「未设置标签」桶且置于末尾', () => {
    const cases = [
      base('tc-a', { tags: ['1人'] }),
      base('tc-b', { tags: [] }),
      base('tc-c', { tags: [] }),
    ]
    const groups = groupReportCasesByTag(cases, MOCK_TAGS)
    const last = groups[groups.length - 1]
    expect(last.label).toBe('未设置标签')
    expect(last.key).toBe('__untagged__')
    expect(last.cases.map((c) => c.id)).toEqual(['tc-b', 'tc-c'])
  })

  it('全部无标签时仅返回「未设置标签」桶', () => {
    const groups = groupReportCasesByTag([base('tc-1', { tags: [] })], MOCK_TAGS)
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('未设置标签')
  })

  it('返回类型保持 ReportCaseItem（组内用例卡消费全字段）', () => {
    const groups = groupReportCasesByTag(
      [base('tc-1', { tags: ['1人'], category: '智能音箱' })],
      MOCK_TAGS
    )
    const typed = groups as ReportCaseSubGroup[]
    expect(typed[0].cases[0].category).toBe('智能音箱')
  })
})
