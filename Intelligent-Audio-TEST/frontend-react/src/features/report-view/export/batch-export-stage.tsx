/**
 * 批量 HTML 导出离屏宿主（INT-2419）。
 *
 * 报告中心没有「报告详情页面」可克隆，批量导出要把每一份渲染成与详情页同一棵组件树再快照。
 * 这里把 `ReportViewBody` 渲染在一个固定宽度、移出视口的容器里（保留布局与绘制：VChart 需要有尺寸
 * 的容器才能出图，`display:none` / 零尺寸会得到空白 canvas），并按 DOM 属性向编排层报告状态：
 * - `data-batch-export-stage` + `data-batch-export-report-id`：当前渲染的是哪一份；
 * - `data-batch-export-state`：`loading` 取数中 / `ready` 已渲染可快照 / `error` 取数失败；
 * - `data-batch-export-error`：失败原因（取数失败时）。
 *
 * 导出态 `isExporting` 与详情页一致：展开全部分区、强制全量用例；采集结束由编排层卸载本组件，
 * 离屏 DOM 与取数缓存随之释放，与真实页面状态无关。
 */
import { useMemo } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useReportDetail } from '@/application/report-view/use-report-detail'
import { useReportReviews } from '@/application/report-view/useReportReviews'
import { ApiError } from '@/infrastructure/api/api-error'

import { ReportViewBody } from '@/features/report-view/components/report-view-body'
import {
  BATCH_STAGE_ATTR,
  BATCH_STAGE_ERROR_ATTR,
  BATCH_STAGE_REPORT_ATTR,
  BATCH_STAGE_STATE_ATTR,
  BATCH_STAGE_WIDTH,
  REPORT_VIEW_ROOT_CLASS,
  type BatchStageState,
} from './batch-html-snapshot'

export interface BatchExportStageProps {
  reportId: number
}

function stageErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.userMessage || error.message
  if (error instanceof Error) return error.message
  return '报告取数失败'
}

export function BatchExportStage({ reportId }: BatchExportStageProps) {
  const detailQuery = useReportDetail(reportId)
  const report = detailQuery.data
  const { hasPermission } = usePermissions()
  // 与详情页同源：报告头「已复核 N 条」徽章（0 不渲染），源任务 query 与用例区共用缓存
  const reviews = useReportReviews(report)

  const state = useMemo<BatchStageState>(() => {
    if (detailQuery.isError) return 'error'
    // 报告头复核徽章来自源任务详情（与详情页同源）；未解析完就快照会少徽章
    if (report && !reviews.taskLoading) return 'ready'
    return 'loading'
  }, [detailQuery.isError, report, reviews.taskLoading])

  const stageAttrs: Record<string, string> = {
    [BATCH_STAGE_ATTR]: '',
    [BATCH_STAGE_REPORT_ATTR]: String(reportId),
    [BATCH_STAGE_STATE_ATTR]: state,
  }
  if (state === 'error') {
    stageAttrs[BATCH_STAGE_ERROR_ATTR] = stageErrorMessage(detailQuery.error)
  }

  return (
    <div
      {...stageAttrs}
      aria-hidden='true'
      style={{
        position: 'fixed',
        top: 0,
        // 移出视口但保留布局与绘制；不用 display:none / 零尺寸（VChart 需要容器尺寸）
        left: -100000,
        width: BATCH_STAGE_WIDTH,
        zIndex: -1,
        pointerEvents: 'none',
        background: '#ffffff',
      }}
    >
      <div className={REPORT_VIEW_ROOT_CLASS}>
        {report ? (
          <ReportViewBody
            report={report}
            isExporting
            editing={false}
            hasPermission={hasPermission}
            canEdit={false}
            onStartEditing={() => undefined}
            onExitEditing={() => undefined}
            onSaveAnalysis={() => undefined}
            reviewCount={reviews.reviewCount}
            header={{
              backLabel: '返回',
              onBack: () => undefined,
              onRename: () => undefined,
              onPublish: () => undefined,
              onUnpublish: () => undefined,
              onExport: () => undefined,
              onRegenerate: () => undefined,
              onCopyLink: () => undefined,
              onShare: () => undefined,
              onClose: () => undefined,
            }}
          />
        ) : null}
      </div>
    </div>
  )
}
