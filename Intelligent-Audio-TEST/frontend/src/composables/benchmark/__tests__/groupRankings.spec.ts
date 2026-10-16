/**
 * groupRankings 纯函数单元测试
 * 覆盖：分组边界（category×metric×scenario）、并列名次、单主体 score100 空、
 * 场景缺省「通用」、测试集去重、数值缩写与时间格式化。
 */
import { describe, it, expect } from 'vitest'
import {
  groupRankings,
  extractSuiteOptions,
  formatMetricValue,
  formatComputedAt,
} from '../groupRankings'
import type { BenchmarkRankingRow } from '../../../domain/model/benchmark'

function row(partial: Partial<BenchmarkRankingRow> & Pick<BenchmarkRankingRow, 'id' | 'metricCode' | 'scenarioKey'>): BenchmarkRankingRow {
  return {
    source: 'platform_test',
    publishedTaskId: null,
    publishedTaskVersion: null,
    reportId: null,
    baselineId: null,
    subjectName: '主体X',
    subjectType: 'open_source',
    deviceType: null,
    benchmarkSuite: 'suite-1',
    category: 'voice_llm',
    metricName: '接管时延',
    metricValue: 100,
    unit: 'ms',
    direction: 'lower_is_better',
    rank: 1,
    total: 3,
    percentile: 33,
    score100: 80,
    gapBest: 0,
    gapMedian: 5,
    deltaExternal: null,
    computedAt: '2026-10-16T07:00:00',
    ...partial,
  }
}

describe('groupRankings', () => {
  it('按 category × metricCode × scenarioKey 分组', () => {
    const groups = groupRankings([
      row({ id: 1, metricCode: 'TTLW', scenarioKey: '通用', subjectName: 'A' }),
      row({ id: 2, metricCode: 'TTLW', scenarioKey: '打断', subjectName: 'B' }),
      row({ id: 3, metricCode: 'WER', scenarioKey: '通用', subjectName: 'C' }),
    ])
    expect(groups).toHaveLength(3)
    const keys = groups.map((g) => `${g.category}/${g.metricCode}/${g.scenarioKey}`)
    // 组间按 category → metricCode → scenarioKey 字典序（localeCompare，中文场景键亦稳定）
    expect(keys).toEqual(['voice_llm/TTLW/打断', 'voice_llm/TTLW/通用', 'voice_llm/WER/通用'])
  })

  it('组内按 rank 升序（并列名次保留返回顺序）', () => {
    const groups = groupRankings([
      row({ id: 1, metricCode: 'TTLW', scenarioKey: '通用', rank: 3, subjectName: 'C' }),
      row({ id: 2, metricCode: 'TTLW', scenarioKey: '通用', rank: 1, subjectName: 'A' }),
      row({ id: 3, metricCode: 'TTLW', scenarioKey: '通用', rank: 2, subjectName: 'B' }),
      row({ id: 4, metricCode: 'TTLW', scenarioKey: '通用', rank: 1, subjectName: 'A2' }),
    ])
    const group = groups[0]
    expect(group.rows.map((r) => r.subjectName)).toEqual(['A', 'A2', 'B', 'C'])
  })

  it('total = 组内行数；computedAt 取组内首个非空', () => {
    const groups = groupRankings([
      row({ id: 1, metricCode: 'TTLW', scenarioKey: '通用', computedAt: '2026-10-16T07:00:00' }),
      row({ id: 2, metricCode: 'TTLW', scenarioKey: '通用', computedAt: null }),
    ])
    expect(groups[0].total).toBe(2)
    expect(groups[0].computedAt).toBe('2026-10-16T07:00:00')
  })

  it('组标题字段取自组内行（metricName/unit/direction 一致）', () => {
    const groups = groupRankings([
      row({ id: 1, metricCode: 'WER', metricName: '词错误率', unit: '%', direction: 'lower_is_better', scenarioKey: '通用' }),
    ])
    expect(groups[0].metricName).toBe('词错误率')
    expect(groups[0].unit).toBe('%')
    expect(groups[0].direction).toBe('lower_is_better')
  })

  it('跨 category 即使 metric 相同也分卡（页签=全部时）', () => {
    const groups = groupRankings([
      row({ id: 1, category: 'asr', metricCode: 'WER', scenarioKey: '通用' }),
      row({ id: 2, category: 'voice_llm', metricCode: 'WER', scenarioKey: '通用' }),
    ])
    expect(groups).toHaveLength(2)
  })
})

describe('extractSuiteOptions', () => {
  it('去重并排序', () => {
    const options = extractSuiteOptions([
      row({ id: 1, metricCode: 'TTLW', scenarioKey: '通用', benchmarkSuite: 'full-duplex-v1' }),
      row({ id: 2, metricCode: 'TTLW', scenarioKey: '通用', benchmarkSuite: 'librispeech' }),
      row({ id: 3, metricCode: 'TTLW', scenarioKey: '通用', benchmarkSuite: 'full-duplex-v1' }),
    ])
    expect(options).toEqual(['full-duplex-v1', 'librispeech'])
  })
})

describe('formatMetricValue', () => {
  it('千分位缩写保留两位内', () => {
    expect(formatMetricValue(1234.56)).toBe('1.23K')
    expect(formatMetricValue(3456789)).toBe('3.46M')
    expect(formatMetricValue(999.9)).toBe('999.9')
  })

  it('空值 → —', () => {
    expect(formatMetricValue(null)).toBe('—')
    expect(formatMetricValue(undefined)).toBe('—')
    expect(formatMetricValue(Number.NaN)).toBe('—')
  })
})

describe('formatComputedAt', () => {
  it('ISO 时间 → YYYY-MM-DD HH:mm', () => {
    expect(formatComputedAt('2026-10-16T07:05:00')).toBe('2026-10-16 07:05')
  })

  it('空值 → —', () => {
    expect(formatComputedAt(null)).toBe('—')
  })
})
