/**
 * 统计页任务上下文选择 + 「评估指标」卡 hint 单测（INT-1802）。
 * 真实库实测：报告 566（task_id=527）的 task 已物理删除、报告行 task_name 为空，
 * 旧逻辑只判 task_id>0 便拿它当 case-averages 上下文 → POST /reports/case-averages 400，
 * 评估指标 / 设备性能整卡空态。这里固化两条口径：
 * 1) 统计上下文只取「task_id>0 且任务名非空」的最近任务报告（对比/benchmark 报告 task_id=0 跳过）；
 * 2) 任务名缺失时 hint 不拼「任务「」」。
 */
import { describe, expect, it } from 'vitest'

import type { ReportCounts, ReportListItem } from '@/domain/models/report'
import type { ReportCaseAveragesData } from '@/domain/models/report-statistics'

import { isStatisticsTaskCandidate, toReportStatisticsData } from '../use-report-statistics'

function report(patch: Partial<ReportListItem> & { id: number }): ReportListItem {
  return {
    name: `报告 ${patch.id}`,
    type: 'task',
    task_name: '',
    summary: { total_cases: 0, completed_cases: 0, failed_cases: 0, pass_rate: 0 },
    status: 'published',
    created_at: '2026-10-23 12:00:00',
    ...patch,
  }
}

/** 主库 2026-10-25 实测形状：566 指向已删任务 527（task_name 空）、564 指向在库任务 413 */
const deletedTaskReport = report({ id: 566, task_id: 527, task_name: '' })
const aliveTaskReport = report({ id: 564, task_id: 413, task_name: '环境理解小艺E2E测试任务' })
const comparisonReport = report({ id: 567, type: 'comparison', task_id: 0, task_name: '' })

const counts: ReportCounts = { all: 66, draft: 60, published: 6, comparison: 9 }

const averages: ReportCaseAveragesData = {
  totalCases: 50,
  totalResults: 50,
  overallAverages: [{ id: 133, metric: '拒识场景裁判', value: 0.02 }],
  metricData: [{ resource: '9-pura90小艺-1.0.0' }],
  resources: ['9-pura90小艺-1.0.0'],
}

function metricsHint(input: {
  averages: ReportCaseAveragesData | null
  task?: { id: number; name: string } | null
  averagesLoading?: boolean
}): string {
  const data = toReportStatisticsData({
    counts,
    reports: [aliveTaskReport],
    averages: input.averages,
    task: input.task ?? null,
    dimension: 'time',
    range: {},
    averagesLoading: input.averagesLoading,
  })
  return data.summary.find((item) => item.key === 'metrics')!.hint
}

describe('isStatisticsTaskCandidate', () => {
  it('跳过已删任务（task_name 为空）的报告', () => {
    expect(isStatisticsTaskCandidate(deletedTaskReport)).toBe(false)
  })

  it('跳过纯空白任务名', () => {
    expect(isStatisticsTaskCandidate(report({ id: 1, task_id: 9, task_name: '   ' }))).toBe(false)
  })

  it('跳过对比 / 二次对比 / benchmark 报告（task_id=0）', () => {
    expect(isStatisticsTaskCandidate(comparisonReport)).toBe(false)
    expect(isStatisticsTaskCandidate(report({ id: 2, task_id: undefined }))).toBe(false)
  })

  it('认任务仍在（task_name 非空）的任务报告', () => {
    expect(isStatisticsTaskCandidate(aliveTaskReport)).toBe(true)
  })
})

describe('统计上下文选择顺序', () => {
  it('最新一份是已删任务报告时，落到下一份任务仍在的报告', () => {
    const reports = [deletedTaskReport, aliveTaskReport, comparisonReport]
    expect(reports.find(isStatisticsTaskCandidate)).toBe(aliveTaskReport)
  })

  it('没有任何任务仍在的报告时不选上下文（不回落到已删任务）', () => {
    const reports = [deletedTaskReport, comparisonReport]
    expect(reports.find(isStatisticsTaskCandidate)).toBeUndefined()
  })
})

describe('评估指标卡 hint', () => {
  it('有统计数据时显示「任务「<任务名>」评估指标」', () => {
    expect(metricsHint({ averages, task: { id: 413, name: aliveTaskReport.task_name } })).toBe(
      '任务「环境理解小艺E2E测试任务」评估指标'
    )
  })

  it('任务名缺失时不再拼「任务「」」', () => {
    expect(metricsHint({ averages, task: null })).toBe('任务评估指标')
    expect(metricsHint({ averages, task: { id: 413, name: '' } })).toBe('任务评估指标')
  })

  it('无统计数据：加载中显示「统计加载中…」，否则「暂无任务执行数据」', () => {
    expect(metricsHint({ averages: null, task: { id: 413, name: 'x' }, averagesLoading: true })).toBe(
      '统计加载中…'
    )
    expect(metricsHint({ averages: null })).toBe('暂无任务执行数据')
  })
})
