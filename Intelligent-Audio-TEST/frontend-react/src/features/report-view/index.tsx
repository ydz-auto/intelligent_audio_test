/**
 * /report/$reportId 报告查看（INT-434 重实施；15_报告域.md §3 真实层级重做）。
 * 壳：返回行（回退来源入口）+ 报告头 + 主列按 type 分发（task→任务级面板 / comparison→对比家族）
 * + 右导航 scrollspy + 底部操作条 + 导出/打印 + 弹窗群（导出/发布/重新生成/重命名）。
 */
import { useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useReportDetail } from '@/application/report-view/use-report-detail'
import { useReportAnalysis } from '@/application/report-view/use-report-analysis'
import { useReportActions } from '@/application/reports/use-report-actions'
import { ExportReportDialog } from '@/features/reports/components/modals/export-report-dialog'
import { PublishReportDialog, RegenerateReportDialog } from '@/features/reports/components/modals/report-confirm-dialogs'
import { ReportRenameDialog } from '@/features/reports/components/modals/report-rename-dialog'

import { ReportHeader } from './components/report-header'
import { ReportReadingNav, type ReadingNavSection } from './components/report-reading-nav'
import { TaskReportPanel } from './components/task-report-panel'
import { ComparisonReportPanel } from './components/comparison-report-panel'

import '@/features/report-view/report-print.css'

const NAV: Record<'task' | 'comparison', ReadingNavSection[]> = {
  task: [
    { id: 'report-overview', label: '总览' },
    { id: 'report-resource-stats', label: '设备与API' },
    { id: 'report-conclusion', label: '分析结论' },
    { id: 'report-comparison-tables', label: '对比表格' },
    { id: 'report-case-category', label: '用例分组' },
    { id: 'report-case-tag', label: '用例标签' },
    { id: 'report-specific-cases', label: '具体用例' },
  ],
  comparison: [
    { id: 'report-resource-stats', label: '设备与API' },
    { id: 'report-conclusion', label: '分析结论' },
    { id: 'report-case-category', label: '用例分组' },
    { id: 'report-case-tag', label: '用例标签' },
    { id: 'report-specific-cases', label: '具体用例' },
  ],
}

function DetailSkeleton() {
  return (
    <div className='mx-auto w-full max-w-[1200px] space-y-4 px-4 py-6 sm:px-6' aria-busy='true'>
      <Skeleton className='h-8 w-36' />
      <Skeleton className='h-28 w-full rounded-2xl' />
      <Skeleton className='h-40 w-full' />
      <Skeleton className='h-48 w-full' />
      <Skeleton className='h-48 w-full' />
    </div>
  )
}

export function ReportViewPage() {
  const { reportId: reportIdParam } = useParams({ strict: false })
  const search = useSearch({ strict: false }) as unknown as { from?: string }
  const reportId = Number(reportIdParam)
  const navigate = useNavigate()
  const { hasPermission } = usePermissions()
  const reportActions = useReportActions()
  const detailQuery = useReportDetail(reportId)
  const report = detailQuery.data

  const [editing, setEditing] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const [regenerateOpen, setRegenerateOpen] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [activeSection, setActiveSection] = useState('report-overview')
  const [progress, setProgress] = useState(0)
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({})

  // 回退来源入口（15_报告域.md §3.1：管理页进→/report-center，展示页进→/reports，无来源默认 /reports）
  const backTarget = useMemo(() => {
    if (search.from === 'management') return { to: '/report-center' as const }
    return { to: '/reports' as const }
  }, [search.from])
  const backLabel = search.from === 'management' ? '← 返回报告中心' : '← 返回报告展示'

  const { saveConclusion: saveAnalysis } = useReportAnalysis(reportId, report?.analysis)

  const sections = useMemo<ReadingNavSection[]>(() => {
    const isComparison = report?.type === 'comparison' || report?.type === 'secondary_comparison'
    const base = isComparison ? [...NAV.comparison] : [...NAV.task]
    if (isComparison && report?.type === 'secondary_comparison') {
      base.push({ id: 'report-compare-diff', label: '对比差异' })
    }
    return base
  }, [report?.type])

  // scrollspy + 阅读进度条
  useEffect(() => {
    if (!sections.length) return
    const handleScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight
      setProgress(max > 0 ? (window.scrollY / max) * 100 : 0)
      const offset = window.scrollY + 140
      let current = sections[0].id
      for (const section of sections) {
        const el = sectionRefs.current[section.id]
        if (el && el.getBoundingClientRect().top + window.scrollY <= offset) {
          current = section.id
        }
      }
      setActiveSection(current)
    }
    handleScroll()
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [sections])

  const handleNav = (id: string) => {
    const el = sectionRefs.current[id]
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const handleBack = () => void navigate(backTarget)

  if (detailQuery.isLoading) {
    return <DetailSkeleton />
  }

  // 空态/错误态（INT-503：isError 先于 !report 判定——加载失败不得落入骨架分支死区）
  if (
    detailQuery.isError ||
    !report ||
    !Number.isFinite(reportId) ||
    reportId <= 0
  ) {
    return (
      <Empty className='min-h-[420px]'>
        <EmptyHeader>
          <EmptyMedia variant='icon' />
          <EmptyTitle>报告不存在</EmptyTitle>
          <EmptyDescription>请提供有效的报告ID</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button variant='outline' size='sm' onClick={() => void navigate({ to: '/report-center' })}>
            返回报告中心
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  const isComparison = report.type === 'comparison' || report.type === 'secondary_comparison'

  return (
    <div className='report-view-container min-h-0 flex-1 overflow-auto print:mx-auto print:max-w-none'>
      <div className='mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6'>
        <ReportHeader
          report={report}
          hasPermission={hasPermission}
          editing={editing}
          backLabel={backLabel}
          onBack={handleBack}
          onEdit={() => setEditing((v) => !v)}
          onSave={() => setEditing(false)}
          onPublish={() => setPublishOpen(true)}
          onUnpublish={() => {
            void reportActions.unpublish(report.id, report.name)
          }}
          onExport={() => setExportOpen(true)}
          onRegenerate={() => setRegenerateOpen(true)}
          onCopyLink={() => {
            void navigator.clipboard?.writeText(`${window.location.origin}/report/${report.id}`)
            toast.success('链接已复制')
          }}
          onClose={handleBack}
        />

        <div className='mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px]'>
          <main className='min-w-0 space-y-6'>
            <div
              ref={(el) => {
                sectionRefs.current['report-overview'] = el
              }}
            >
              {isComparison ? (
                <ComparisonReportPanel
                  report={report}
                  isExporting={exportOpen}
                  editing={editing}
                  onStartEditing={() => setEditing(true)}
                  onExitEditing={() => setEditing(false)}
                  onSaveAnalysis={(content) => void saveAnalysis(content)}
                />
              ) : (
                <TaskReportPanel
                  report={report}
                  isExporting={exportOpen}
                  editing={editing}
                  onStartEditing={() => setEditing(true)}
                  onExitEditing={() => setEditing(false)}
                  onSaveAnalysis={(content) => void saveAnalysis(content)}
                />
              )}
            </div>
          </main>

          <aside className='print:hidden'>
            <ReportReadingNav
              sections={sections}
              activeId={activeSection}
              progress={progress}
              onNavigate={handleNav}
            />
          </aside>
        </div>

        {/* 底部操作条（sticky bottom） */}
        <div className='print:hidden sticky bottom-3 z-10 mt-8'>
          <div className='bg-background/95 supports-[backdrop-filter]:bg-background/60 flex flex-wrap items-center justify-end gap-2 rounded-xl border p-2 shadow-lg backdrop-blur-lg'>
            <Button variant='outline' size='sm' onClick={() => setExportOpen(true)}>
              导出
            </Button>
            <Button variant='ghost' size='sm' onClick={() => window.print()}>
              打印
            </Button>
            <Button variant='ghost' size='sm' onClick={handleBack}>
              关闭
            </Button>
          </div>
        </div>
      </div>

      <ExportReportDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        scope={report.name}
        count={1}
        onExport={(format) => toast.success(`报告已导出（${format.toUpperCase()}）`)}
      />
      <PublishReportDialog
        open={publishOpen}
        onOpenChange={setPublishOpen}
        report={report}
        onConfirm={(target) => {
          setPublishOpen(false)
          void reportActions.publish(target.id)
        }}
      />
      <RegenerateReportDialog
        open={regenerateOpen}
        onOpenChange={setRegenerateOpen}
        report={report}
        onConfirm={(target) => {
          setRegenerateOpen(false)
          void reportActions.regenerate(target.id)
        }}
      />
      <ReportRenameDialog
        open={renameOpen}
        onOpenChange={setRenameOpen}
        report={report}
        onConfirm={(target, payload) => void reportActions.rename(target.id, payload)}
      />
    </div>
  )
}
