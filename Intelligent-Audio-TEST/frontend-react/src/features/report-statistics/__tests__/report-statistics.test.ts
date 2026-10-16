/**
 * 报告统计分析（INT-500 §2.2）：统计卡四枚 + 四标签页常量 + 各维度行数据确定性。
 */
import { describe, expect, it } from 'vitest'

import { computeStatistics } from '@/application/report-statistics/use-report-statistics'
import { STATISTIC_TABS, STATISTIC_DIMENSIONS } from '@/features/report-statistics/constants'

describe('报告统计分析（INT-500）', () => {
  it('四标签页：统计维度/统计结果/趋势分析/报表生成', () => {
    expect(STATISTIC_TABS.map((t) => t.label)).toEqual([
      '统计维度',
      '统计结果',
      '趋势分析',
      '报表生成',
    ])
  })

  it('四维统计：时间/任务类型/设备类型/评估维度', () => {
    expect(STATISTIC_DIMENSIONS.map((d) => d.label)).toEqual([
      '时间',
      '任务类型',
      '设备类型',
      '评估维度',
    ])
  })

  it('统计卡四枚（报告数量/用例执行/评估指标/设备性能）', () => {
    const data = computeStatistics('time')
    expect(data.summary.map((s) => s.label)).toEqual([
      '报告数量',
      '测试用例执行',
      '评估指标',
      '设备性能',
    ])
  })

  it('不同维度产出不同统计行，且都含散点/热力图数据', () => {
    const time = computeStatistics('time')
    const metric = computeStatistics('metric')
    expect(time.rows[0].dimension).not.toBe(metric.rows[0].dimension)
    expect(time.scatter.datasets[0].data.length).toBeGreaterThan(0)
    expect(time.heatmap.datasets[0].data.length).toBeGreaterThan(0)
  })
})
