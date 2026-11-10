/**
 * 导出用例卡筛选/排序事实单测（INT-2434 二轮）。
 * 口径对齐后端：指标名去轮次后缀、跨资源（含多轮后缀）取平均。
 */
import { describe, expect, it } from 'vitest'

import type { ReportCaseItem } from '@/domain/models/report'

import { caseMetricAverages, caseMetricNames } from '../case-metrics'

function makeCase(metrics: ReportCaseItem['metrics']): ReportCaseItem {
  return {
    id: 'case-1',
    name: '用例一',
    tags: [],
    metrics,
    results: [],
    audios: [],
  }
}

describe('caseMetricNames', () => {
  it('dict 格式去轮次后缀并去重', () => {
    const item = makeCase({
      'device-1': { '接管率@round:1': 0.9, '接管率@round:2': 0.7, 误接管率: 0.1 },
      'device-2': { '接管率@round:1': 0.8 },
    })
    expect(caseMetricNames(item)).toEqual(['接管率', '误接管率'])
  })

  it('list 格式同样去后缀', () => {
    const item = makeCase([
      {
        resource: 'device-1',
        metrics: [
          { metric: '接管率', value: 0.8 },
          { metric: '时延@overall', value: 1200 },
        ],
      },
    ])
    expect(caseMetricNames(item)).toEqual(['接管率', '时延'])
  })
})

describe('caseMetricAverages', () => {
  it('跨资源 + 跨轮次取平均（与后端排序口径一致）', () => {
    const item = makeCase({
      'device-1': { '接管率@round:1': 0.9, '接管率@round:2': 0.7 },
      'device-2': { 接管率: 0.8 },
    })
    const averages = caseMetricAverages(item)
    expect(averages['接管率']).toBeCloseTo((0.9 + 0.7 + 0.8) / 3)
  })

  it('非数值指标跳过，无指标时返回空对象', () => {
    const item = makeCase({ 'device-1': { 说明: Number.NaN } })
    expect(caseMetricAverages(item)).toEqual({})
  })
})
