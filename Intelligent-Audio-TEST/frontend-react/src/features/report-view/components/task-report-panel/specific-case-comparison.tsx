/**
 * 具体用例（15_报告域.md §3.3.7，SpecificCaseComparison 对位）。
 *
 * 基本结构：筛选卡（名称/分组/标签两级/评估维度三级/排序）+ 三视图工具栏 + 已固定用例区 + 用例列表 + 展开详情。
 * - **三视图（INT-1738）**：用例视图（组织层 → 用例卡 → 跨资源叶表）/ 设备视图（设备·API → 组织层 →
 *   用例卡 → 结果类型叶表）/ 结果类型视图（result_type → 组织层 → 用例卡 → 设备叶表）；
 *   「结果类型视图」档仅在当前结果集解析出非「默认」result_type 时渲染（现网全部两档）；
 *   切换视图保留筛选 / 固定 / 组织 / 排序，只重置展开态。
 * - **用例合并（INT-1738）**：`report_cases` 一行 = 用例 × 资源，用例视图按 `test_case_id` 合并，
 *   `results / metrics / algorithmResults / audios / logs` 按资源取并集（见 `report-case-view-model`）。
 * - **显示设置（§3.5.10）**：工具栏右端「显示设置」+ 非全选时「已隐藏 {n} 项」，区级一份状态，
 *   裁剪用例卡七块 + 叶表指标列 / 行集；当维由视图决定（口径 A）；导出态强制全显且不渲染入口。
 * - 组织控件（INT-1125）：分组视图/标签视图 + 平铺/交叉，三视图共用一份状态。
 * - 人工复核 + AI 复核交互（19 规范 §4/§5）与日志下载两段流程保持不变。
 */
import {
  ArrowDownWideNarrow,
  ArrowLeftRight,
  ArrowUpNarrowWide,
  ChevronDown,
  Download,
  Pin,
  PinOff,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Tag,
} from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
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
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import { useReportCases } from '@/application/report-view/use-report-cases'
import {
  caseResourceKeys,
  resultTypeText,
  type MergedReportCase,
  type ReportCaseView,
} from '@/application/report-view/report-case-view-model'
import { useReportCaseViews } from '@/application/report-view/use-report-case-views'
import { useCaseDisplaySettings } from '@/application/report-view/use-case-display-settings'
import { useReportFilterTaxonomy } from '@/application/report-view/use-report-filter-taxonomy'
import { useReportReviews } from '@/application/report-view/useReportReviews'
import { usePermissions } from '@/application/hooks/use-permissions'
import type { ReportCaseItem, ReportDetailData, ReportLogFile } from '@/domain/models/report'
import type { CaseResultForReview } from '@/domain/models/review'
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

import { getDeviceName, roundTagLabel } from '../case-report-detail/case-report-utils'
import { CaseDetailDialog } from '../modals/case-detail-dialog'
import { LogDownloadProgressDialog } from '../modals/log-download-progress-dialog'
import { LogFileSelectDialog } from '../modals/log-file-select-dialog'
import { ReviewBadge } from '../review/review-badge'
import { ManualReviewDialog } from '../review/manual-review-dialog'
import { ReviewHistoryDrawer } from '../review/review-history-drawer'
import { CaseDisplaySettings } from './case-display-settings'
import { FilterDimensionTree } from './filter-dimension-tree'
import { FilterTagTree } from './filter-tag-tree'
import { MultiSelectFilter, SelectedConditionsBar } from './multi-select-filter'
import { CaseReportExpanded } from './specific-case-views/case-report-expanded'

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

/** 节点内 / 视图内一次加载的用例数（「加载更多（剩余 {n}）」） */
const NODE_PAGE_SIZE = 20

/** 选项值兜底：真实库聚合行存在缺名项（all_metrics.name / tag_name 为空） */
function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

/** 三视图档位定义（结果类型视图按数据显隐） */
const VIEW_LABELS: Record<ReportCaseView, string> = {
  case: '用例视图',
  resource: '设备视图',
  resultType: '结果类型视图',
}

/** 叶表渲染上下文（按视图给行集锚点） */
interface LeafContext {
  view: ReportCaseView
  resourceKey?: string
  resultType?: string
}

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
    pinnedIds,
    pinnedCases,
    togglePin,
    expandedIds,
    toggleExpand,
    clearExpanded,
    downloadLogs,
  } = useReportCases(report.id, fallbackCases, isExporting)

  // 人工复核 + AI 复核（19 规范 §4：源任务 review_count / reviewed 标记 / 复核弹窗 / AI 结论）
  const reviews = useReportReviews(report)
  const { hasPermission } = usePermissions()
  const canReview = hasPermission('task.result.review')
  const canAiReview = hasPermission('task.result.ai_review')
  const isTaskReport = report.type === 'task' && Boolean(report.task_id)

  const [reviewCase, setReviewCase] = useState<ReportCaseItem>()
  const [aiCase, setAiCase] = useState<ReportCaseItem>()
  const [quickTarget, setQuickTarget] = useState<{
    caseId: string
    caseName?: string
    results: CaseResultForReview[]
    evaluationStatus?: string | null
  }>()
  const [historyCase, setHistoryCase] = useState<ReportCaseItem>()

  // 用例当前评估状态（任务侧用例简报 evaluation_status → AI 结论卡「原评估判定」）
  const caseEvaluationStatus = (caseId: string): string | null | undefined =>
    reviews.taskCases.find((c) => c.case_id === caseId)?.evaluation_status

  /** AI 复核入口（§5.2 主形态）：取源任务该用例结果行校验有结果 → 打开灵犀Agent 复核会话（可追问） */
  const openAiReview = async (c: ReportCaseItem) => {
    if (!reviews.taskId) return
    try {
      const res = await fetchCaseResults(reviews.taskId, c.id)
      // 无执行结果的用例不开放 AI 复核（§5.2 可发起对象须有结果）
      if (res.results.length === 0) {
        toast.error('该用例无执行结果，无法复核')
        return
      }
      setAiCase(c)
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
      })
    } catch (err) {
      toast.error(
        err instanceof Error ? `用例结果加载失败：${err.message}` : '用例结果加载失败'
      )
    }
  }

  const headers = report.summary.resource_headers ?? []

  /** 三视图聚合（按 test_case_id 合并 + 资源并集；纯计算） */
  const views = useReportCaseViews(items, headers)

  /** 显示设置（区级一份；导出态强制全显） */
  const display = useCaseDisplaySettings(report.id, isExporting)

  // 筛选卡可选项（分组/标签/评估维度；标签合并自用例 + summary 标签池）
  // 真实库存在字段残缺的聚合行（all_metrics 无 name 等）→ 只保留非空字符串，避免筛选树崩溃
  const availableGroups = useMemo(() => {
    const set = new Set<string>()
    for (const c of report.summary.case_categories) {
      if (isNonEmptyString(c.category_name)) set.add(c.category_name)
    }
    for (const c of [...fallbackCases, ...views.mergedCases]) {
      if (isNonEmptyString(c.category) && c.category !== '未分类') set.add(c.category)
    }
    return [...set]
  }, [report.summary.case_categories, fallbackCases, views.mergedCases])
  const availableTags = useMemo(() => {
    const set = new Set<string>()
    for (const c of [...fallbackCases, ...views.mergedCases]) {
      for (const t of c.tags ?? []) if (isNonEmptyString(t)) set.add(t)
    }
    for (const tag of [...(report.summary.all_tags ?? []), ...report.summary.all_case_tags]) {
      if (isNonEmptyString(tag.tag_name)) set.add(tag.tag_name)
    }
    return [...set]
  }, [fallbackCases, views.mergedCases, report.summary.all_tags, report.summary.all_case_tags])

  /** 分类归属（评估维度三级树 / 标签两级树；只影响展示，不改筛选请求） */
  const taxonomy = useReportFilterTaxonomy(
    views.baseDimensions,
    report.summary.all_metrics,
    [...(report.summary.all_case_tags ?? []), ...(report.summary.all_tags ?? [])],
    availableTags
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

  const [collapsed, setCollapsed] = useState(false)
  /** 显示设置 Popover 受控（叶表「未选择轮次」入口可从卡内打开，§3.3.7 兜底） */
  const [displaySettingsOpen, setDisplaySettingsOpen] = useState(false)
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
      const { blob } = await downloadLogs(
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
      // 触发浏览器下载（对照 use-report-actions triggerBlobDownload 先例）
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `case_${target.id}_logs.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
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

  // 三视图（默认「用例视图」= 现状；导出态强制用例视图，§3.5.10）
  const [view, setView] = useState<ReportCaseView>('case')
  const effectiveView: ReportCaseView = isExporting ? 'case' : view
  /** 设备 / 结果类型视图第 1 层节点展开态（默认只展开第一个；切视图重置） */
  const [openNodeKeys, setOpenNodeKeys] = useState<string[]>([])

  // 结果类型视图档位翻转 → 静默回落用例视图（保留筛选/固定/组织/排序，只重置展开态）
  useEffect(() => {
    if (view !== 'resultType') return
    if (isLoading || items.length === 0) return
    if (views.hasResultTypeView) return
    setView('case')
    clearExpanded()
  }, [view, views.hasResultTypeView, isLoading, items.length, clearExpanded])

  /** 第 1 层节点列表（按视图） */
  const layerNodes = useMemo(() => {
    if (effectiveView === 'resource') {
      return views.resourceNodes.map((node) => ({
        key: node.key,
        title: node.name,
        icon: node.kind === 'api' ? 'api' : 'device',
        version: node.version,
        taskPrefix: node.taskPrefix,
        mono: undefined as string | undefined,
        cases: node.cases as MergedReportCase[],
        leaf: { view: 'resource' as ReportCaseView, resourceKey: node.key },
      }))
    }
    if (effectiveView === 'resultType') {
      return views.resultTypeNodes.map((node) => ({
        key: node.key,
        title: node.label,
        icon: 'tag' as const,
        version: undefined,
        taskPrefix: undefined,
        mono: node.key,
        cases: node.cases,
        leaf: { view: 'resultType' as ReportCaseView, resultType: node.key },
      }))
    }
    return []
  }, [effectiveView, views.resourceNodes, views.resultTypeNodes])

  /** 节点 key 签名（切视图 / 换数据时重置展开态，避免同数量节点误判） */
  const nodeKeysSignature = useMemo(
    () => layerNodes.map((n) => n.key).join('|'),
    [layerNodes]
  )

  /** 节点默认展开（首个 / 展开全部 / 收起全部） */
  useEffect(() => {
    const keys = nodeKeysSignature ? nodeKeysSignature.split('|') : []
    setOpenNodeKeys(keys.length > 0 ? [keys[0]] : [])
    clearExpanded()
  }, [nodeKeysSignature, clearExpanded])

  /** 用例视图层内加载更多 */
  const [caseViewLimit, setCaseViewLimit] = useState(NODE_PAGE_SIZE)
  useEffect(() => {
    setCaseViewLimit(NODE_PAGE_SIZE)
  }, [effectiveView])

  // ---- 显示设置派生：叶表行集 / 轮次 chips / 维度（列集按每卡激活轮次在展开区容器内装配） ----
  const settings = display.settings
  const selectedBaseDimensions = views.baseDimensions.filter(
    (d) => !settings.hiddenMetrics.includes(d)
  )
  /**
   * 已选轮次 = 可用轮次集（叶表 Tab 候选 + 评分指标块 / 执行结果块轮次范围，§3.3.7 / §3.5.10）。
   * 报告里没有任何轮次 chip（单轮报告）时传 `undefined`——空数组只表示「用户把 chips 全清了」，
   * 两种语义不能混（否则单轮用例会误显示「未选择轮次」）。
   */
  const hasRoundChips = views.rounds.length > 0
  const selectedRounds = hasRoundChips
    ? views.rounds.filter((r) => !settings.hiddenRounds.includes(r))
    : undefined
  /** chips 被全清（显式标志，见上） */
  const roundsAllCleared = hasRoundChips && selectedRounds!.length === 0
  const selectedResources = views.resourceKeys.filter(
    (k) => !settings.hiddenResources.includes(k)
  )
  const selectedResultTypes = views.resultTypes.filter(
    (k) => !settings.hiddenResultTypes.includes(k)
  )

  /** 用例卡渲染（平铺 / 组内共用同一条 CaseCard 口径） */
  const renderCaseCard = (c: ReportCaseItem, leafCtx: LeafContext) => {
    const status = c.overall_status ?? overallStatusOf(c)
    const expanded = expandedIds.includes(c.id)
    const pinned = pinnedIds.includes(c.id)
    const resourceCount = caseResourceKeys(c).length
    return (
      <CaseCard
        key={`${leafCtx.view}:${leafCtx.resourceKey ?? leafCtx.resultType ?? ''}:${c.id}`}
        caseItem={c}
        selected={false}
        showCheckbox={false}
        tagRegistry={reportTagRegistry}
        leading={<StatusDot status={status} className='mt-1.5' />}
        titleExtra={
          <>
            <Badge variant='outline' className='text-xs'>
              {c.category ?? '未分类'}
            </Badge>
            {/* 用例视图卡头计数位：{n} 个设备·API（n > 1 才显示，§3.3.7） */}
            {leafCtx.view === 'case' && resourceCount > 1 && (
              <Badge variant='secondary' className='font-mono text-[11px] tabular-nums'>
                {resourceCount} 个设备·API
              </Badge>
            )}
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
            <CaseReportExpanded
              caseItem={c}
              view={leafCtx.view}
              resourceKey={leafCtx.resourceKey}
              resultType={leafCtx.resultType}
              report={report}
              display={isExporting ? undefined : settings}
              onRestoreDisplay={display.reset}
              selectedBaseDimensions={selectedBaseDimensions}
              includeSubDimensions={settings.includeSubDimensions}
              subDimensionNames={taxonomy.subDimensions}
              selectedRounds={selectedRounds}
              roundsAllCleared={roundsAllCleared}
              selectedResources={selectedResources}
              selectedResultTypes={selectedResultTypes}
              onOpenDisplaySettings={isExporting ? undefined : () => setDisplaySettingsOpen(true)}
            />
          ) : undefined
        }
      />
    )
  }

  /**
   * 组织层（INT-1125 / §3.3.7 组织层语义）：第 1 层 = 分组视图 / 标签视图，
   * 平铺 = 用例卡直接挂当层（不渲染子组头），交叉 = 组内再按另一维度分子组。
   */
  const renderOrgLayer = (cases: ReportCaseItem[], leafCtx: LeafContext) => {
    const groups =
      org === 'tag' ? groupReportCasesByTag(cases, reportTagRegistry) : groupReportCasesByCategory(cases)
    const body = (list: ReportCaseItem[]) => {
      if (subView === 'flat') {
        return <div className='space-y-2'>{list.map((c) => renderCaseCard(c, leafCtx))}</div>
      }
      const subgroups =
        org === 'group'
          ? groupReportCasesByTag(list, reportTagRegistry)
          : groupReportCasesByCategory(list)
      return (
        <div className='space-y-2'>
          {subgroups.map((sg) => (
            <div key={sg.key} className='space-y-2'>
              <ReportGroupHeader
                group={sg}
                muted={sg.key === '__untagged__' || sg.key === '__uncategorized__'}
              />
              <div className='space-y-2'>{sg.cases.map((c) => renderCaseCard(c, leafCtx))}</div>
            </div>
          ))}
        </div>
      )
    }
    return (
      <div className='space-y-2'>
        {groups.map((g) => (
          <div key={g.key} className='space-y-2'>
            <ReportGroupHeader
              group={g}
              muted={g.key === '__untagged__' || g.key === '__uncategorized__'}
            />
            {body(g.cases)}
          </div>
        ))}
      </div>
    )
  }

  const hasResultTypeView = views.hasResultTypeView && !isExporting
  const totalCases = effectiveView === 'case' ? total : views.caseCount

  return (
    <Collapsible open={!collapsed || isExporting} onOpenChange={setCollapsed} className='space-y-3'>
      <div className='flex items-center justify-between'>
        <CollapsibleTrigger
          render={<Button variant='ghost' size='sm' className='text-foreground -ml-2 h-8' />}
        >
          <span className='flex items-center gap-2 text-sm font-semibold'>
            具体用例对比
            {/* 计数口径按视图分（§3.3.7 定死）：用例视图 = 结果行数，设备/结果类型视图 = 去重用例数 */}
            {effectiveView === 'case' ? (
              <span title='按结果行计数：同一用例在多台设备上各计一行'>
                <Badge variant='secondary' className='font-mono tabular-nums'>
                  共 {totalCases} 条结果
                </Badge>
              </span>
            ) : (
              <Badge variant='secondary' className='font-mono tabular-nums'>
                共 {totalCases} 个用例
              </Badge>
            )}
          </span>
          <ChevronDown
            aria-hidden='true'
            className={cn('text-muted-foreground size-4 transition-transform', collapsed && 'rotate-180')}
          />
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent className='space-y-3'>
        {/* 筛选卡（§3.3.7：名称/分组多选/标签两级多选/评估维度三级多选/排序[按评估维度含资源+维度+升降序]） */}
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
                  {/* 同一三级口径：SelectGroup 分类组头 + 主维度 + 子维度缩进（§3.5.10 消费点） */}
                  <Select
                    value={filters.sortMetric ?? views.baseDimensions[0] ?? 'all'}
                    onValueChange={(v) =>
                      setFilters({ ...filters, sortMetric: v === 'all' || v === null ? undefined : v })
                    }
                  >
                    <SelectTrigger className='h-8 text-xs'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {taxonomy.dimensionSections.map((section) => (
                        <SelectGroup key={section.key}>
                          <SelectLabel>{section.name}</SelectLabel>
                          {section.groups.map((group) => (
                            <SelectGroup key={`${section.key}:${group.main}`}>
                              <SelectItem value={group.main}>{group.main}</SelectItem>
                              {group.subs.map((sub) => (
                                <SelectItem key={sub} value={sub}>
                                  <span className='ps-3'>{sub}</span>
                                </SelectItem>
                              ))}
                            </SelectGroup>
                          ))}
                        </SelectGroup>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}
          </div>

          <div className='mt-2 space-y-2 border-t pt-2'>
            {/* 分组多选：搜索 + 分页（§3.3.7；原全铺 chip 无界） */}
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
            {/* 标签筛选：分类 → 标签两级（负责人 2026-10-24 口径）；多选面板收起为按钮，避免整卡撑高 */}
            <div className='flex flex-wrap items-center gap-2'>
              <Popover>
                <PopoverTrigger
                  render={<Button variant='outline' size='sm' className='h-7 gap-1 px-2 text-xs' />}
                >
                  用例标签
                  {(filters.tags ?? []).length > 0 && (
                    <Badge variant='secondary' className='px-1 font-mono text-[10px]'>
                      {(filters.tags ?? []).length}
                    </Badge>
                  )}
                </PopoverTrigger>
                <PopoverContent align='start' className='w-[300px]'>
                  <FilterTagTree
                    sections={taxonomy.tagSections}
                    selected={filters.tags ?? []}
                    pageSize={8}
                    onToggle={(name, checked) =>
                      setFilters({
                        ...filters,
                        tags: checked
                          ? [...new Set([...(filters.tags ?? []), name])]
                          : (filters.tags ?? []).filter((x) => x !== name),
                      })
                    }
                  />
                </PopoverContent>
              </Popover>

              {/* 评估维度筛选：分类 → 主维度 → 子维度三级（同一 filter-dimension-tree） */}
              <Popover>
                <PopoverTrigger
                  render={<Button variant='outline' size='sm' className='h-7 gap-1 px-2 text-xs' />}
                >
                  评估维度
                  {(filters.metrics ?? []).length > 0 && (
                    <Badge variant='secondary' className='px-1 font-mono text-[10px]'>
                      {(filters.metrics ?? []).length}
                    </Badge>
                  )}
                </PopoverTrigger>
                <PopoverContent align='start' className='w-[340px]'>
                  <FilterDimensionTree
                    sections={taxonomy.dimensionSections}
                    selected={filters.metrics ?? []}
                    pageSize={8}
                    onToggle={(names, checked) =>
                      setFilters({
                        ...filters,
                        metrics: checked
                          ? [...new Set([...(filters.metrics ?? []), ...names])]
                          : (filters.metrics ?? []).filter((x) => !names.includes(x)),
                      })
                    }
                  />
                </PopoverContent>
              </Popover>
            </div>
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

        {/* 三视图工具栏（筛选卡之下、已固定用例之上）：左端视图 Tabs，右端组织控件 + 显示设置 */}
        <div className='flex flex-wrap items-center gap-2 px-1'>
          <Tabs
            value={effectiveView}
            onValueChange={(v) => {
              setView(v as ReportCaseView)
              clearExpanded()
            }}
            aria-label='用例视图切换'
          >
            <TabsList className='h-7 gap-0.5 p-0.5'>
              <TabsTrigger value='case' className='px-2 text-xs'>
                {VIEW_LABELS.case}
              </TabsTrigger>
              <TabsTrigger value='resource' className='px-2 text-xs'>
                {VIEW_LABELS.resource}
              </TabsTrigger>
              {hasResultTypeView && (
                <TabsTrigger value='resultType' className='px-2 text-xs'>
                  {VIEW_LABELS.resultType}
                </TabsTrigger>
              )}
            </TabsList>
          </Tabs>

          <div className='ms-auto flex flex-wrap items-center gap-2'>
            {/* 组织控件（三视图共用一份状态，切视图不重置） */}
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
            {/* 显示设置（导出态不渲染，§3.5.10） */}
            {!isExporting && (
              <CaseDisplaySettings
                view={effectiveView}
                settings={settings}
                onChange={display.update}
                onReset={display.reset}
                hiddenCount={display.hiddenCount}
                open={displaySettingsOpen}
                onOpenChange={setDisplaySettingsOpen}
                dimensionSections={taxonomy.dimensionSections}
                rounds={views.rounds.map((r) => ({ key: r, label: roundTagLabel(r) }))}
                resourceOptions={views.resourceNodes.map((n) => ({
                  key: n.key,
                  label: n.name,
                  kind: n.kind,
                }))}
                resultTypeOptions={views.resultTypeNodes.map((n) => ({
                  key: n.key,
                  label: n.label,
                }))}
              />
            )}
          </div>
        </div>

        {/* 已固定用例（跨视图共享，pinnedIds 按用例 ID） */}
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
                          <span className='font-mono text-[10px] opacity-70'>{resultTypeText(r.result_type)}</span>
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

        {/* 用例列表（按视图渲染） */}
        <div className='space-y-2'>
          {isLoading && items.length === 0 ? (
            <p className='text-muted-foreground p-4 text-center text-sm'>正在加载用例数据...</p>
          ) : isError && items.length === 0 ? (
            // §7 加载失败 + 请重试（refetch 可重拉）
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
          ) : views.mergedCases.length === 0 ? (
            <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
              暂无数据
            </div>
          ) : (
            <>
              {/* 聚合降级提示（>10000 条） */}
              {total > 10000 && (
                <p className='text-warning px-1 text-[11px]'>
                  当前筛选命中 {total} 条，聚合仅覆盖前 10000 条，请先缩小筛选条件
                </p>
              )}

              {effectiveView === 'case' ? (
                <div className='space-y-2'>
                  {renderOrgLayer(views.mergedCases.slice(0, caseViewLimit), { view: 'case' })}
                  {views.mergedCases.length > caseViewLimit && (
                    <div className='flex justify-center'>
                      <Button
                        variant='outline'
                        size='sm'
                        className='h-7 px-3 text-xs'
                        onClick={() => setCaseViewLimit((n) => n + NODE_PAGE_SIZE)}
                      >
                        加载更多（剩余 {views.mergedCases.length - caseViewLimit}）
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <div className='space-y-2'>
                  {/* 节点区概况：共 {d} 个设备 · {r} 个结果类型 · {m} 个用例 */}
                  <div className='flex flex-wrap items-center gap-2 px-1'>
                    <span className='text-muted-foreground text-xs'>
                      共 {views.resourceNodes.length} 个设备 · {views.resultTypeNodes.length} 个结果类型 ·{' '}
                      {views.caseCount} 个用例
                    </span>
                    <div className='ms-auto flex items-center gap-1'>
                      <Button
                        variant='ghost'
                        size='sm'
                        className='text-muted-foreground h-6 px-2 text-xs'
                        onClick={() => setOpenNodeKeys(layerNodes.map((n) => n.key))}
                      >
                        展开全部
                      </Button>
                      <Button
                        variant='ghost'
                        size='sm'
                        className='text-muted-foreground h-6 px-2 text-xs'
                        onClick={() => setOpenNodeKeys([])}
                      >
                        收起全部
                      </Button>
                    </div>
                  </div>
                  {layerNodes.length === 0 ? (
                    <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
                      暂无数据
                    </div>
                  ) : (
                    layerNodes.map((node) => {
                      const open = openNodeKeys.includes(node.key)
                      return (
                        <div key={node.key} className='rounded-xl border'>
                          <button
                            type='button'
                            className='flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left'
                            aria-expanded={open}
                            onClick={() =>
                              setOpenNodeKeys((prev) =>
                                prev.includes(node.key)
                                  ? prev.filter((k) => k !== node.key)
                                  : [...prev, node.key]
                              )
                            }
                          >
                            {node.icon === 'api' ? (
                              <ArrowLeftRight aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
                            ) : node.icon === 'tag' ? (
                              <Tag aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
                            ) : (
                              <Smartphone aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
                            )}
                            <span className={cn('text-sm font-medium', node.icon === 'device' ? '' : 'truncate')}>
                              {node.title}
                            </span>
                            {node.mono && (
                              <span className='text-muted-foreground font-mono text-[10px]'>{node.mono}</span>
                            )}
                            {node.version && (
                              <span className='text-muted-foreground font-mono text-[10px]'>{node.version}</span>
                            )}
                            {node.taskPrefix && (
                              <Badge variant='outline' className='font-mono text-[10px]'>
                                t{node.taskPrefix}
                              </Badge>
                            )}
                            <Badge variant='secondary' className='ms-auto font-mono text-[11px] tabular-nums'>
                              {node.cases.length} 个用例
                            </Badge>
                            <ChevronDown
                              aria-hidden='true'
                              className={cn('size-4 shrink-0 transition-transform', !open && '-rotate-90')}
                            />
                          </button>
                          {open && (
                            <div className='border-t p-2'>
                              <NodeCases
                                cases={node.cases}
                                leaf={node.leaf}
                                renderOrgLayer={(list) => renderOrgLayer(list, node.leaf)}
                              />
                            </div>
                          )}
                        </div>
                      )
                    })
                  )}
                </div>
              )}
            </>
          )}
        </div>
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

      {/* 人工复核 + AI 复核（19 规范 §4/§5） */}
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
          <AiReviewSessionDialog
            open={aiCase !== undefined}
            onOpenChange={(open) => {
              if (!open) setAiCase(undefined)
            }}
            taskId={reviews.taskId}
            caseId={aiCase?.id ?? ''}
            caseName={aiCase?.name}
          />
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

/** 节点内用例（「加载更多（剩余 {n}）」分页 + 组织层） */
function NodeCases({
  cases,
  leaf,
  renderOrgLayer,
}: {
  cases: MergedReportCase[]
  leaf: LeafContext
  renderOrgLayer: (cases: MergedReportCase[]) => ReactNode
}) {
  const [limit, setLimit] = useState(NODE_PAGE_SIZE)
  useEffect(() => {
    setLimit(NODE_PAGE_SIZE)
  }, [leaf.view, leaf.resourceKey, leaf.resultType])
  const shown = cases.slice(0, limit)
  return (
    <div className='space-y-2'>
      {renderOrgLayer(shown)}
      {cases.length > shown.length && (
        <div className='flex justify-center'>
          <Button
            variant='outline'
            size='sm'
            className='h-7 px-3 text-xs'
            onClick={() => setLimit((n) => n + NODE_PAGE_SIZE)}
          >
            加载更多（剩余 {cases.length - shown.length}）
          </Button>
        </div>
      )}
    </div>
  )
}

/** 用例整体状态（后端枚举未归一：completed/成功 同义，§10-11） */
function overallStatusOf(c: ReportCaseItem): 'pass' | 'fail' | 'warning' | 'skip' | 'unknown' {
  const statuses = c.results.map((r) => r.status ?? '')
  const has = (...values: string[]) => statuses.some((s) => values.includes(s))
  if (has('failed', '失败', '执行失败')) return 'fail'
  if (has('skipped', '跳过', '已跳过')) return 'skip'
  if (has('warning', '警告')) return 'warning'
  return statuses.length > 0 ? 'pass' : 'unknown'
}

/** 资源执行状态 → 语义点（completed/成功、failed/失败、warning/警告、其余 neutral） */
function resourceStatus(status?: string): string {
  const s = status ?? ''
  if (s === 'completed' || s === '成功' || s === 'success' || s === '已完成') return 'pass'
  if (s === 'failed' || s === '失败' || s === '执行失败') return 'fail'
  if (s === 'warning' || s === '警告') return 'warning'
  return 'unknown'
}

/** 资源执行状态中文（§3.3.4 STATUS_LABELS 同源；中英文枚举都归一为中文） */
function resourceStatusLabel(status?: string): string {
  const map: Record<string, string> = {
    completed: '成功',
    success: '成功',
    成功: '成功',
    已完成: '成功',
    failed: '失败',
    失败: '失败',
    执行失败: '失败',
    warning: '警告',
    警告: '警告',
    running: '执行中',
    'in-progress': '执行中',
    执行中: '执行中',
    pending: '排队中',
    排队中: '排队中',
    skipped: '已跳过',
    跳过: '已跳过',
    已跳过: '已跳过',
  }
  return map[status ?? ''] ?? (status ?? '未知')
}

function resourceStatusVariant(status?: string): 'secondary' | 'destructive' | 'warning' | 'outline' {
  const normalized = resourceStatus(status)
  if (normalized === 'pass') return 'secondary'
  if (normalized === 'fail') return 'destructive'
  if (normalized === 'warning') return 'warning'
  return 'outline'
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
