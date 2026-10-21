/**
 * 子视图客户端聚合纯函数测试（domain/lib/subViewAggregation，11_用例域.md §3.5/§3.6，INT-1103）。
 * groupCasesByTag：多标签多卡、无标签→「未设置标签」桶（末尾）、按用例数降序、色值/分类角标解析、总时长。
 * groupCasesByCaseGroup：按分组聚合、无分组→「未分组」桶（末尾）、按用例数降序。
 */
import { describe, expect, it } from 'vitest'

import {
  groupCasesByCaseGroup,
  groupCasesByTag,
  type CaseSubGroup,
  type SubViewCaseItem,
} from '../subViewAggregation'

const MOCK_TAGS = [
  { id: 11, name: '1人', color: '#f97316', categoryName: '人数' },
  { id: 21, name: '客厅', color: '#06b6d4', categoryName: '场景' },
]

const base = (id: string, patch: Partial<SubViewCaseItem>): SubViewCaseItem => ({
  tags: [],
  groupId: null,
  groupName: null,
  totalDuration: 10,
  ...patch,
})

describe('groupCasesByTag', () => {
  it('多标签用例在每个命中的标签子组各呈现一次；色值/分类角标从登记表解析', () => {
    const cases = [
      base('tc-1', { tags: ['1人', '客厅'], totalDuration: 60 }),
      base('tc-2', { tags: ['1人'], totalDuration: 30 }),
    ]
    const groups = groupCasesByTag(cases, MOCK_TAGS)
    expect(groups).toHaveLength(2)
    const onePerson = groups.find((g) => g.label === '1人')
    const living = groups.find((g) => g.label === '客厅')
    expect(onePerson?.cases.map((c) => c.tags)).toEqual([['1人', '客厅'], ['1人']])
    expect(onePerson?.color).toBe('#f97316')
    expect(onePerson?.categoryName).toBe('人数')
    expect(onePerson?.totalDuration).toBe(90)
    expect(living?.cases.map((c) => c.tags)).toEqual([['1人', '客厅']])
    // 子组默认按用例数降序（1人 2 条 → 客厅 1 条）
    expect(groups[0].label).toBe('1人')
  })

  it('无标签用例归入「未设置标签」桶且置于末尾', () => {
    const cases = [
      base('tc-a', { tags: ['1人'] }),
      base('tc-b', { tags: [] }),
      base('tc-c', { tags: [] }),
    ]
    const groups = groupCasesByTag(cases, MOCK_TAGS)
    const last = groups[groups.length - 1]
    expect(last.label).toBe('未设置标签')
    expect(last.key).toBe('__untagged__')
    expect(last.cases.map((c) => c.tags)).toEqual([[], []])
    expect(last.color).toBeNull()
  })

  it('全部无标签时仅返回「未设置标签」桶', () => {
    const groups = groupCasesByTag([base('tc-1', { tags: [] })], MOCK_TAGS)
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('未设置标签')
  })
})

describe('groupCasesByCaseGroup', () => {
  it('按 groupId/groupName 建桶；无分组归「未分组」桶置于末尾', () => {
    const cases: SubViewCaseItem[] = [
      { tags: [], groupId: 'g1', groupName: '唤醒', totalDuration: 30 },
      { tags: [], groupId: 'g2', groupName: '远场', totalDuration: 20 },
      { tags: [], groupId: null, groupName: null, totalDuration: 10 },
    ]
    const groups = groupCasesByCaseGroup(cases)
    const last = groups[groups.length - 1]
    expect(last.label).toBe('未分组')
    expect(last.key).toBe('__ungrouped__')
    expect(last.cases).toHaveLength(1)
    expect(last.totalDuration).toBe(10)
  })

  it('groupId 非空但 groupName 缺失时以 groupId 兜底 label，避免与真「未分组」桶混淆', () => {
    const cases: SubViewCaseItem[] = [
      { tags: [], groupId: 'g1', groupName: null, totalDuration: 5 },
      { tags: [], groupId: null, groupName: null, totalDuration: 3 },
    ]
    const groups = groupCasesByCaseGroup(cases)
    expect(groups[0].label).toBe('g1')
    expect(groups[0].key).toBe('g1')
    expect(groups[groups.length - 1].label).toBe('未分组')
  })

  it('子组默认按用例数降序（同数按名称升序）', () => {
    const cases: SubViewCaseItem[] = [
      { tags: [], groupId: 'g1', groupName: 'b组', totalDuration: 10 },
      { tags: [], groupId: 'g2', groupName: 'a组', totalDuration: 10 },
      { tags: [], groupId: 'g1', groupName: 'b组', totalDuration: 10 },
    ]
    const groups = groupCasesByCaseGroup(cases)
    expect(groups[0].label).toBe('b组') // 2 条 → 降序首位
    expect(groups[1].label).toBe('a组') // 1 条
  })

  it('子组总时长求和', () => {
    const cases: SubViewCaseItem[] = [
      { tags: [], groupId: 'g1', groupName: '组1', totalDuration: 40 },
      { tags: [], groupId: 'g1', groupName: '组1', totalDuration: 60 },
    ]
    const groups = groupCasesByCaseGroup(cases)
    expect(groups[0].totalDuration).toBe(100)
  })
})
