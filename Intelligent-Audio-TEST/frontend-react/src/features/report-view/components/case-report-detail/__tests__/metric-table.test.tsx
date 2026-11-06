/**
 * 评分指标块（INT-2120）：报告域恒走对比模式——单资源也出轮次 Tab（与叶表 / 执行结果共用
 * activeRoundTab），行集 = 当前轮 currentRoundMetricKeys；单轮用例无 Tab、行集不变。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'
import { useCaseRoundTabs } from '@/application/report-view/use-case-round-tabs'

import { MetricTable } from '../metric-table'

function makeReport(metricNames: string[]): ReportDetailData {
  return {
    id: 1,
    name: '报告',
    type: 'task',
    task_name: '任务',
    status: 'completed',
    created_at: '2026-10-28T00:00:00',
    summary: {
      all_metrics: metricNames.map((name) => ({ name })),
      resource_headers: [],
    },
  } as unknown as ReportDetailData
}

function makeCase(metricKeys: [string, number][], resource = 'dev1'): ReportCaseItem {
  return {
    id: 'case-1',
    name: '用例',
    metrics: [
      {
        resource,
        metrics: metricKeys.map(([metric, value]) => ({ metric, value })),
      },
    ],
  } as unknown as ReportCaseItem
}

function Harness({ caseItem, report }: { caseItem: ReportCaseItem; report: ReportDetailData }) {
  const roundState = useCaseRoundTabs(caseItem)
  return (
    <MetricTable
      caseItem={caseItem}
      report={report}
      roundTabs={roundState.roundTabs}
      activeRoundTab={roundState.activeRoundTab}
      setActiveRoundTab={roundState.setActiveRoundTab}
      currentRoundMetricKeys={roundState.currentRoundMetricKeys}
      noRoundSelected={roundState.noRoundSelected}
    />
  )
}

describe('评分指标恒对比模式：单资源也出轮次 Tab（INT-2120）', () => {
  const report = makeReport(['WER', '打断成功数量'])
  const multiRoundCase = makeCase([
    ['WER@overall', 5],
    ['打断成功数量@overall', 6],
    ['WER@round:1', 1],
    ['打断成功数量@round:1', 2],
    ['WER@round:2', 3],
    ['打断成功数量@round:2', 4],
  ])

  it('单资源多轮用例：渲染「第 1 轮 / 第 2 轮 / 整体」Tab，资源列照常保留', () => {
    render(<Harness caseItem={multiRoundCase} report={report} />)
    expect(screen.getByRole('tablist', { name: '轮次切换' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '第 1 轮' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '第 2 轮' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '整体' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'dev1' })).toBeInTheDocument()
  })

  it('默认「整体」只显示 overall 行集', () => {
    render(<Harness caseItem={multiRoundCase} report={report} />)
    expect(screen.getByText('5.00')).toBeInTheDocument()
    expect(screen.getByText('6.00')).toBeInTheDocument()
    expect(screen.queryByText('1.00')).toBeNull()
    expect(screen.queryByText('3.00')).toBeNull()
  })

  it('点「第 2 轮」后行集换成 round:2（不再三个轮次混排）', () => {
    render(<Harness caseItem={multiRoundCase} report={report} />)
    fireEvent.click(screen.getByRole('tab', { name: '第 2 轮' }))
    expect(screen.getByText('3.00')).toBeInTheDocument()
    expect(screen.getByText('4.00')).toBeInTheDocument()
    expect(screen.queryByText('5.00')).toBeNull()
    expect(screen.queryByText('1.00')).toBeNull()
    expect(screen.queryByText('2.00')).toBeNull()
  })

  it('单轮用例（指标键无轮次后缀）：无 Tab，行集与现网一致', () => {
    render(
      <Harness
        caseItem={makeCase([
          ['WER', 7],
          ['打断成功数量', 8],
        ])}
        report={report}
      />
    )
    expect(screen.queryByRole('tablist', { name: '轮次切换' })).toBeNull()
    expect(screen.getByText('7.00')).toBeInTheDocument()
    expect(screen.getByText('8.00')).toBeInTheDocument()
  })
})
