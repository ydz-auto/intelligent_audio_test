/**
 * Benchmark 报告排行快照分组纯函数测试（INT-483）
 * 覆盖：groupSnapshotRows (category × metric × scenario) 分组 + 组内 rank 升序 + 字典序稳定排序、
 * directionLabel / formatMetricValue 文案工具。
 */
import { describe, it, expect } from 'vitest'
import {
  groupSnapshotRows,
  directionLabel,
  formatMetricValue,
} from '../benchmarkReportGroups'
import type { BenchmarkSnapshotRow } from '../../../domain/model/benchmarkReport'

function row(partial: Partial<BenchmarkSnapshotRow>): BenchmarkSnapshotRow {
  return {
    id: 1,
    source: 'platform_test',
    publishedTaskId: null,
    publishedTaskVersion: null,
    reportId: null,
    baselineId: null,
    subjectName: '模型A',
    subjectType: 'closed_source',
    deviceType: null,
    benchmarkSuite: 'suite-1',
    category: 'asr',
    metricCode: 'WER',
    metricName: '字错误率',
    metricValue: 8.5,
    unit: '%',
    direction: 'lower_is_better',
    rank: 1,
    total: 3,
    percentile: null,
    score100: null,
    gapBest: null,
    gapMedian: null,
    deltaExternal: null,
    scenarioKey: '通用',
    computedAt: '2026-10-16T07:00:00',
    ...partial,
  }
}

describe('groupSnapshotRows', () => {
  it('按 (category × metricCode × scenarioKey) 分组，组内按 rank 升序', () => {
    const groups = groupSnapshotRows([
      row({ id: 1, rank: 3, subjectName: 'C' }),
      row({ id: 2, rank: 1, subjectName: 'A' }),
      row({ id: 3, rank: 2, subjectName: 'B' }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].rows.map((r) => r.subjectName)).toEqual(['A', 'B', 'C'])
    expect(groups[0].total).toBe(3)
  })

  it('不同指标/类别/场景拆分为独立组，输出按字典序稳定排序', () => {
    const groups = groupSnapshotRows([
      row({ id: 1, category: 'tts', metricCode: 'MOS', scenarioKey: 'S2' }),
      row({ id: 2, category: 'asr', metricCode: 'WER', scenarioKey: '通用' }),
      row({ id: 3, category: 'asr', metricCode: 'CER', scenarioKey: '通用' }),
    ])
    expect(groups.map((g) => g.metricCode)).toEqual(['CER', 'WER', 'MOS'])
    expect(groups.every((g) => g.total > 0)).toBe(true)
  })

  it('空行返回空组', () => {
    expect(groupSnapshotRows([])).toEqual([])
  })
})

describe('directionLabel', () => {
  it('已知方向返回中文标签，未知值回退原文', () => {
    expect(directionLabel('lower_is_better')).toBe('越低越好')
    expect(directionLabel('higher_is_better')).toBe('越高越好')
    expect(directionLabel('unknown_dir')).toBe('unknown_dir')
  })
})

describe('formatMetricValue', () => {
  it('数值缩写与空值兜底', () => {
    expect(formatMetricValue(1234)).toBe('1.23K')
    expect(formatMetricValue(0)).toBe('0')
    expect(formatMetricValue(null)).toBe('—')
    expect(formatMetricValue(undefined)).toBe('—')
    expect(formatMetricValue(Number.NaN)).toBe('—')
  })
})
