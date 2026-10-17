/**
 * 子视图客户端聚合纯函数测试（domain/lib/sub-view-aggregation，11_用例域.md §3.5/§3.6）。
 * groupCasesByTag：多标签多卡、无标签→「未设置标签」桶（末尾）、按用例数降序、色值/分类角标解析、总时长。
 * groupCasesByCaseGroup：按分组聚合、无分组→「未分组」桶（末尾）、按用例数降序。
 */
import { describe, expect, it } from 'vitest'

import {
  groupCasesByCaseGroup,
  groupCasesByTag,
} from '@/domain/lib/sub-view-aggregation'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TagItem } from '@/domain/models/testTag'

const MOCK_TAGS: TagItem[] = [
  { id: 11, name: '1人', description: null, color: '#f97316', categoryId: 1, categoryName: '人数', createdAt: null, updatedAt: null },
  { id: 21, name: '客厅', description: null, color: '#06b6d4', categoryId: 2, categoryName: '场景', createdAt: null, updatedAt: null },
]

const base = (id: string, patch: Partial<TestCaseListItem>): TestCaseListItem => ({
  id,
  name: `用例 ${id}`,
  description: null,
  groupId: null,
  groupName: null,
  type: 'e2e',
  tags: [],
  algorithmType: 'asr-v3',
  createdAt: null,
  updatedAt: null,
  isFavorite: false,
  deleted: false,
  deletedAt: null,
  deletedByUserId: null,
  totalDuration: 10,
  rounds: 1,
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
    expect(onePerson?.cases.map((c) => c.id)).toEqual(['tc-1', 'tc-2'])
    expect(onePerson?.color).toBe('#f97316')
    expect(onePerson?.categoryName).toBe('人数')
    expect(onePerson?.totalDuration).toBe(90)
    expect(living?.cases.map((c) => c.id)).toEqual(['tc-1'])
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
    expect(last.cases.map((c) => c.id)).toEqual(['tc-b', 'tc-c'])
    expect(last.color).toBeNull()
  })

  it('全部无标签时仅返回「未设置标签」桶', () => {
    const groups = groupCasesByTag([base('tc-1', { tags: [] })], MOCK_TAGS)
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('未设置标签')
  })
})

describe('groupCasesByCaseGroup', () => {
  it('按 group_id/group_name 聚合，子组头文案取分组名', () => {
    const cases = [
      base('tc-1', { groupId: 'g1', groupName: '智能音箱功能测试' }),
      base('tc-2', { groupId: 'g1', groupName: '智能音箱功能测试' }),
      base('tc-3', { groupId: 'g2', groupName: '车载语音交互' }),
    ]
    const groups = groupCasesByCaseGroup(cases)
    expect(groups).toHaveLength(2)
    const g1 = groups.find((g) => g.key === 'g1')
    expect(g1?.label).toBe('智能音箱功能测试')
    expect(g1?.cases.map((c) => c.id)).toEqual(['tc-1', 'tc-2'])
    expect(g1?.totalDuration).toBe(20)
  })

  it('无分组用例归入「未分组」桶且置于末尾', () => {
    const cases = [
      base('tc-1', { groupId: 'g1', groupName: '分组一' }),
      base('tc-2', { groupId: null, groupName: null }),
      base('tc-3', { groupId: null, groupName: null }),
    ]
    const groups = groupCasesByCaseGroup(cases)
    const last = groups[groups.length - 1]
    expect(last.label).toBe('未分组')
    expect(last.key).toBe('__ungrouped__')
    expect(last.cases.map((c) => c.id)).toEqual(['tc-2', 'tc-3'])
  })

  it('全部无分组时仅返回「未分组」桶', () => {
    const groups = groupCasesByCaseGroup([base('tc-1', { groupId: null })])
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('未分组')
  })

  it('审计 P3-2 防御：groupId 非空但 groupName 缺失时 label 以 groupId 兜底，不与真「未分组」桶混淆', () => {
    const groups = groupCasesByCaseGroup([
      base('tc-1', { groupId: 'g1', groupName: null }),
      base('tc-2', { groupId: null, groupName: null }),
    ])
    const g1 = groups.find((g) => g.key === 'g1')
    expect(g1?.label).toBe('g1')
    // 真「未分组」桶保持 key/label 固定，置于末尾
    const last = groups[groups.length - 1]
    expect(last.key).toBe('__ungrouped__')
    expect(last.label).toBe('未分组')
  })
})
