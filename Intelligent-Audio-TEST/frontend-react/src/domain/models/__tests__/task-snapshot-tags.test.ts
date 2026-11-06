/**
 * 冻结报告快照读模型：用例标签归一化（INT-1650）。
 * 后端 `report_snapshot.cases[].tags` 是对象数组（`{ name }`），视图层拿到的必须是字符串数组，
 * 否则 `.join('、')` 会把每个标签渲染成 `[object Object]`。
 */
import { describe, expect, it } from 'vitest'

import { readReportSnapshot, readReportSummary, toTagNames } from '@/domain/models/task'

describe('toTagNames', () => {
  it('对象数组取 name', () => {
    expect(toTagNames([{ name: '拒识' }, { name: '多次拒识-用户Backchannel拒识' }])).toEqual([
      '拒识',
      '多次拒识-用户Backchannel拒识',
    ])
  })

  it('同源对象里存在非字符串 name 时取字符串形态', () => {
    expect(toTagNames([{ name: 123 }, { id: 1, name: '标签' }])).toEqual(['123', '标签'])
  })

  it('字符串数组原样保留（兼容存量快照）', () => {
    expect(toTagNames(['拒识', '噪声'])).toEqual(['拒识', '噪声'])
  })

  it('过滤空值与非标签元素', () => {
    expect(toTagNames([{ name: '' }, null, undefined, 0, {}, '标签'])).toEqual(['标签'])
  })

  it('非数组入参返回空数组', () => {
    expect(toTagNames(undefined)).toEqual([])
    expect(toTagNames(null)).toEqual([])
    expect(toTagNames('拒识')).toEqual([])
  })
})

describe('readReportSnapshot', () => {
  const raw = {
    schemaVersion: 2,
    sourceReportId: 564,
    name: '冻结报告',
    status: 'published',
    summary: { totalCases: 188, passRate: 0.9 },
    cases: [
      {
        id: 1,
        testCaseId: 'case-1',
        name: '拒识用例',
        category: '拒识',
        tags: [{ name: '拒识' }, { name: '多次拒识-用户Backchannel拒识' }],
        metrics: { 准确率: 0.9 },
      },
      {
        id: 2,
        testCaseId: 'case-2',
        name: '无标签用例',
        tags: [],
        metrics: {},
      },
    ],
  }

  it('null / 非对象返回 null', () => {
    expect(readReportSnapshot(null)).toBeNull()
  })

  it('把每个用例的 tags 归一化成 string[]，其余字段原样保留', () => {
    const snapshot = readReportSnapshot(raw)
    expect(snapshot).not.toBeNull()
    expect(snapshot?.cases).toHaveLength(2)
    expect(snapshot?.cases?.[0].tags).toEqual(['拒识', '多次拒识-用户Backchannel拒识'])
    expect(snapshot?.cases?.[0].tags.join('、')).toBe('拒识、多次拒识-用户Backchannel拒识')
    expect(snapshot?.cases?.[1].tags).toEqual([])
    expect(snapshot?.cases?.[0].name).toBe('拒识用例')
    expect(snapshot?.cases?.[0].category).toBe('拒识')
    expect(snapshot?.cases?.[0].metrics).toEqual({ 准确率: 0.9 })
    expect(snapshot?.sourceReportId).toBe(564)
    expect(snapshot?.name).toBe('冻结报告')
  })

  it('缺 tags 字段的用例补空数组，不残留 undefined', () => {
    const snapshot = readReportSnapshot({
      name: '冻结报告',
      status: 'published',
      cases: [{ id: 3, testCaseId: 'case-3' }],
    })
    expect(snapshot?.cases?.[0].tags).toEqual([])
  })

  it('原快照对象不被就地修改', () => {
    const source = {
      name: '冻结报告',
      status: 'published',
      cases: [{ id: 1, testCaseId: 'case-1', tags: [{ name: '拒识' }] }],
    }
    readReportSnapshot(source)
    expect(source.cases[0].tags).toEqual([{ name: '拒识' }])
  })

  it('无 cases 的存量快照走空态判定', () => {
    const snapshot = readReportSnapshot({ name: '冻结报告', status: 'published' })
    expect(snapshot?.cases).toBeUndefined()
    expect(readReportSummary(snapshot).caseCount).toBeNull()
  })
})
