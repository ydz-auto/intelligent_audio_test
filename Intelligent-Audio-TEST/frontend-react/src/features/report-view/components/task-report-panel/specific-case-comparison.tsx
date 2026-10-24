/**
 * 具体用例（15_报告域.md §3.3.7，SpecificCaseComparison 对位）。
 * 筛选卡（名称搜索/分组/标签/维度/排序）+ 已固定用例区 + 用例列表（INT-1046 全站统一：
 * 用例行照 11_用例域 §3.3 统一 `CaseCard` 口径呈现——名称 / CaseIdBadge / 算法徽章 / 标签，
 * 保留报告侧专属标记：状态指示点、分组 Badge、人工复核/AI复核 Badge、下载日志/固定/详情/展开）+ 展开详情
 * = TestCaseReportDetail 七块（§3.5）。
 * 用例卡片组织（INT-1125 修订）：具体用例列表改照用例管理页组织控件——分组视图/标签视图
 * + 平铺/交叉（复用 case-sub-view-toggle.tsx 同款 + specific-case-grouping.ts 聚合，默认分组视图+平铺）；
 * 排序下拉收敛为纯排序（移除「按分组/按标签」，组织由组织控件承担）；
 * 组头=组名+计数「{n} 个用例」，未分类/未设置标签兜底组末尾弱化；组织作用于当前页已加载用例集，
 * 跨页不合并；纯客户端聚合、不新增后端请求——用例行自带 category/tags（ReportCaseItem）。
 * 人工复核 + AI 复核交互（19 规范 §4/§5，INT-793/INT-1065）：卡片标记（复核 Badge → 复核明细抽屉）
 * + 明细操作（「人工复核」弹窗 / 「AI 复核」灵犀Agent 复核会话 / 「快速复核」一次性状态机）多路径；
 * 源任务 result_id 溯源（§4.2 路径 A）。
 */
import {
  ArrowDownWideNarrow,
  ArrowUpNarrowWide,
  ChevronDown,
  Download,
  Pin,
  PinOff,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { useReportCases } from '@/application/report-view/use-report-cases'
import { useReportReviews } from '@/application/report-view/useReportReviews'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useAlgorithmLabels } from '@/application/hooks/use-algorithm-options'
import type { ReportCaseItem, ReportDetailData, ReportLogFile } from '@/domain/models/report'
import type { CaseResultForReview } from '@/domain/models/review'
import { toAiReviewDimensionIds } from '@/domain/models/review'
import type { TagItem } from '@/domain/models/testTag'
import { cn } from '@/lib/utils'
import { fetchCaseResults } from '@/infrastructure/api/reviewApi'
import { AiReviewSessionDialog } from '@/features/ai-review/ai-review-session-dialog'
import { QuickAiReviewDialog } from '@/features/ai-review/quick-ai-review-dialog'
import { CaseCard } from '@/features/testcases/components/case-card'
import {
  CaseSubViewToggle,
  GROUP_SUB_VIEW_OPTIONS,
  TAG_SUB_VIEW_OPTIONS,
  type SubViewValue,
} from '@/features/testcases/components/case-sub-view-toggle'
import {
  groupReportCasesByCategory,
  groupReportCasesByTag,
  type ReportCaseSubGroup,
} from './specific-case-grouping'

import { CaseReportDetail } from '../case-report-detail'
import { getDeviceName } from '../case-report-detail/case-report-utils'
import { CaseDetailDialog } from '../modals/case-detail-dialog'
import { LogDownloadProgressDialog } from '../modals/log-download-progress-dialog'
import { LogFileSelectDialog } from '../modals/log-file-select-dialog'
import { ReviewBadge } from '../review/review-badge'
import { ManualReviewDialog } from '../review/manual-review-dialog'
import { ReviewHistoryDrawer } from '../review/review-history-drawer'
import { MultiSelectFilter, SelectedConditionsBar } from './multi-select-filter'

/** 日志下载进度视图态（§4.10b：进度 Dialog 受控数据，由真实下载流计算） */
interface LogDownloadViewState {
  /** 所选文件数（正在下载日志（{n} 个文件）） */
  fileCount: number
  /** 所选文件总大小（bytes；进度分母） */
  totalSize: number
  /** 已下载字节 */
  downloaded: number
  /** 下载速度（bytes/s，500ms 采样） */
  speed: number
  /** 是否完成 */
  done: boolean
}

/** 组织维度（INT-1125：分组视图/标签视图，照 18_挑选合并 §3.8.3 用例层组织语义） */
type OrgDimension = 'group' | 'tag'

export function SpecificCaseComparison({
  report,
  isExporting,
}: {
  report: ReportDetailData
  isExporting?: boolean
}) {
  const fallbackCases = report.summary.cases ?? []
  const {
    filters,
    setFilters,
    applyFilters,
    resetFilters,
    items,
    isLoading,
    isError,
    refetch,
    total,
    page,
    setPage,
    pages,
    pinnedIds,
    pinnedCases,
    togglePin,
    expandedIds,
    toggleExpand,
    downloadLogs,
  } = useReportCases(report.id, fallbackCases, isExporting)

  // 人工复核 + AI 复核（19 规范 §4：源任务 review_count / reviewed 标记 / 复核弹窗 / AI 结论）
  const reviews = useReportReviews(report)
  const { hasPermission } = usePermissions()
  // 人工复核提交（task.result.review）；AI 复核发起/对话/保存/驳回（task.result.ai_review，INT-800 已注册）
  const canReview = hasPermission('task.result.review')
  const canAiReview = hasPermission('task.result.ai_review')
  const isTaskReport = report.type === 'task' && Boolean(report.task_id)

  const [reviewCase, setReviewCase] = useState<ReportCaseItem>()
  const [aiCase, setAiCase] = useState<ReportCaseItem>()
  /** INT-1279 P2：AI 复核会话 dimension_ids（发起时源任务用例简报解析后快照，避免异步源竞态静默缺省 400） */
  const [aiDimensionIds, setAiDimensionIds] = useState<number[]>()
  const [quickTarget, setQuickTarget] = useState<{
    caseId: string
    caseName?: string
    results: CaseResultForReview[]
    evaluationStatus?: string | null
    /** INT-1279：用例评估维度 id（真实库结果无 LLM 判分维度时显式传 dimension_ids，避免发起 400） */
    dimensionIds?: number[]
  }>()
  const [historyCase, setHistoryCase] = useState<ReportCaseItem>()

  // 用例当前评估状态（任务侧用例简报 evaluation_status → AI 结论卡「原评估判定」）
  const caseEvaluationStatus = (caseId: string): string | null | undefined =>
    reviews.taskCases.find((c) => c.case_id === caseId)?.evaluation_status

  /** INT-1279：用例评估维度 id（源任务用例简报 evaluation_dimensions 溯源；AI 复核按用例评估维度显式传） */
  const caseDimensionIds = (caseId: string): number[] | undefined =>
    toAiReviewDimensionIds(
      reviews.taskCases.find((c) => c.case_id === caseId)?.evaluation_dimensions
    )

  /**
   * INT-1279 P2：报告具体用例入口 dimension_ids 源 = reviews.taskCases（['tasks','detail'] 异步加载）。
   * 用例卡先于源任务详情解析即可渲染 → 未就绪发起则 dimension_ids 静默缺省 → 真实库 400（code 203）。
   * 发起前等源任务详情查询解析（区分「加载中」与「真实为空」：仅 taskLoading 时 await，
   * 解析后仍无维度 = 用例 config 无评估维度，走后端缺省口径）。await 后须用结果.data 重算，
   * 规避闭包持有的旧 taskCases。
   */
  const resolveAiReviewDimensionIds = async (
    caseId: string
  ): Promise<number[] | undefined> => {
    if (reviews.taskLoading) {
      const result = await reviews.refetchTask()
      return toAiReviewDimensionIds(
        result.data?.cases.find((c) => c.case_id === caseId)?.evaluation_dimensions
      )
    }
    return caseDimensionIds(caseId)
  }

  /** AI 复核入口（§5.2 主形态）：取源任务该用例结果行校验有结果 → 打开灵犀Agent 复核会话（可追问） */
  const openAiReview = async (c: ReportCaseItem) => {
    if (!reviews.taskId) return
    try {
      const dimensionIds = await resolveAiReviewDimensionIds(c.id)
      const res = await fetchCaseResults(reviews.taskId, c.id)
      // 无执行结果的用例不开放 AI 复核（§5.2 可发起对象须有结果）
      if (res.results.length === 0) {
        toast.error('该用例无执行结果，无法复核')
        return
      }
      setAiCase(c)
      setAiDimensionIds(dimensionIds)
    } catch (err) {
      toast.error(
        err instanceof Error ? `用例结果加载失败：${err.message}` : '用例结果加载失败'
      )
    }
  }

  /** 快速复核入口（§5.1 次要形态）：一次性状态机弹窗（批量/低分初筛，不可追问） */
  const openQuickReview = async (c: ReportCaseItem) => {
    if (!reviews.taskId) return
    try {
      const dimensionIds = await resolveAiReviewDimensionIds(c.id)
      const res = await fetchCaseResults(reviews.taskId, c.id)
      if (res.results.length === 0) {
        toast.error('该用例无执行结果，无法复核')
        return
      }
      setQuickTarget({
        caseId: c.id,
        caseName: res.caseName || c.name,
        results: res.results,
        evaluationStatus: caseEvaluationStatus(c.id),
        dimensionIds,
      })
    } catch (err) {
      toast.error(
        err instanceof Error ? `用例结果加载失败：${err.message}` : '用例结果加载失败'
      )
    }
  }

  // 筛选卡可选项（分组/标签/评估维度；标签合并自用例 + summary 标签池）
  const availableGroups = useMemo(
    () => report.summary.case_categories.map((c) => c.category_name).filter(Boolean),
    [report.summary.case_categories]
  )
  const availableTags = useMemo(() => {
    const set = new Set<string>()
    for (const c of fallbackCases) for (const t of c.tags) set.add(t)
    for (const tag of [...(report.summary.all_tags ?? []), ...report.summary.all_case_tags]) {
      if (tag.tag_name) set.add(tag.tag_name)
    }
    return [...set]
  }, [fallbackCases, report.summary.all_tags, report.summary.all_case_tags])
  const availableMetrics = useMemo(
    () => report.summary.all_metrics.map((m) => m.name),
    [report.summary.all_metrics]
  )

  /** 报告侧标签登记表（all_case_tags/all_tags 含分类名；色值后端未下发，TagBadge 灰色兜底 + 分类角标） */
  const reportTagRegistry = useMemo<TagItem[]>(() => {
    const map = new Map<string, TagItem>()
    for (const tag of [
      ...(report.summary.all_case_tags ?? []),
      ...(report.summary.all_tags ?? []),
    ]) {
      if (!tag.tag_name) continue
      map.set(tag.tag_name, {
        id: tag.tag_id ? Number(tag.tag_id) : map.size + 1,
        name: tag.tag_name,
        description: null,
        color: null,
        categoryId: tag.category_id ? Number(tag.category_id) : null,
        categoryName: tag.category_name ?? null,
        createdAt: null,
        updatedAt: null,
      })
    }
    return [...map.values()]
  }, [report.summary.all_case_tags, report.summary.all_tags])

  /** 算法类型码 → 中文名（真实 /algorithm/options；用例卡算法徽章，INT-1687） */
  const algorithmLabels = useAlgorithmLabels()

  const [collapsed, setCollapsed] = useState(false)
  const [detailCase, setDetailCase] = useState<ReportCaseItem>()
  // INT-1067 两段流程：① 下载日志 → 文件选择 Dialog（§4.10a）→ ② 确认 → 打包下载 + 进度 Dialog（§4.10b）
  const [fileSelectCase, setFileSelectCase] = useState<ReportCaseItem>()
  const [downloadTarget, setDownloadTarget] = useState<ReportCaseItem>()
  const [downloadState, setDownloadState] = useState<LogDownloadViewState>()

  /** ① 点击「下载日志」：打开文件选择 Dialog（确认后进入下载） */
  const openLogFileSelect = (c: ReportCaseItem) => setFileSelectCase(c)

  /** ② 确认所选文件：?files= 打包下载 + 真实进度 Dialog；完成后触发浏览器下载 */
  const startLogDownload = async (files: ReportLogFile[]) => {
    const target = fileSelectCase
    if (!target) return
    setFileSelectCase(undefined)
    const totalSize = files.reduce((sum, f) => sum + (f.size || 0), 0)
    setDownloadTarget(target)
    setDownloadState({
      fileCount: files.length,
      totalSize,
      downloaded: 0,
      speed: 0,
      done: false,
    })
    try {
      const result = await downloadLogs(
        target.id,
        files.map((f) => f.name),
        (progress) => {
          setDownloadState((prev) =>
            prev
              ? {
                  ...prev,
                  downloaded: progress.loaded,
                  speed: progress.speed,
                }
              : prev
          )
        }
      )
      if (result.downloadUrl) {
        // INT-1116：OSS 可用时网关回 presigned JSON 信封，浏览器直连 OSS 预签名 URL
        // 下载（跨源导航，无 CORS 约束；rustfs 需暴露浏览器可达地址）。
        const a = document.createElement('a')
        a.href = result.downloadUrl
        a.download = `case_${target.id}_logs.zip`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
      } else {
        // 本地降级：zip 字节流 Blob → objectURL 下载（对照 use-report-actions triggerBlobDownload 先例）
        const url = URL.createObjectURL(result.blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `case_${target.id}_logs.zip`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
      }
      setDownloadState((prev) => (prev ? { ...prev, done: true } : prev))
    } catch (err) {
      setDownloadTarget(undefined)
      setDownloadState(undefined)
      toast.error(err instanceof Error ? err.message : '下载日志失败，请稍后重试')
    }
  }

  // INT-1125 组织控件状态（会话内存、不进 URL；默认 = 分组视图 + 平铺，不破坏现状默认）
  const [org, setOrg] = useState<OrgDimension>('group')
  const [subView, setSubView] = useState<SubViewValue>('flat')

  /** 组织层（INT-1125：分组视图=按分类聚合，标签视图=按标签聚合；作用于当前页已加载用例集，跨页不合并） */
  const orgGroups = useMemo<ReportCaseSubGroup[]>(() => {
    if (org === 'tag') return groupReportCasesByTag(items, reportTagRegistry)
    return groupReportCasesByCategory(items)
  }, [org, items, reportTagRegistry])

  /** 用例卡渲染（平铺 / 组内共用同一条 CaseCard 口径） */
  const renderCaseCard = (c: ReportCaseItem) => {
    const status = c.overall_status ?? overallStatusOf(c)
    const expanded = expandedIds.includes(c.id)
    const pinned = pinnedIds.includes(c.id)
    return (
      <CaseCard
        key={c.id}
        caseItem={c}
        selected={false}
        showCheckbox={false}
        tagRegistry={reportTagRegistry}
        algorithmLabels={algorithmLabels}
        leading={<StatusDot status={status} className='mt-1.5' />}
        titleExtra={
          <>
            <Badge variant='outline' className='text-xs'>
              {c.category ?? '未分类'}
            </Badge>
            {/* 卡片标记（§4.1：用例卡片头行「人工复核」Badge → 复核明细抽屉） */}
            {isTaskReport && reviews.reviewedCases[c.id] === true && (
              <button
                type='button'
                className='cursor-pointer'
                onClick={() => setHistoryCase(c)}
                aria-label='查看复核明细'
              >
                <ReviewBadge />
              </button>
            )}
          </>
        }
        hideMeta
        actions={
          <>
            {/* 明细操作（§4.2 双路径入口之二）：人工复核 / AI 复核（灵犀Agent 会话）+ 快速复核（§5.1 次要入口） */}
            {isTaskReport && canReview && (
              <Button
                variant='outline'
                size='sm'
                className='h-7 gap-1 px-2 text-xs'
                onClick={() => setReviewCase(c)}
              >
                <ShieldCheck aria-hidden='true' className='size-3.5' />
                人工复核
              </Button>
            )}
            {isTaskReport && canAiReview && (
              <>
                <Button
                  variant='ghost'
                  size='sm'
                  className='h-7 gap-1 px-2 text-xs'
                  onClick={() => void openAiReview(c)}
                >
                  <Sparkles aria-hidden='true' className='size-3.5' />
                  AI 复核
                </Button>
                <Button
                  variant='ghost'
                  size='sm'
                  className='text-muted-foreground/70 h-7 gap-1 px-2 text-xs'
                  onClick={() => void openQuickReview(c)}
                  title='快速复核（一次性状态机，无需追问的快速复检）'
                >
                  快速复核
                </Button>
              </>
            )}
            <Button
              variant='ghost'
              size='sm'
              className='h-7 gap-1 px-2 text-xs'
              onClick={() => openLogFileSelect(c)}
            >
              <Download aria-hidden='true' className='size-3.5' />
              下载日志
            </Button>
            <Button
              variant='ghost'
              size='sm'
              className='text-muted-foreground h-7 px-1.5'
              aria-pressed={pinned}
              aria-label={pinned ? '取消固定' : '固定'}
              title={pinned ? '取消固定' : '固定'}
              onClick={() => togglePin(c.id)}
            >
              <Pin aria-hidden='true' className={cn('size-3.5', pinned && 'text-primary fill-primary/20')} />
            </Button>
            <Button variant='ghost' size='sm' className='h-7 px-1.5' onClick={() => setDetailCase(c)}>
              详情
            </Button>
            <Button
              variant='ghost'
              size='sm'
              className='h-7 px-1.5'
              aria-label={expanded ? '收起详情' : '展开详情'}
              aria-expanded={expanded}
              onClick={() => toggleExpand(c.id)}
            >
              <ChevronDown
                aria-hidden='true'
                className={cn('size-4 transition-transform', expanded && 'rotate-180')}
              />
            </Button>
          </>
        }
        expandedContent={
          expanded ? (
            <div className='border-t p-3'>
              <CaseReportDetail caseItem={c} report={report} />
            </div>
          ) : undefined
        }
      />
    )
  }

  /** 组内组织（INT-1125）：平铺 或 交叉——分组视图内按标签、标签视图内按用例分组（组头复用 ReportGroupHeader 形态） */
  const renderOrgGroupBody = (cases: ReportCaseItem[]) => {
    if (subView === 'flat') {
      return <div className='space-y-2'>{cases.map(renderCaseCard)}</div>
    }
    const subgroups =
      org === 'group'
        ? groupReportCasesByTag(cases, reportTagRegistry)
        : groupReportCasesByCategory(cases)
    return (
      <div className='space-y-2'>
        {subgroups.map((sg) => (
          <div key={sg.key} className='space-y-2'>
            <ReportGroupHeader
              group={sg}
              muted={sg.key === '__untagged__' || sg.key === '__uncategorized__'}
            />
            <div className='space-y-2'>{sg.cases.map(renderCaseCard)}</div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <Collapsible open={!collapsed || isExporting} onOpenChange={setCollapsed} className='space-y-3'>
      <div className='flex items-center justify-between'>
        <CollapsibleTrigger
          render={<Button variant='ghost' size='sm' className='text-foreground -ml-2 h-8' />}
        >
          <span className='flex items-center gap-2 text-sm font-semibold'>
            具体用例对比
            <Badge variant='secondary' className='font-mono tabular-nums'>
              共 {total} 个用例
            </Badge>
          </span>
          <ChevronDown
            aria-hidden='true'
            className={cn('text-muted-foreground size-4 transition-transform', collapsed && 'rotate-180')}
          />
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent className='space-y-3'>
        {/* 筛选卡（§3.3.7：名称/分组多选/标签多选/评估维度多选/排序[按评估维度含资源+维度+升降序]） */}
        <div className='rounded-xl border p-3'>
          <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-3'>
            <div>
              <label className='text-muted-foreground mb-1 block text-xs'>用例名称</label>
              <Input
                value={filters.keyword ?? ''}
                onChange={(e) => setFilters({ ...filters, keyword: e.target.value })}
                placeholder='输入用例ID或名称关键词'
                className='h-8 text-xs'
              />
            </div>
            <div>
              <label className='text-muted-foreground mb-1 block text-xs'>排序方式</label>
              <div className='flex items-center gap-1.5'>
                <Select
                  value={filters.sortBy ?? 'name'}
                  onValueChange={(v) =>
                    setFilters({ ...filters, sortBy: v as typeof filters.sortBy })
                  }
                >
                  <SelectTrigger className='h-8 flex-1 text-xs'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='name'>按名称</SelectItem>
                    <SelectItem value='createdat'>按创建时间</SelectItem>
                    <SelectItem value='metric'>按评估维度</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  variant='outline'
                  size='sm'
                  className='h-8 px-2'
                  aria-label={filters.sortOrder === 'desc' ? '降序' : '升序'}
                  title={filters.sortOrder === 'desc' ? '降序' : '升序'}
                  onClick={() =>
                    setFilters({
                      ...filters,
                      sortOrder: filters.sortOrder === 'desc' ? 'asc' : 'desc',
                    })
                  }
                >
                  {filters.sortOrder === 'desc' ? (
                    <ArrowDownWideNarrow aria-hidden='true' className='size-3.5' />
                  ) : (
                    <ArrowUpNarrowWide aria-hidden='true' className='size-3.5' />
                  )}
                </Button>
              </div>
            </div>
            {filters.sortBy === 'metric' && (
              <div className='grid grid-cols-2 gap-1.5'>
                <div>
                  <label className='text-muted-foreground mb-1 block text-xs'>资源</label>
                  <Select
                    value={filters.sortResource ?? 'all'}
                    onValueChange={(v) =>
                      setFilters({ ...filters, sortResource: v === 'all' || v === null ? undefined : v })
                    }
                  >
                    <SelectTrigger className='h-8 text-xs'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value='all'>全部资源(平均)</SelectItem>
                      {report.summary.resources.map((r) => (
                        <SelectItem key={r} value={r}>{r}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className='text-muted-foreground mb-1 block text-xs'>评估维度</label>
                  <Select
                    value={filters.sortMetric ?? availableMetrics[0] ?? 'all'}
                    onValueChange={(v) =>
                      setFilters({ ...filters, sortMetric: v === 'all' || v === null ? undefined : v })
                    }
                  >
                    <SelectTrigger className='h-8 text-xs'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {availableMetrics.map((m) => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}
          </div>

          <div className='mt-2 space-y-1.5 border-t pt-2'>
            {/* 分组/标签/评估维度多选：搜索 + 分页（§3.3.7/3.3.8；原全铺 chip 无界） */}
            <MultiSelectFilter
              label='用例分组'
              options={availableGroups}
              selected={filters.categories ?? []}
              onToggle={(g) =>
                setFilters({
                  ...filters,
                  categories: (filters.categories ?? []).includes(g)
                    ? (filters.categories ?? []).filter((x) => x !== g)
                    : [...(filters.categories ?? []), g],
                })
              }
            />
            <MultiSelectFilter
              label='用例标签'
              options={availableTags}
              selected={filters.tags ?? []}
              onToggle={(t) =>
                setFilters({
                  ...filters,
                  tags: (filters.tags ?? []).includes(t)
                    ? (filters.tags ?? []).filter((x) => x !== t)
                    : [...(filters.tags ?? []), t],
                })
              }
            />
            <MultiSelectFilter
              label='评估维度'
              options={availableMetrics}
              selected={filters.metrics ?? []}
              onToggle={(m) =>
                setFilters({
                  ...filters,
                  metrics: (filters.metrics ?? []).includes(m)
                    ? (filters.metrics ?? []).filter((x) => x !== m)
                    : [...(filters.metrics ?? []), m],
                })
              }
            />
          </div>
          <SelectedConditionsBar
            conditions={[
              ...(filters.categories ?? []).map((g) => ({ key: `group:${g}`, label: `分组·${g}` })),
              ...(filters.tags ?? []).map((t) => ({ key: `tag:${t}`, label: `标签·${t}` })),
              ...(filters.metrics ?? []).map((m) => ({ key: `metric:${m}`, label: `维度·${m}` })),
            ]}
            onRemove={(key) => {
              const [kind, ...rest] = key.split(':')
              const value = rest.join(':')
              setFilters({
                ...filters,
                categories:
                  kind === 'group'
                    ? (filters.categories ?? []).filter((x) => x !== value)
                    : filters.categories,
                tags:
                  kind === 'tag'
                    ? (filters.tags ?? []).filter((x) => x !== value)
                    : filters.tags,
                metrics:
                  kind === 'metric'
                    ? (filters.metrics ?? []).filter((x) => x !== value)
                    : filters.metrics,
              })
            }}
          />

          <div className='mt-2 flex items-center justify-end gap-2 border-t pt-2'>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => {
                resetFilters()
                void refetch()
              }}
            >
              重置
            </Button>
            <Button
              size='sm'
              onClick={() => {
                applyFilters(filters)
                void refetch()
              }}
            >
              应用筛选
            </Button>
          </div>
        </div>

        {/* 已固定用例 */}
        {pinnedCases.length > 0 && (
          <div className='rounded-xl border p-3'>
            <p className='text-muted-foreground text-xs font-medium'>已固定用例</p>
            <div className='mt-2 flex flex-wrap gap-2'>
              {pinnedCases.map((c) => (
                <div key={c.id} className='bg-muted/40 flex flex-wrap items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs'>
                  <span className='font-medium'>{c.name}</span>
                  {/* 各资源状态徽标（§3.3.7：固定卡片行 = 名称 + 各资源状态徽标 + 取消固定） */}
                  {c.results.map((r) => (
                    <Badge key={r.resource} variant={resourceStatusVariant(r.status)} className='gap-1'>
                      <StatusDot status={resourceStatus(r.status)} />
                      <span className='flex items-center gap-1'>
                        {getDeviceName(r.resource, report.summary.resource_headers)}
                        {r.result_type && (
                          <span className='font-mono text-[10px] opacity-70'>{resultTypeLabel(r.result_type)}</span>
                        )}
                      </span>
                      {resourceStatusLabel(r.status)}
                    </Badge>
                  ))}
                  <Button
                    variant='ghost'
                    size='sm'
                    className='text-muted-foreground h-5 px-1'
                    aria-label='取消固定'
                    onClick={() => togglePin(c.id)}
                  >
                    <PinOff aria-hidden='true' className='size-3' />
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 用例列表 */}
        <div className='space-y-2'>
          {isLoading && items.length === 0 ? (
            <p className='text-muted-foreground p-4 text-center text-sm'>正在加载用例数据...</p>
          ) : isError && items.length === 0 ? (
            // §7 加载失败 + 请重试（同 reports-table/card-grid/showcase 错误态一致；refetch 可重拉）
            <div className='flex h-20 flex-col items-center justify-center gap-2 rounded-lg border text-xs'>
              <span className='text-muted-foreground'>加载失败</span>
              <Button
                variant='outline'
                size='sm'
                className='h-7 px-3 text-xs'
                onClick={() => void refetch()}
              >
                请重试
              </Button>
            </div>
          ) : items.length === 0 ? (
            <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
              暂无数据
            </div>
          ) : (
            /* INT-1125 组织控件：分组视图/标签视图 + 平铺/交叉（照用例管理交互，会话内存、不进 URL） */
            <div className='space-y-2'>
              <div className='flex flex-wrap items-center gap-2 px-1'>
                <Tabs
                  value={org}
                  onValueChange={(v) => {
                    setOrg(v as OrgDimension)
                    setSubView('flat')
                  }}
                  aria-label='用例组织方式'
                >
                  <TabsList className='h-7 gap-0.5 p-0.5'>
                    <TabsTrigger value='group' className='px-2 text-xs'>
                      分组视图
                    </TabsTrigger>
                    <TabsTrigger value='tag' className='px-2 text-xs'>
                      标签视图
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
                <CaseSubViewToggle
                  value={subView}
                  onValueChange={setSubView}
                  options={org === 'group' ? GROUP_SUB_VIEW_OPTIONS : TAG_SUB_VIEW_OPTIONS}
                />
              </div>
              {/* 组织层：组头 = 组名 + 计数「{n} 个用例」，未分类/未设置标签兜底组末尾弱化（§3.3.7） */}
              {orgGroups.map((g) => (
                <div key={g.key} className='space-y-2'>
                  <ReportGroupHeader
                    group={g}
                    muted={g.key === '__untagged__' || g.key === '__uncategorized__'}
                  />
                  {renderOrgGroupBody(g.cases)}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 分页 */}
        {pages > 1 && !isExporting && (
          <div className='flex items-center justify-between text-xs'>
            <span className='text-muted-foreground'>第 {page} / {pages} 页</span>
            <div className='flex items-center gap-1'>
              <Button variant='ghost' size='sm' className='h-7 px-2 text-xs' disabled={page <= 1} onClick={() => setPage(page - 1)}>
                上一页
              </Button>
              <Button variant='ghost' size='sm' className='h-7 px-2 text-xs' disabled={page >= pages} onClick={() => setPage(page + 1)}>
                下一页
              </Button>
            </div>
          </div>
        )}
      </CollapsibleContent>

      {/* INT-1067 两段流程：① 文件选择 Dialog（§4.10a）→ ② 下载进度 Dialog（§4.10b） */}
      <LogFileSelectDialog
        open={fileSelectCase !== undefined}
        onOpenChange={(open) => {
          if (!open) setFileSelectCase(undefined)
        }}
        reportId={report.id}
        caseItem={fileSelectCase}
        onConfirm={(files) => void startLogDownload(files)}
      />
      <LogDownloadProgressDialog
        open={downloadTarget !== undefined}
        onOpenChange={(open) => {
          if (!open) {
            setDownloadTarget(undefined)
            setDownloadState(undefined)
          }
        }}
        caseName={downloadTarget?.name ?? ''}
        fileCount={downloadState?.fileCount ?? 0}
        downloaded={downloadState?.downloaded ?? 0}
        totalSize={downloadState?.totalSize ?? 0}
        speed={downloadState?.speed ?? 0}
        done={downloadState?.done ?? false}
        onComplete={() => {
          setDownloadTarget(undefined)
          setDownloadState(undefined)
          toast.success('日志下载完成')
        }}
      />
      <CaseDetailDialog
        open={detailCase !== undefined}
        onOpenChange={(open) => {
          if (!open) setDetailCase(undefined)
        }}
        caseItem={detailCase}
        report={report}
      />

      {/* 人工复核 + AI 复核（19 规范 §4/§5：卡片标记 → 明细抽屉 / 明细操作 → 复核弹窗；源任务 result_id 溯源） */}
      {isTaskReport && reviews.taskId && (
        <>
          <ManualReviewDialog
            open={reviewCase !== undefined}
            onOpenChange={(open) => {
              if (!open) setReviewCase(undefined)
            }}
            taskId={reviews.taskId}
            caseItem={reviewCase}
            onSubmitted={() => void reviews.refetchTask()}
            onViewHistory={() => {
              setHistoryCase(reviewCase)
            }}
          />
          {/* §5.2 AI 复核主入口（灵犀Agent 复核会话，可追问；复核上下文由会话自身预填 §5.3） */}
          <AiReviewSessionDialog
            open={aiCase !== undefined}
            onOpenChange={(open) => {
              if (!open) {
                setAiCase(undefined)
                setAiDimensionIds(undefined)
              }
            }}
            taskId={reviews.taskId}
            caseId={aiCase?.id ?? ''}
            caseName={aiCase?.name}
            dimensionIds={aiDimensionIds}
          />
          {/* §5.1 快速复核次要入口（一次性状态机，批量/低分初筛场景） */}
          <QuickAiReviewDialog
            open={quickTarget !== undefined}
            onOpenChange={(open) => {
              if (!open) setQuickTarget(undefined)
            }}
            taskId={reviews.taskId}
            caseId={quickTarget?.caseId ?? ''}
            caseName={quickTarget?.caseName}
            results={quickTarget?.results ?? []}
            evaluationStatus={quickTarget?.evaluationStatus}
            dimensionIds={quickTarget?.dimensionIds}
          />
          <ReviewHistoryDrawer
            open={historyCase !== undefined}
            onOpenChange={(open) => {
              if (!open) setHistoryCase(undefined)
            }}
            taskId={reviews.taskId}
            caseId={historyCase?.id}
            title={historyCase?.name ?? '用例'}
          />
        </>
      )}
    </Collapsible>
  )
}

function overallStatusOf(c: ReportCaseItem): 'pass' | 'fail' | 'warning' | 'skip' | 'unknown' {
  const statuses = c.results.map((r) => r.status ?? '')
  if (statuses.some((s) => s === 'failed')) return 'fail'
  if (statuses.some((s) => s === 'skipped')) return 'skip'
  if (statuses.some((s) => s === 'warning')) return 'warning'
  return statuses.length > 0 ? 'pass' : 'unknown'
}

/** 资源执行状态 → 语义点（completed/通过、failed/失败、warning/警告、其余 neutral） */
function resourceStatus(status?: string): string {
  const s = status ?? ''
  if (s === 'completed') return 'pass'
  if (s === 'failed') return 'fail'
  if (s === 'warning') return 'warning'
  return 'unknown'
}

/** 资源执行状态中文（§3.3.4 STATUS_LABELS 同源） */
function resourceStatusLabel(status?: string): string {
  const map: Record<string, string> = {
    completed: '已完成',
    failed: '执行失败',
    warning: '警告',
    running: '执行中',
    pending: '排队中',
    skipped: '跳过',
  }
  return map[status ?? ''] ?? (status ?? '未知')
}

function resourceStatusVariant(status?: string): 'secondary' | 'destructive' | 'warning' | 'outline' {
  if (status === 'completed') return 'secondary'
  if (status === 'failed') return 'destructive'
  if (status === 'warning') return 'warning'
  return 'outline'
}

/** 结果类型中文（V9.7.10 result_type 后缀：realtime→实时/final→最终，缺省原样） */
function resultTypeLabel(resultType?: string) {
  const map: Record<string, string> = {
    realtime: '实时',
    final: '最终',
    recording: '录音',
    default: '默认',
  }
  return map[resultType ?? ''] ?? resultType ?? ''
}

function StatusDot({ status, className }: { status: string; className?: string }) {
  const color =
    status === 'pass' || status === 'completed'
      ? 'bg-success'
      : status === 'fail' || status === 'failed'
        ? 'bg-destructive'
        : status === 'warning'
          ? 'bg-warning'
          : status === 'skip'
            ? 'bg-muted'
            : 'bg-muted-foreground/40'
  return <span aria-hidden='true' className={cn('size-2 shrink-0 rounded-full', color, className)} />
}

/**
 * 报告用例分组头（§3.3.7 用例卡片组织 INT-1125：组头 = 组名 + 计数「{n} 个用例」；
 * 照 case-sub-group-header 形态——按标签子组带色点 + 分类角标，「未分类 / 未设置标签」兜底组末尾弱化）。
 */
function ReportGroupHeader({
  group,
  muted = false,
}: {
  group: ReportCaseSubGroup
  /** 未分类/未设置标签桶：弱化（末尾） */
  muted?: boolean
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-2 px-1 py-1.5',
        muted && 'bg-muted/40 rounded-md px-2'
      )}
    >
      {group.color && (
        <span
          aria-hidden='true'
          className='size-2 shrink-0 rounded-full'
          style={{ backgroundColor: group.color }}
        />
      )}
      <span className={cn('text-sm font-medium', muted && 'text-muted-foreground')}>
        {group.label}
      </span>
      {group.categoryName && (
        <span className='text-muted-foreground text-xs'>{group.categoryName}</span>
      )}
      <Badge
        variant='secondary'
        className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'
      >
        {group.cases.length} 个用例
      </Badge>
    </div>
  )
}
