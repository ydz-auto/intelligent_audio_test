/**
 * groupRankings 单测（14_benchmark排行.md §9 实施清单 #2 分组边界）：
 * (metricCode × scenarioKey) 分组 + 组内 rank 升序；
 * 边界：并列名次共享 rank / 单主体不归一化 score100 为空 / 场景缺省「通用」。
 */
import { describe, expect, it } from 'vitest'

import { groupRankings } from '@/application/rankings/groupRankings'
import type { RankingRow } from '@/domain/models/benchmark'

function makeRow(overrides: Partial<RankingRow>): RankingRow {
  return {
    id: 1,
    source: 'platform_test',
    category: 'asr',
    metricCode: 'wer',
    metricName: '字错率',
    unit: '%',
    direction: 'lower_is_better',
    rank: 1,
    total: 3,
    percentile: 10,
    score100: 95,
    subjectName: '主体A',
    subjectType: 'closed_source',
    deviceType: 'physical',
    benchmarkSuite: 'general',
    scenarioKey: '通用',
    metricValue: 2.4,
    gapBest: 0,
    gapMedian: -0.5,
    deltaExternal: null,
    publishedTaskId: 1001,
    publishedTaskVersion: 1,
    reportId: 1201,
    baselineId: null,
    computedAt: '2026-10-16T09:20:00',
    ...overrides,
  }
}

describe('groupRankings', () => {
  it('按 (metricCode × scenarioKey) 分组并组内 rank 升序', () => {
    const rows = [
      makeRow({ id: 1, rank: 2, scenarioKey: '通用' }),
      makeRow({ id: 2, rank: 1, scenarioKey: '通用' }),
      makeRow({ id: 3, rank: 1, metricCode: 'ttlw', scenarioKey: '多轮' }),
      makeRow({ id: 4, rank: 1, scenarioKey: '噪声' }),
    ]
    const groups = groupRankings(rows)

    expect(groups).toHaveLength(3)
    const werGeneral = groups.find(
      (g) => g.metricCode === 'wer' && g.scenarioKey === '通用'
    )
    expect(werGeneral?.rows.map((r) => r.rank)).toEqual([1, 2])
    expect(groups.find((g) => g.metricCode === 'ttlw')?.scenarioKey).toBe('多轮')
    expect(groups.find((g) => g.scenarioKey === '噪声')).toBeDefined()
  })

  it('并列名次共享同一 rank（组内不破坏并列）', () => {
    const rows = [
      makeRow({ id: 1, rank: 1 }),
      makeRow({ id: 2, rank: 1 }),
      makeRow({ id: 3, rank: 3 }),
    ]
    const [group] = groupRankings(rows)
    expect(group.rows.map((r) => r.rank)).toEqual([1, 1, 3])
  })

  it('场景缺省「通用」：空 scenarioKey 归入默认场景', () => {
    const rows = [makeRow({ id: 1, scenarioKey: '' })]
    const [group] = groupRankings(rows)
    expect(group.scenarioKey).toBe('通用')
  })

  it('单主体不归一化：score100 为空保持为空（不杜撰分值）', () => {
    const rows = [makeRow({ id: 1, score100: null })]
    const [group] = groupRankings(rows)
    expect(group.rows[0].score100).toBeNull()
  })

  it('组携带共享 total（参与对比模型数）', () => {
    const rows = [
      makeRow({ id: 1, total: 8 }),
      makeRow({ id: 2, total: 8 }),
    ]
    const [group] = groupRankings(rows)
    expect(group.total).toBe(8)
  })

  it('空输入返回空组', () => {
    expect(groupRankings([])).toEqual([])
  })
})
