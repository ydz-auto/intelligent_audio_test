/**
 * 时间轴对比资源下拉回显（INT-2676）：value 用「全部」哨兵，触发器应回显「全部资源」而非原始「全部」。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'
import { TimelineComparison } from '@/features/report-view/components/case-report-detail/timeline-comparison'

vi.mock('@/application/report-view/use-timeline-comparison', () => ({
  useTimelineComparison: () => ({
    scale: 1,
    zoom: () => undefined,
    resetZoom: () => undefined,
    selectedSpeaker: '全部',
    setSelectedSpeaker: () => undefined,
    build: () => ({
      referenceSegments: [],
      resultSegments: [],
      effectiveDuration: 10,
      speakers: ['全部', '发言人A'],
    }),
  }),
}))

const CASE_ITEM = {
  id: 'case-1',
  name: '用例',
  tags: [],
  metrics: {},
  results: [],
  audios: [],
} as ReportCaseItem

const REPORT = { summary: {} } as unknown as ReportDetailData

describe('时间轴对比资源下拉回显（INT-2676）', () => {
  it('资源触发器显示「全部资源」，不暴露「全部」原始 value', () => {
    render(<TimelineComparison caseItem={CASE_ITEM} report={REPORT} />)
    const resourceTrigger = screen.getAllByRole('combobox')[0]
    expect(resourceTrigger).toHaveTextContent('全部资源')
  })
})
