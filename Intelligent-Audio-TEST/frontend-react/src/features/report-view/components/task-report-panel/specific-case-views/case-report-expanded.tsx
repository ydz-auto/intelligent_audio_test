/**
 * 用例卡展开区容器（15_报告域.md §3.3.7，INT-1774）。
 *
 * 装「结果对比」叶表 + `CaseReportDetail` 七块，并**承载每卡一份 `activeRoundTab`**：
 * 叶表轮次 Tab 与评分指标块 / 执行结果块的轮次 Tab 共用同一个 `activeRoundTab`（照 V9.7.10
 * `TestCaseReportDetail.vue:1157` 单实例）；状态为会话内存、不持久化、不进 URL。
 * 详情 Dialog（§4.7）不入本容器——由 `CaseReportDetail` 自建一份轮次轴、始终全显。
 */
import { useMemo } from 'react'

import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'
import {
  buildLeafMetricColumns,
  collectMetricKeys,
  type MergedReportCase,
  type ReportCaseView,
} from '@/application/report-view/report-case-view-model'
import { useCaseRoundTabs } from '@/application/report-view/use-case-round-tabs'
import {
  isBlockVisible,
  type CaseDisplaySettings,
} from '@/application/report-view/use-case-display-settings'

import { CaseReportDetailView } from '../../case-report-detail'
import { ResultComparisonTable } from './result-comparison-table'

export interface CaseReportExpandedProps {
  caseItem: ReportCaseItem
  /** 叶表行集锚点（三视图） */
  view: ReportCaseView
  resourceKey?: string
  resultType?: string
  report: ReportDetailData
  /** 区级显示设置（不传 = 全显） */
  display?: CaseDisplaySettings
  /** 隐藏全部内容时的「恢复默认」回调（§3.5.10 兜底） */
  onRestoreDisplay?: () => void
  /** 显示设置「评估维度」已选（去轮次后缀的基础维度名） */
  selectedBaseDimensions: string[]
  /** 显示设置「叶表包含子维度」（默认关） */
  includeSubDimensions: boolean
  /** 子维度名集合（叶表默认不出子维度列） */
  subDimensionNames: string[]
  /** 显示设置「轮次」已选（= 可用轮次集，叶表 Tab 候选与评分指标块轮次范围）；无轮次 chip 时为 undefined */
  selectedRounds?: string[]
  /** 显示设置「轮次」chips 被全清（显式标志，不能用空数组反推——单轮报告本就无 chip） */
  roundsAllCleared?: boolean
  /** 显示设置已选资源 / 结果类型（叶表行集） */
  selectedResources: string[]
  selectedResultTypes: string[]
  /** 「未选择轮次」时打开工具栏显示设置 */
  onOpenDisplaySettings?: () => void
}

export function CaseReportExpanded({
  caseItem,
  view,
  resourceKey,
  resultType,
  report,
  display,
  onRestoreDisplay,
  selectedBaseDimensions,
  includeSubDimensions,
  subDimensionNames,
  selectedRounds,
  roundsAllCleared = false,
  selectedResources,
  selectedResultTypes,
  onOpenDisplaySettings,
}: CaseReportExpandedProps) {
  // 一张用例卡一个轮次轴（叶表 / 评分指标 / 执行结果共用）
  const roundState = useCaseRoundTabs(caseItem, selectedRounds, roundsAllCleared)

  /** 叶表指标列 = 已选主维度（一维一列；取值键按当前激活轮次后缀，列头不带轮次） */
  const leafColumns = useMemo(() => {
    if (roundState.noRoundSelected) return []
    return buildLeafMetricColumns(
      collectMetricKeys([caseItem]),
      selectedBaseDimensions,
      roundState.activeRoundTag,
      includeSubDimensions,
      subDimensionNames
    )
  }, [
    caseItem,
    roundState.noRoundSelected,
    roundState.activeRoundTag,
    selectedBaseDimensions,
    includeSubDimensions,
    subDimensionNames,
  ])

  const showResultComparison = display ? isBlockVisible(display, 'resultComparison') : true

  return (
    <div className='space-y-4 border-t p-3'>
      {showResultComparison && (
        <ResultComparisonTable
          caseItem={caseItem as MergedReportCase}
          view={view}
          resourceKey={resourceKey}
          resultType={resultType}
          headers={report.summary.resource_headers}
          allMetrics={report.summary.all_metrics}
          columns={leafColumns}
          selectedResources={selectedResources}
          selectedResultTypes={selectedResultTypes}
          roundTabs={roundState.roundTabs}
          activeRoundTab={roundState.activeRoundTab}
          onActiveRoundTabChange={roundState.setActiveRoundTab}
          noRoundSelected={roundState.noRoundSelected}
          onOpenDisplaySettings={onOpenDisplaySettings}
        />
      )}

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
