/**
 * 报告详情正文（INT-2419）：详情页与「批量 HTML 导出」离屏宿主共用的同一套组件树。
 *
 * 单份导出（INT-2418）克隆的是页面 DOM，批量导出要拿到「同一份报告单独打开导出」的产物，
 * 就必须渲染同一棵报告组件树，而不是另写一份简化布局。这里把 `/report/$reportId` 的正文
 * （报告头 → 按 type 分发的主面板 → 报告文档区）提出来，两边共用。
 *
 * 右导航 `aside` 与底部操作条都被快照清理规则整块移除（`aside` / `.print:hidden`），
 * 因此做成可选插槽：详情页传，离屏宿主不传，不影响导出产物。
 */
import type { ReactNode } from 'react'

import { StudioDocumentSection } from '@/features/reports/components/studio-document-section'
import { StudioSourceType } from '@/domain/models/report-studio'
import type { ReportDetailData } from '@/domain/models/report'

import { ReportHeader } from './report-header'
import { BenchmarkRankingBlock } from './benchmark-ranking-block'
import { TaskReportPanel } from './task-report-panel'
import { ComparisonReportPanel } from './comparison-report-panel'

export interface ReportViewBodyProps {
  report: ReportDetailData
  /** 导出态：展开全部分区、强制全量用例、强制显示全部裁剪项 */
  isExporting?: boolean
  editing: boolean
  hasPermission: (permission: string) => boolean
  /** report:update 权限（§6 RBAC：无权限 readonly 冻结快照，隐藏编辑钮） */
  canEdit: boolean
  onStartEditing: () => void
  onExitEditing: () => void
  onSaveAnalysis: (content: string) => void
  reviewCount?: number
  onReviewStatsClick?: () => void
  /** 报告头操作组回调（离屏宿主传空实现） */
  header: {
    backLabel: string
    onBack: () => void
    onRename: () => void
    onPublish: () => void
    onUnpublish: () => void
    onExport: () => void
    onRegenerate: () => void
    onCopyLink: () => void
    onShare: () => void
    onClose: () => void
  }
  /** 右导航（详情页传；离屏宿主不传） */
  readingNav?: ReactNode
  /** 底部操作条（详情页传；离屏宿主不传） */
  bottomActions?: ReactNode
}

export function ReportViewBody({
  report,
  isExporting,
  editing,
  hasPermission,
  canEdit,
  onStartEditing,
  onExitEditing,
  onSaveAnalysis,
  reviewCount,
  onReviewStatsClick,
  header,
  readingNav,
  bottomActions,
}: ReportViewBodyProps) {
  const isComparison = report.type === 'comparison' || report.type === 'secondary_comparison'

  return (
    <div className='mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6'>
      <ReportHeader
        report={report}
        hasPermission={hasPermission}
        editing={editing}
        backLabel={header.backLabel}
        onBack={header.onBack}
        onEdit={() => (editing ? onExitEditing() : onStartEditing())}
        onSave={onExitEditing}
        onRename={header.onRename}
        onPublish={header.onPublish}
        onUnpublish={header.onUnpublish}
        onExport={header.onExport}
        onRegenerate={header.onRegenerate}
        onCopyLink={header.onCopyLink}
        onShare={header.onShare}
        onClose={header.onClose}
        reviewCount={reviewCount}
        onReviewStatsClick={onReviewStatsClick}
      />

      <div className='mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px]'>
        <main className='min-w-0 space-y-6'>
          {report.type === 'benchmark' && (
            <BenchmarkRankingBlock reportId={report.id} reportName={report.name} />
          )}
          {isComparison ? (
            <ComparisonReportPanel
              report={report}
              isExporting={isExporting}
              editing={editing}
              canEdit={canEdit}
              onStartEditing={onStartEditing}
              onExitEditing={onExitEditing}
              onSaveAnalysis={onSaveAnalysis}
            />
          ) : (
            <TaskReportPanel
              report={report}
              isExporting={isExporting}
              editing={editing}
              canEdit={canEdit}
              onStartEditing={onStartEditing}
              onExitEditing={onExitEditing}
              onSaveAnalysis={onSaveAnalysis}
            />
          )}

          {/* 报告文档区（INT-1766 3a/3c）：固定 report_id + source_type=platform_report，
              上传的独立报告不混进平台报告文档列表（后端 list_documents 契约口径） */}
          {hasPermission('report:read') && (
            <section id='report-documents' className='scroll-mt-20'>
              <StudioDocumentSection
                description='本报告的平台报告文档。上传的独立报告不在本列表，见报告中心「更多操作 → 报告文档」。'
                emptyText='该报告暂无平台报告文档'
                reportId={report.id}
                sourceType={StudioSourceType.PLATFORM_REPORT}
                title='报告文档'
              />
            </section>
          )}
        </main>

        {readingNav ? <aside className='print:hidden'>{readingNav}</aside> : null}
      </div>

      {bottomActions ? (
        <div className='print:hidden sticky bottom-3 z-10 mt-8'>
          <div className='bg-background/95 supports-[backdrop-filter]:bg-background/60 flex flex-wrap items-center justify-end gap-2 rounded-xl border p-2 shadow-lg backdrop-blur-lg'>
            {bottomActions}
          </div>
        </div>
      ) : null}
    </div>
  )
}
