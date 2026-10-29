/**
 * 用例卡展开区容器（15_报告域.md §3.3.7，INT-1774）。
 *
 * 只装 `CaseReportDetailView` 七块，并**承载每卡一份 `activeRoundTab`**：
 * 评分指标块 / 执行结果块的轮次 Tab 共用同一个 `activeRoundTab`（照 V9.7.10
 * `TestCaseReportDetail.vue:1157` 单实例）；状态为会话内存、不持久化、不进 URL。
 *
 * 原「结果对比」叶表已移除：其内容与评分指标块（设备/API × 维度对比）重复。
 */
import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'
import { useCaseRoundTabs } from '@/application/report-view/use-case-round-tabs'
import type { CaseDisplaySettings } from '@/application/report-view/use-case-display-settings'

import { CaseReportDetailView } from '../../case-report-detail'

export interface CaseReportExpandedProps {
  caseItem: ReportCaseItem
  report: ReportDetailData
  /** 区级显示设置（不传 = 全显） */
  display?: CaseDisplaySettings
  /** 隐藏全部内容时的「恢复默认」回调（§3.5.10 兜底） */
  onRestoreDisplay?: () => void
  /** 显示设置「轮次」已选（= 可用轮次集，评分指标块 / 执行结果块轮次范围）；无轮次 chip 时为 undefined */
  selectedRounds?: string[]
  /** 显示设置「轮次」chips 被全清（显式标志，不能用空数组反推——单轮报告本就无 chip） */
  roundsAllCleared?: boolean
}

export function CaseReportExpanded({
  caseItem,
  report,
  display,
  onRestoreDisplay,
  selectedRounds,
  roundsAllCleared = false,
}: CaseReportExpandedProps) {
  // 一张用例卡一个轮次轴（评分指标 / 执行结果共用）
  const roundState = useCaseRoundTabs(caseItem, selectedRounds, roundsAllCleared)

  return (
    <div className='space-y-4 border-t p-3'>
      <CaseReportDetailView
        caseItem={caseItem}
        report={report}
        display={display}
        onRestoreDisplay={onRestoreDisplay}
        roundState={roundState}
      />
    </div>
  )
}
