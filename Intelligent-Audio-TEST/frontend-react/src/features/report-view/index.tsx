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
import { ApiError } from '@/infrastructure/api/api-error'
import { HttpStatus } from '@/domain/models/api'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useReportDetail } from '@/application/report-view/use-report-detail'
import { useReportReviews } from '@/application/report-view/useReportReviews'
import { useReportAnalysis } from '@/application/report-view/use-report-analysis'
import { useReportShare } from '@/application/report-view/use-report-share'
import { useReportActions } from '@/application/reports/use-report-actions'
import { waitForReportGenerated } from '@/application/reports/use-report-compare'
import { ExportReportDialog } from '@/features/reports/components/modals/export-report-dialog'
import { PublishReportDialog, RegenerateReportDialog } from '@/features/reports/components/modals/report-confirm-dialogs'
import { ReportRenameDialog } from '@/features/reports/components/modals/report-rename-dialog'
import { ReportProgressDialog } from '@/features/reports/components/modals/report-progress-dialog'
import { ReportShareDialog } from './components/modals/report-share-dialog'

import { ReportHeader } from './components/report-header'
import { ReportReadingNav, type ReadingNavSection } from './components/report-reading-nav'
import { TaskReportPanel } from './components/task-report-panel'
import { ComparisonReportPanel } from './components/comparison-report-panel'
import { BenchmarkRankingBlock } from './components/benchmark-ranking-block'

import '@/features/report-view/report-print.css'

const NAV: Record<'task' | 'comparison' | 'benchmark', ReadingNavSection[]> = {
  task: [
    { id: 'report-overview', label: '总览' },
    { id: 'report-resource-stats', label: '设备与API' },
    { id: 'report-conclusion', label: '分析结论' },
    { id: 'report-comparison-tables', label: '对比表格' },
    { id: 'report-case-category', label: '用例分组' },
    { id: 'report-case-tag', label: '用例标签' },
    { id: 'report-specific-cases', label: '具体用例' },
  ],
  benchmark: [
    { id: 'report-benchmark-ranking', label: 'Benchmark 排行' },
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

/**
 * 报告不存在的错误判定（INT-934）：后端 GET /reports/{id} 对不存在报告返回
 * HTTP 400 + envelope {code:404, message:"report not found"}（report_service
 * interfaces/api/routes.py:208）——envelope code 404 即业务 not-found，配 httpStatus
 * 404 兜底；非标准码时按 message 语义兜底（英文 not found / 旧中文「不存在」「未找到」）。
 */
function isReportNotFoundError(error: unknown): boolean {
  if (error instanceof ApiError) {
    // 后端 GET /reports/{id} 对不存在报告返回 HTTP 400 + envelope {code:404}——404 是 HTTP
    // 语义码，不在 ApiErrorCode 枚举内，按裸数值比对 HttpStatus.NOT_FOUND；httpStatus=404 兜底。
    const code = error.code as number | null
    if (code === HttpStatus.NOT_FOUND || error.httpStatus === HttpStatus.NOT_FOUND) return true
    return /不存在|未找到|not found/i.test(error.serverMessage ?? '')
  }
  if (typeof error !== 'object' || error === null) return false
  const message = (error as { message?: unknown }).message
  return typeof message === 'string' && message.includes('不存在')
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
  // 报告源任务复核数据（§4.1 统计徽章；仅任务型报告，源任务 review_count 驱动）
  const reportReviews = useReportReviews(report)

  const [editing, setEditing] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const [regenerateOpen, setRegenerateOpen] = useState(false)
  const [regenerateProgressOpen, setRegenerateProgressOpen] = useState(false)
  /** 重新生成进度弹窗按源任务订阅 report_generated（regenerate 异步删旧建新，旧报告 id 不可作进度键） */
  const [regenerateProgressTaskId, setRegenerateProgressTaskId] = useState<number | undefined>(undefined)
  /** 重新生成 SSE 等待（提交前已订阅，POST 成功后开进度弹窗直接 await；避免 taskId 补订阅的快速失败事件竞态） */
  const [regenerateWait, setRegenerateWait] = useState<
    { promise: Promise<number>; abort: () => void } | undefined
  >(undefined)
  const [renameOpen, setRenameOpen] = useState(false)
  const [activeSection, setActiveSection] = useState('report-overview')
  const [progress, setProgress] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  // 回退来源入口（15_报告域.md §3.1：管理页进→/report-center，展示页进→/reports，无来源默认 /reports）
  const backTarget = useMemo(() => {
    if (search.from === 'management') return { to: '/report-center' as const }
    return { to: '/reports' as const }
  }, [search.from])
  const backLabel = '返回'

  const { saveConclusion: saveAnalysis } = useReportAnalysis(reportId, report?.analysis)
  const share = useReportShare(reportId, report?.name ?? '报告')

  const sections = useMemo<ReadingNavSection[]>(() => {
    const isComparison = report?.type === 'comparison' || report?.type === 'secondary_comparison'
    const base =
      isComparison ? [...NAV.comparison]
      : report?.type === 'benchmark' ? [...NAV.benchmark]
      : [...NAV.task]
    if (isComparison && report?.type === 'secondary_comparison') {
      base.push({ id: 'report-compare-diff', label: '对比差异' })
    }
    return base
  }, [report?.type])

  // scrollspy + 阅读进度条（P2-1：容器内滚动，scroll 事件与坐标系绑定 report-view-container；
  // SidebarInset overflow-hidden 下 window 永不起滚，进度/激活分节全部用容器坐标系判。
  // 锚点元素从容器内按 <section id='report-*'> 收集——面板不逐段透传 ref，逐条 querySelector 即可）
  useEffect(() => {
    if (!sections.length) return
    const container = containerRef.current
    if (!container) return
    const anchors = new Map<string, HTMLElement>()
    for (const section of sections) {
      const el = container.querySelector<HTMLElement>(`#${section.id}`)
      if (el) anchors.set(section.id, el)
    }
    const handleScroll = () => {
      const max = container.scrollHeight - container.clientHeight
      setProgress(max > 0 ? (container.scrollTop / max) * 100 : 0)
      const offset = container.scrollTop + 140
      let current = sections[0].id
      for (const section of sections) {
        const el = anchors.get(section.id)
        if (el) {
          // 元素在滚动内容中的绝对偏移 = 容器视口内偏移 + 已滚距离
          const elTop =
            el.getBoundingClientRect().top -
            container.getBoundingClientRect().top +
            container.scrollTop
          if (elTop <= offset) current = section.id
        }
      }
      setActiveSection(current)
    }
    handleScroll()
    container.addEventListener('scroll', handleScroll, { passive: true })
    return () => container.removeEventListener('scroll', handleScroll)
  }, [sections])

  const handleNav = (id: string) => {
    const el = containerRef.current?.querySelector<HTMLElement>(`#${id}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const handleBack = () => void navigate(backTarget)

  // 空态/错误态（INT-503：isError 先于 !report 判定——加载失败不得落入骨架分支死区；
  // INT-596 P2-4：404/无效 ID →「报告不存在」，网络/500 →「加载失败 + 请重试」分叉，不合并误导）
  const isInvalidId = !Number.isFinite(reportId) || reportId <= 0
  const notFoundError = detailQuery.isError && isReportNotFoundError(detailQuery.error)

  if (detailQuery.isLoading) {
    return <DetailSkeleton />
  }

  if (detailQuery.isError && !notFoundError) {
    return (
      <Empty className='min-h-[420px]'>
        <EmptyHeader>
          <EmptyMedia variant='icon' />
          <EmptyTitle>加载失败</EmptyTitle>
          <EmptyDescription>报告数据加载失败，请重试</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button variant='secondary' size='sm' onClick={() => void detailQuery.refetch()}>
            请重试
          </Button>
          <Button variant='outline' size='sm' onClick={() => void navigate({ to: '/report-center' })}>
            返回报告中心
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  if (isInvalidId || notFoundError || !report) {
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
    <div
      ref={containerRef}
      className='report-view-container min-h-0 flex-1 overflow-auto print:mx-auto print:max-w-none'
    >
      <div className='mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6'>
        <ReportHeader
          report={report}
          hasPermission={hasPermission}
          editing={editing}
          backLabel={backLabel}
          onBack={handleBack}
          onEdit={() => setEditing((v) => !v)}
          onSave={() => setEditing(false)}
          onRename={() => setRenameOpen(true)}
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
          onShare={() => share.openShare('link')}
          onClose={handleBack}
          reviewCount={reportReviews.reviewCount}
          onReviewStatsClick={() =>
            containerRef.current
              ?.querySelector<HTMLElement>('#report-specific-cases')
              ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          }
        />

        <div className='mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_220px]'>
          <main className='min-w-0 space-y-6'>
            {report.type === 'benchmark' && (
              <BenchmarkRankingBlock reportId={report.id} reportName={report.name} />
            )}
            {isComparison ? (
              <ComparisonReportPanel
                report={report}
                isExporting={exportOpen}
                editing={editing}
                canEdit={hasPermission('report:update')}
                onStartEditing={() => setEditing(true)}
                onExitEditing={() => setEditing(false)}
                onSaveAnalysis={(content) => void saveAnalysis(content)}
              />
            ) : (
              <TaskReportPanel
                report={report}
                isExporting={exportOpen}
                editing={editing}
                canEdit={hasPermission('report:update')}
                onStartEditing={() => setEditing(true)}
                onExitEditing={() => setEditing(false)}
                onSaveAnalysis={(content) => void saveAnalysis(content)}
              />
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

        {/* 底部操作条（sticky bottom；15_报告域.md §3.1：保存 report:update / 发布 report:publish / 导出 / 打印 / 关闭） */}
        <div className='print:hidden sticky bottom-3 z-10 mt-8'>
          <div className='bg-background/95 supports-[backdrop-filter]:bg-background/60 flex flex-wrap items-center justify-end gap-2 rounded-xl border p-2 shadow-lg backdrop-blur-lg'>
            {editing && hasPermission('report:update') && (
              <Button variant='secondary' size='sm' onClick={() => setEditing(false)}>
                保存
              </Button>
            )}
            {hasPermission('report:publish') && report.status === 'draft' && (
              <Button variant='secondary' size='sm' onClick={() => setPublishOpen(true)}>
                发布
              </Button>
            )}
            {hasPermission('report:publish') && report.status === 'published' && (
              <Button variant='outline' size='sm' onClick={() => void reportActions.unpublish(report.id, report.name)}>
                取消发布
              </Button>
            )}
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
        onExport={(format) => void reportActions.exportReport([report.id], format)}
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
          const taskId = target.task_id
          if (typeof taskId === 'number' && taskId > 0) {
            // INT-935 返工 P2：regenerate 异步快速失败事件竞态——task_id 来自报告详情，提交前已知，
            // 先订阅 report_generated、等 SSE open 再 POST（对齐二次对比 onOpen-gate），事件必达
            const controller = new AbortController()
            let sseOpened: (() => void) | undefined
            const sseReady = new Promise<void>((resolve) => {
              sseOpened = resolve
            })
            const waitPromise = waitForReportGenerated(
              { taskId },
              { signal: controller.signal, onOpen: () => sseOpened?.() },
            )
            // 交接前先挂 no-op catch，避免取消/超时在进度弹窗接管前成为 unhandled rejection
            void waitPromise.catch(() => undefined)
            void (async () => {
              try {
                // 等 SSE 连接建立（≤2s 兜底）再提交，杜绝 <1s 快速失败事件早于订阅到达的竞态
                await Promise.race([sseReady, new Promise((r) => setTimeout(r, 2_000))])
                await reportActions.regenerate(target.id)
                // POST 成功 → 开进度弹窗 await 预订阅 waitPromise 取新报告 id
                setRegenerateWait({ promise: waitPromise, abort: () => controller.abort() })
                setRegenerateProgressTaskId(undefined)
                setRegenerateProgressOpen(true)
              } catch (err) {
                controller.abort()
                toast.error(err instanceof Error ? err.message : '重新生成报告提交失败')
              }
            })()
          } else {
            // 无 task_id 兜底（理论上任务型报告必有；防类型漏）：按旧路径直接开弹窗
            setRegenerateWait(undefined)
            setRegenerateProgressOpen(true)
            void reportActions.regenerate(target.id)
          }
        }}
      />
      <ReportProgressDialog
        open={regenerateProgressOpen}
        onOpenChange={setRegenerateProgressOpen}
        taskId={regenerateProgressTaskId}
        waitPromise={regenerateWait?.promise}
        onWaitAbort={regenerateWait?.abort}
        onComplete={(newReportId) => {
          setRegenerateProgressOpen(false)
          void navigate({
            to: '/report/$reportId',
            params: { reportId: String(newReportId) },
            search: { from: search.from as 'showcase' | 'management' | undefined },
          })
        }}
      />
      <ReportRenameDialog
        open={renameOpen}
        onOpenChange={setRenameOpen}
        report={report}
        onConfirm={(target, payload) => void reportActions.rename(target.id, payload)}
      />
      <ReportShareDialog
        reportName={report.name}
        state={share.shareState}
        onOpenChange={(open) => {
          if (open) share.openShare()
          else share.closeShare()
        }}
        onMethodChange={(method) => share.patchShare({ method })}
        onAccessChange={(access) => share.patchShare({ access })}
        onExpiryChange={(expiry) => share.patchShare({ expiry })}
        onPasswordChange={(password) => share.patchShare({ password })}
        onRecipientsChange={(recipients) => share.patchShare({ recipients })}
        onExpiresAtChange={(expiresAt) => share.patchShare({ expiresAt })}
        onGenerate={() => void share.generateShareLink()}
        onRevoke={share.revokeShare}
        onCopy={() => {
          if (share.shareState.shareUrl) {
            void navigator.clipboard?.writeText(share.shareState.shareUrl)
            toast.success('链接已复制')
          }
        }}
        onRefreshStats={share.refreshStats}
      />
    </div>
  )
}
