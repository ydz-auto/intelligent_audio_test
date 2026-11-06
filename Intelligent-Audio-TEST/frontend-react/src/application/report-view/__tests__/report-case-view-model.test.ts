/**
 * 具体用例三视图纯函数单测（15_报告域.md §3.3.7 / §3.5.10，INT-1738 / INT-1774）。
 * 覆盖：按 test_case_id 合并与资源并集、结果类型解析与显隐判定、三视图聚合、
 * 叶表行集 / 列集（一维一列，轮次改 Tab 后不再是列维度）、显示设置隐藏计数。
 */
import { describe, expect, it } from 'vitest'

import type { ReportCaseItem, ReportResourceHeader } from '@/domain/models/report'

import {
  buildLeafMetricColumns,
  buildResultComparisonRows,
  buildTransposedMetricRows,
  collectRounds,
  groupCasesByResource,
  groupCasesByResultType,
  hasNonDefaultResultType,
  mergeCaseRowsByCaseId,
  parseResultType,
} from '../report-case-view-model'
import {
  countHiddenOptions,
  DEFAULT_CASE_DISPLAY_SETTINGS,
  isBlockVisible,
} from '../use-case-display-settings'

const headers: ReportResourceHeader[] = [
  { key: '9-pura90小艺-1.0.0', label: 'pura90小艺', type: 'device', version: '1.0.0' },
  { key: '10-pura90豆包-1.0.0', label: 'pura90豆包', type: 'device', version: '1.0.0' },
]

/** 一行 = 一个用例 × 一个资源（真实库 report_cases 行粒度） */
function row(
  id: string,
  resource: string,
  metrics: Record<string, number>,
  status = 'completed'
): ReportCaseItem {
  return {
    id,
    name: `用例 ${id}`,
    tags: ['会议'],
    metrics: { [resource]: metrics },
    results: [{ resource, status, startTime: '2026-09-23T05:10:00Z' }],
    audios: [{ audio_id: 'a1', audio_name: '音频1' }],
    algorithmResults: [{ paramCode: 'answer@round:1', device: resource, value: 'ok' }],
    logs: `log-${resource}`,
  }
}

describe('parseResultType', () => {
  it('resource_headers.result_type 非空即用', () => {
    expect(
      parseResultType('dev-1', [{ key: 'dev-1', label: '设备', result_type: 'Realtime' }])
    ).toBe('realtime')
  })

  it('资源键后缀命中白名单', () => {
    expect(parseResultType('9-pura90小艺-1.0.0-recording')).toBe('recording')
  })

  it('解析不出 → 默认', () => {
    expect(parseResultType('9-pura90小艺-1.0.0')).toBe('default')
    expect(parseResultType(undefined)).toBe('default')
  })

  it('全部为默认时不渲染结果类型视图档', () => {
    expect(hasNonDefaultResultType(['9-pura90小艺-1.0.0'])).toBe(false)
    expect(hasNonDefaultResultType(['9-dev-recording'])).toBe(true)
  })
})

describe('mergeCaseRowsByCaseId', () => {
  it('同一 test_case_id 多资源行合并为一张卡，results / metrics / 日志按资源并集', () => {
    const merged = mergeCaseRowsByCaseId([
      row('c1', '9-pura90小艺-1.0.0', { 接管率占比: 0.75 }),
      row('c1', '10-pura90豆包-1.0.0', { 接管率占比: 1.0 }),
      row('c2', '9-pura90小艺-1.0.0', { 接管率占比: 0.5 }),
    ])

    expect(merged).toHaveLength(2)
    const c1 = merged[0]
    expect(c1.results.map((r) => r.resource)).toEqual([
      '10-pura90豆包-1.0.0',
      '9-pura90小艺-1.0.0',
    ])
    // dict 格式按资源合并键
    const metrics = c1.metrics as Record<string, Record<string, number>>
    expect(metrics['9-pura90小艺-1.0.0']['接管率占比']).toBe(0.75)
    expect(metrics['10-pura90豆包-1.0.0']['接管率占比']).toBe(1.0)
    // 音频按 audio_id 去重、algorithmResults 按 (paramCode, device) 去重
    expect(c1.audios).toHaveLength(1)
    expect(c1.algorithmResults).toHaveLength(2)
    // 日志各资源不同 → 按资源保留
    expect(c1.resourceLogs).toEqual({
      '9-pura90小艺-1.0.0': 'log-9-pura90小艺-1.0.0',
      '10-pura90豆包-1.0.0': 'log-10-pura90豆包-1.0.0',
    })
  })

  it('数组格式 metrics 按资源去重合并', () => {
    const a: ReportCaseItem = {
      ...row('c1', 'r1', {}),
      metrics: [{ resource: 'r1', metrics: [{ metric: 'WER', value: 1 }] }],
    }
    const b: ReportCaseItem = {
      ...row('c1', 'r2', {}),
      metrics: [{ resource: 'r2', metrics: [{ metric: 'WER', value: 2 }] }],
    }
    const merged = mergeCaseRowsByCaseId([a, b])[0]
    expect(Array.isArray(merged.metrics)).toBe(true)
    const groups = merged.metrics as { resource: string }[]
    expect(groups.map((g) => g.resource).sort()).toEqual(['r1', 'r2'])
  })
})

describe('三视图聚合', () => {
  const merged = mergeCaseRowsByCaseId([
    row('c1', '9-pura90小艺-1.0.0', { 接管率占比: 0.75 }),
    row('c1', '10-pura90豆包-1.0.0', { 接管率占比: 1.0 }),
    row('c2', '9-pura90小艺-1.0.0', { 接管率占比: 0.5 }),
  ])

  it('设备视图按资源聚合，计数为去重用例数', () => {
    const nodes = groupCasesByResource(merged, headers)
    expect(nodes.map((n) => n.key)).toEqual(['9-pura90小艺-1.0.0', '10-pura90豆包-1.0.0'])
    expect(nodes[0].count).toBe(2)
    expect(nodes[0].name).toBe('pura90小艺')
    expect(nodes[1].count).toBe(1)
  })

  it('结果类型视图按 result_type 聚合，「默认」恒末尾', () => {
    const withType = mergeCaseRowsByCaseId([
      row('c1', '9-dev-recording', {}),
      row('c2', '9-dev-1.0.0', {}),
    ])
    const nodes = groupCasesByResultType(withType)
    expect(nodes.map((n) => n.key)).toEqual(['recording', 'default'])
    expect(nodes[0].label).toBe('录音')
    expect(nodes[1].label).toBe('默认')
  })
})

describe('叶表行集 / 列集', () => {
  const merged = mergeCaseRowsByCaseId([
    row('c1', '9-pura90小艺-1.0.0', { '接管率占比@overall': 0.75 }),
    row('c1', '10-pura90豆包-1.0.0', { '接管率占比@overall': 1.0 }),
  ])[0]

  it('用例视图 = 设备 × result_type', () => {
    const rows = buildResultComparisonRows(merged, { view: 'case', headers })
    expect(rows).toHaveLength(2)
    expect(rows.every((r) => r.resultType === 'default')).toBe(true)
    expect(rows[0].metrics['接管率占比@overall']).toBeDefined()
  })

  it('设备视图 = 当前资源的 result_type', () => {
    const rows = buildResultComparisonRows(merged, {
      view: 'resource',
      resourceKey: '9-pura90小艺-1.0.0',
      headers,
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].resultType).toBe('default')
    expect(rows[0].status).toBe('completed')
  })

  it('结果类型视图 = 当前 result_type 下的设备', () => {
    const rows = buildResultComparisonRows(merged, {
      view: 'resultType',
      resultType: 'default',
      headers,
    })
    expect(rows.map((r) => r.resource).sort()).toEqual([
      '10-pura90豆包-1.0.0',
      '9-pura90小艺-1.0.0',
    ])
  })

  it('显示设置全不选时行集为空（∩ 不当作「不过滤」）', () => {
    const rows = buildResultComparisonRows(merged, {
      view: 'resultType',
      resultType: 'default',
      headers,
      selectedResources: [],
    })
    expect(rows).toHaveLength(0)
  })

  it('轮次集合按轮次升序、「整体」末位', () => {
    expect(collectRounds(['A@round:2', 'A@overall', 'A@round:1'])).toEqual([
      'round:1',
      'round:2',
      'overall',
    ])
  })

  it('叶表列 = 已选主维度一维一列，列头不带轮次后缀（INT-1774）', () => {
    const keys = ['接管率占比@overall', '接管率占比@round:1', '评分@overall', '打断次数@overall']
    const columns = buildLeafMetricColumns(
      keys,
      ['接管率占比', '评分', '打断次数'],
      'overall',
      false,
      ['评分']
    )
    expect(columns.map((c) => c.metricKey)).toEqual([
      '接管率占比@overall',
      '打断次数@overall',
    ])
    // 列头只用基础维度名，不带「（整体）」后缀
    expect(columns.map((c) => c.label)).toEqual(['接管率占比', '打断次数'])

    const withSub = buildLeafMetricColumns(
      keys,
      ['接管率占比', '评分', '打断次数'],
      'overall',
      true,
      ['评分']
    )
    expect(withSub.map((c) => c.base)).toEqual(['接管率占比', '评分', '打断次数'])
  })

  it('切换轮次 Tab 只换取值键，列数不变', () => {
    const keys = ['接管率占比@overall', '接管率占比@round:1', '打断次数@overall', '打断次数@round:1']
    const dims = ['接管率占比', '打断次数']
    const overall = buildLeafMetricColumns(keys, dims, 'overall', false)
    const round1 = buildLeafMetricColumns(keys, dims, 'round:1', false)
    expect(overall.map((c) => c.key)).toEqual(round1.map((c) => c.key))
    expect(overall.map((c) => c.label)).toEqual(round1.map((c) => c.label))
    expect(round1.map((c) => c.metricKey)).toEqual([
      '接管率占比@round:1',
      '打断次数@round:1',
    ])
  })

  it('单轮用例（无轮次后缀）列取基础维度键', () => {
    const columns = buildLeafMetricColumns(['接管率占比', '打断次数'], ['接管率占比'], null, false)
    expect(columns[0].metricKey).toBe('接管率占比')
    expect(columns[0].label).toBe('接管率占比')
    expect(columns[0].round).toBe('')
  })

  it('本用例没有的维度不出列（不产整列「—」）', () => {
    const columns = buildLeafMetricColumns(['A@overall'], ['A', 'B'], 'overall', false)
    expect(columns.map((c) => c.base)).toEqual(['A'])
  })
})

describe('转置后叶表指标行（INT-2089）', () => {
  const metricConfigs = [
    { name: '接管率占比', dimension_type: 'main' as const, decimal_places: 2 },
    { name: 'WER', dimension_type: 'main' as const, decimal_places: 2 },
    { name: '主观评分', dimension_type: 'sub' as const, parent_dimension_name: 'WER' },
    { name: '平均延迟', dimension_type: 'sub' as const, parent_dimension_name: 'WER' },
  ]

  const columns = buildLeafMetricColumns(
    ['接管率占比@overall', 'WER@overall', '主观评分@overall', '平均延迟@overall'],
    ['接管率占比', 'WER', '主观评分', '平均延迟'],
    'overall',
    true,
    ['主观评分', '平均延迟']
  )

  it('主维度一行、子维度归父维度组缩进、组内子维度中文排序', () => {
    const rows = buildTransposedMetricRows(columns, metricConfigs)
    // 接管率占比：独立主维度行
    expect(rows[0]).toMatchObject({ name: '接管率占比', isSubDim: false, metricKey: '接管率占比@overall' })
    // WER 组：主维度行兼组头 + 两个子维度（中文排序：平均延迟 < 主观评分）
    const wer = rows.slice(1)
    expect(wer[0]).toMatchObject({ name: 'WER', isGroupHeader: true, isSubDim: false })
    expect(wer[1]).toMatchObject({ name: '平均延迟', isSubDim: true, metricKey: '平均延迟@overall' })
    expect(wer[2]).toMatchObject({ name: '主观评分', isSubDim: true, metricKey: '主观评分@overall' })
  })

  it('组内只有子维度（父维度未选）时插独立分组标题行', () => {
    const subOnly = buildLeafMetricColumns(
      ['主观评分@overall', '平均延迟@overall'],
      ['主观评分', '平均延迟'],
      'overall',
      true,
      ['主观评分', '平均延迟']
    )
    const rows = buildTransposedMetricRows(subOnly, metricConfigs)
    expect(rows[0]).toMatchObject({ name: 'WER', isGroupHeader: true, isSubDim: false, metricKey: '' })
    expect(rows[1]).toMatchObject({ name: '平均延迟', isSubDim: true })
    expect(rows[2]).toMatchObject({ name: '主观评分', isSubDim: true })
  })

  it('无子维度时无独立分组标题行（主维度行兼作分组标题）', () => {
    const mainOnly = buildLeafMetricColumns(
      ['接管率占比@overall', 'WER@overall'],
      ['接管率占比', 'WER'],
      'overall',
      false
    )
    const rows = buildTransposedMetricRows(mainOnly, metricConfigs)
    expect(rows).toHaveLength(2)
    // 主维度名 = 组名 → 主维度行兼作分组标题（V9.7.10 口径），无独立 hdr 行
    expect(rows.every((r) => r.metricKey !== '')).toBe(true)
    expect(rows.every((r) => !r.isSubDim)).toBe(true)
  })
})

describe('显示设置', () => {
  it('默认全选，隐藏项计数按各 Section 累加', () => {
    expect(countHiddenOptions(DEFAULT_CASE_DISPLAY_SETTINGS)).toBe(0)
    expect(
      countHiddenOptions({
        ...DEFAULT_CASE_DISPLAY_SETTINGS,
        hiddenBlocks: ['multiRound'],
        hiddenMetrics: ['评分'],
        hiddenResources: ['r1'],
      })
    ).toBe(3)
  })

  it('执行结果父开关与子项联动', () => {
    const settings = {
      ...DEFAULT_CASE_DISPLAY_SETTINGS,
      hiddenExecution: ['reference', 'caseParams', 'evaluation', 'deviceResults', 'timeline', 'audio'],
    } as typeof DEFAULT_CASE_DISPLAY_SETTINGS
    expect(isBlockVisible(settings, 'execution')).toBe(false)
    expect(
      isBlockVisible({ ...DEFAULT_CASE_DISPLAY_SETTINGS, hiddenBlocks: ['execution'] }, 'execution')
    ).toBe(false)
  })
})
