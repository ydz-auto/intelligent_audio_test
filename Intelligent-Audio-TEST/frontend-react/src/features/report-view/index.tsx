/**
 * /report/$reportId 报告查看（INT-434 落位；阅读优先版式，规范 §4）。
 * 返回行 + 报告头 + 主列分节（总览/设备与API/评估指标/分析结论/具体用例/对比差异）
 * + 右导航 scrollspy + 底部操作条 + 弹窗群（导出/发布/重新生成）。
 */
import { useNavigate, useParams } from '@tanstack/react-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useReportDetail } from '@/application/report-view/use-report-detail'
import { updateReport } from '@/infrastructure/api/reports-api'

import { ReportHeader } from './components/report-header'
import { ReportOverview } from './components/report-overview'
import { ReportResourceStats } from './components/report-resource-stats'
import { ReportCharts } from './components/report-charts'
import { ReportConclusion } from './components/report-conclusion'
import { ReportCaseList } from './components/report-case-list'
import { ReportComparisonSection } from './components/report-comparison-section'
import {
  ReportReadingNav,
  type ReadingNavSection,
} from './components/report-reading-nav'
import { ExportReportDialog } from '@/features/reports/components/modals/export-report-dialog'
import {
  PublishReportDialog,
  RegenerateReportDialog,
} from '@/features/reports/components/modals/report-confirm-dialogs'

import '@/features/report-view/report-print.css'

const SECTION_IDS = {
  overview: 'report-overview',
  resources: 'report-resource-stats',
  charts: 'report-charts',
  conclusion: 'report-conclusion',
  cases: 'report-cases',
  comparison: 'report-comparison',
} as const

function DetailSkeleton() {
  return (
    <div className='mx-auto w-full max-w-[1200px] space-y-4 px-4 py-6 sm:px-6' aria-busy='true'>
      <Skeleton className='h-8 w-36' />
      <Skeleton className='h-28 w-full rounded-2xl' />
      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className='h-24 w-full' />
        ))}
      </div>
      <Skeleton className='h-48 w-full' />
      <Skeleton className='h-48 w-full' />
    </div>
  )
}

export function ReportViewPage() {
  const { reportId: reportIdParam } = useParams({ strict: false })
  const reportId = Number(reportIdParam)
  const navigate = useNavigate()
  const { hasPermission } = usePermissions()
  const detailQuery = useReportDetail(reportId)
  const report = detailQuery.data

  const [editing, setEditing] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const [regenerateOpen, setRegenerateOpen] = useState(false)

  const [activeSection, setActiveSection] = useState<string>(SECTION_IDS.overview)
  const [progress, setProgress] = useState(0)
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({})

  const sections = useMemo<ReadingNavSection[]>(() => {
    const isComparison =
      report?.type === 'comparison' || report?.type === 'secondary_comparison'
    return [
      { id: SECTION_IDS.overview, label: '总览' },
      { id: SECTION_IDS.resources, label: '设备与API' },
      { id: SECTION_IDS.charts, label: '评估指标' },
      { id: SECTION_IDS.conclusion, label: '分析结论' },
      { id: SECTION_IDS.cases, label: '具体用例' },
      ...(isComparison ? [{ id: SECTION_IDS.comparison, label: '对比差异' }] : []),
    ]
  }, [report?.type])

  // scrollspy + 阅读进度条
  useEffect(() => {
    const handleScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight
      setProgress(max > 0 ? (window.scrollY / max) * 100 : 0)
      const offset = window.scrollY + 140
      let current: string = SECTION_IDS.overview
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

  const handleBack = () => void navigate({ to: '/reports' })

  if (detailQuery.isLoading || !report) {
    return <DetailSkeleton />
  }

  const isComparison =
    report.type === 'comparison' || report.type === 'secondary_comparison'

  return (
    <div className='report-view-container print:mx-auto print:max-w-none'>
      <div className='mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6'>
        <ReportHeader
          report={report}
          hasPermission={hasPermission}
          editing={editing}
          onBack={handleBack}
          onEdit={() => setEditing((v) => !v)}
          onPublish={() => setPublishOpen(true)}
          onExport={() => setExportOpen(true)}
          onRegenerate={() => setRegenerateOpen(true)}
          onCopyLink={() => toast.success('链接已复制')}
          onClose={handleBack}
        />

        <div className='mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px]'>
          <main className='min-w-0 space-y-8'>
            <section
              id={SECTION_IDS.overview}
              ref={(el) => {
                sectionRefs.current[SECTION_IDS.overview] = el
              }}
              className='scroll-mt-20'
            >
              <ReportOverview report={report} />
            </section>

            <section
              id={SECTION_IDS.resources}
              ref={(el) => {
                sectionRefs.current[SECTION_IDS.resources] = el
              }}
              className='scroll-mt-20'
            >
              <ReportResourceStats report={report} />
            </section>

            <section
              id={SECTION_IDS.charts}
              ref={(el) => {
                sectionRefs.current[SECTION_IDS.charts] = el
              }}
              className='scroll-mt-20'
            >
              <ReportCharts report={report} />
            </section>

            <section
              id={SECTION_IDS.conclusion}
              ref={(el) => {
                sectionRefs.current[SECTION_IDS.conclusion] = el
              }}
              className='scroll-mt-20'
            >
              <ReportConclusion
                report={report}
                editing={editing}
                onExitEditing={() => setEditing(false)}
                onSaveAnalysis={(analysis) => {
                  void updateReport(report.id, { analysis })
                }}
              />
            </section>

            <section
              id={SECTION_IDS.cases}
              ref={(el) => {
                sectionRefs.current[SECTION_IDS.cases] = el
              }}
              className='scroll-mt-20'
            >
              <ReportCaseList report={report} />
            </section>

            {isComparison && (
              <section
                id={SECTION_IDS.comparison}
                ref={(el) => {
                  sectionRefs.current[SECTION_IDS.comparison] = el
                }}
                className='scroll-mt-20 print:block'
              >
                <ReportComparisonSection report={report} />
              </section>
            )}
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
          void import('@/infrastructure/api/reports-api').then(({ publishReport }) =>
            publishReport(target.id)
          )
          toast.success('报告发布成功')
        }}
      />
      <RegenerateReportDialog
        open={regenerateOpen}
        onOpenChange={setRegenerateOpen}
        report={report}
        onConfirm={(target) => {
          setRegenerateOpen(false)
          void import('@/infrastructure/api/reports-api').then(({ regenerateReport }) =>
            regenerateReport(target.id)
          )
          toast.success('报告已重新生成')
        }}
      />
    </div>
  )
}
