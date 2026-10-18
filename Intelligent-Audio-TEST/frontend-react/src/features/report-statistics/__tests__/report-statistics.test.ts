/**
 * 报告统计分析（INT-500 §2.2）：统计卡四枚 + 四标签页常量 + 真实数据装配确定性。
 * INT-643 接线：数据源已切真实端点（tab-counts/报告列表/case-averages），
 * 本测试覆盖纯函数 toReportStatisticsData 对真实形状数据的装配。
 */
import { describe, expect, it } from 'vitest'

import type { ReportCounts, ReportListItem } from '@/domain/models/report'
import type { ReportCaseAveragesData } from '@/domain/models/report-statistics'
import { toReportStatisticsData, type StatisticsTimeRange } from '@/application/report-statistics/use-report-statistics'
import { STATISTIC_TABS, STATISTIC_DIMENSIONS } from '@/features/report-statistics/constants'

const counts: ReportCounts = { all: 42, draft: 8, published: 34, comparison: 5, benchmark: 0 }

const reports: ReportListItem[] = [
  {
    id: 446,
    name: '任务报告_INT95R11_E2E',
    type: 'task',
    task_id: 64,
    task_name: 'task-64',
    task_type: 'e2e',
    device_type: 'smart_speaker',
    summary: { total_cases: 120, completed_cases: 110, failed_cases: 10, pass_rate: 91.7 },
    status: 'published',
    created_at: new Date(Date.now() - 3 * 24 * 3600 * 1000).toISOString(),
  },
  {
    id: 445,
    name: '对比报告',
    type: 'comparison',
    task_name: 'compare',
    task_type: 'api',
    device_type: 'car_voice',
    summary: { total_cases: 80, completed_cases: 75, failed_cases: 5, pass_rate: 93.8 },
    status: 'published',
    created_at: new Date(Date.now() - 40 * 24 * 3600 * 1000).toISOString(),
  },
]

const averages: ReportCaseAveragesData = {
  totalCases: 200,
  totalResults: 185,
  overallAverages: [
    { id: 1, metric: '唤醒成功率', value: 95.8 },
    { id: 2, metric: '识别准确率', value: 93.1 },
  ],
  metricData: [
    {
      resource: '旗舰-01',
      metrics: [
        { id: 1, metric: '唤醒成功率', value: 96.5 },
        { id: 2, metric: '识别准确率', value: 94.2 },
      ],
    },
    {
      resource: '入门-03',
      metrics: [
        { id: 1, metric: '唤醒成功率', value: 93.1 },
        { id: 2, metric: '识别准确率', value: 91.8 },
      ],
    },
  ],
  resources: ['旗舰-01', '入门-03'],
  resourceHeaders: ['资源'],
}

const range: StatisticsTimeRange = {}

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

  it('统计卡四枚（报告数量/用例执行统计/评估指标/设备性能）真实装配', () => {
    const data = toReportStatisticsData({
      counts,
      reports,
      averages,
      task: { id: 64, name: 'task-64', type: 'e2e' },
      dimension: 'time',
      range,
    })
    expect(data.summary.map((s) => s.label)).toEqual([
      '报告数量',
      '测试用例执行统计',
      '评估指标',
      '设备性能',
    ])
    // 真实数据：报告数量=counts.all；用例=列表 summary 求和；指标/设备=case-averages
    expect(data.summary[0].value).toBe(42)
    expect(data.summary[1].value).toBe(200)
    expect(data.summary[2].value).toBe(2)
    expect(data.summary[3].value).toBe(2)
  })

  it('不同维度产出不同统计行，评估维度行来自 case-averages overall_averages', () => {
    const time = toReportStatisticsData({
      counts,
      reports,
      averages,
      task: null,
      dimension: 'time',
      range,
    })
    const metric = toReportStatisticsData({
      counts,
      reports,
      averages,
      task: null,
      dimension: 'metric',
      range,
    })
    expect(time.rows.map((r) => r.dimension)).toEqual(['今日', '近7天', '近30天'])
    expect(metric.rows.map((r) => r.dimension)).toEqual(['唤醒成功率', '识别准确率'])
    // 散点/热力来自 case-averages metric_data（资源×指标）
    expect(metric.heatmap.datasets[0].data.length).toBeGreaterThan(0)
  })

  it('无任务执行数据时评估指标/设备卡回落 0，异常识别为空态（不虚构）', () => {
    const data = toReportStatisticsData({
      counts,
      reports,
      averages: null,
      task: null,
      dimension: 'metric',
      range,
    })
    expect(data.summary[2].value).toBe(0)
    expect(data.summary[3].value).toBe(0)
    expect(data.anomalyRows).toEqual([])
  })
})
