/**
 * 关联用例 / 关联资源（09_任务域.md §4.4，Card 内 Tabs）。
 * 页签「关联用例」（默认）/「关联资源」（INT-1241 起中性文案，不再按任务类型定「关联API/关联设备」）；
 * 工具行 = 搜索 + 视图切换（平铺/标签/分组）+ 状态筛选。
 * 平铺态 DataTable 列：用例名称/执行状态/评估状态/耗时/轮次/操作（移除用例）。
 * INT-1492 对照 V9.7.10 基线修正三处：
 * ① 平铺由 CaseCard 三列网格改为紧凑行式列表（名称/执行状态/评估状态/耗时/轮次/操作一行，
 *   行高 54px 对齐基线 caseItemHeight）；标签/分组态组内同样用该行（不再卡片网格）。
 * ② 用例区 max-h-[400px] + 虚拟滚动（scrollTop 切片 + overscan）替代全量渲染（任务 526 有 1737 条，
 *   旧实现 scrollHeight 达 136,697px），并补搜索（按名称或用例 ID，基线 caseSearchQuery 口径）。
 * ③ 状态筛选补「执行失败」「评估失败」两项（基线 execution_failed / evaluation_failed 口径：
 *   执行失败 = execution_status=failed；评估失败 = evaluation_status=failed 且执行未失败），
 *   执行/评估两列徽章分别显示「执行失败」「评估失败」，不再合并成「已失败」。
 * （轮次列：分母取 TaskCaseBrief.rounds_count（用例 config.rounds 长度），
 *   未执行（无耗时）显示「—」且进度条为空，执行后显示第 N/N 轮）
 * 19_人工审核与AI复核交互设计.md §3 落位（INT-795）：
 * - 已复核用例行执行/评估徽章旁叠加「人工复核」Badge（TaskCaseBrief.reviewed 驱动）；
 * - 行尾「人工复核」钮（终态任务 + task.result.review）→ §3.2 单条复核弹窗（取该用例结果行）；
 * - 行尾「AI 复核」钮（evaluation:execute）→ AI 复核状态机弹窗（§2.1/§5.2）；
 * - 勾选多行 → 底部「批量复核」浮条（§3.3，同一改判字段应用到全部勾选结果）；
 * - 工具行「查看复核历史」link + 头行「已复核 {n} 条」计数（TaskDetailData.review_count 驱动）→ §3.4 抽屉。
 * 标签/分组态用 Collapsible 组头（名称 + 计数）行。
 * INT-949：行尾「移除用例」先弹 ConfirmDialog（§5.9 按任务阶段两段后果文案），
 * 末例追加二次确认（「移除并停止任务」/「仅移除用例」）；取消不发请求。
 */
import { ClipboardCheck, History, Search, Sparkles, Trash2, Zap } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTaskActions } from '@/application/tasks/use-task-actions'
import {
  useReviewRecordScope,
  useScopedReviewHistory,
} from '@/application/tasks/useReview'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { CaseResultForReview } from '@/domain/models/review'
import {
  caseEvaluationStatusLabel,
  caseEvaluationStatusTone,
  toAiReviewDimensionIds,
} from '@/domain/models/review'
import type { TaskCaseBrief, TaskCaseTarget, TaskDetailData } from '@/domain/models/task'
import { fetchCaseResults } from '@/infrastructure/api/reviewApi'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { Progress } from '@/features/tasks/components/ui/progress'
import { formatCaseDuration } from '@/features/testcases/constants'
import { AiReviewSessionDialog } from '@/features/ai-review/ai-review-session-dialog'
import { QuickAiReviewDialog } from '@/features/ai-review/quick-ai-review-dialog'
import { ManualReviewBatchBar } from '@/features/tasks/components/manual-review-batch-bar'
import { ManualReviewDialog } from '@/features/tasks/components/manual-review-dialog'
import { ReviewBadge } from '@/features/tasks/components/review-badge'
import {
  buildCaseNameMap,
  ReviewHistoryDrawer,
} from '@/features/tasks/components/review-history-drawer'
import {
  getCaseRemovePhase,
  TaskConfirmDialog,
  type CaseRemovePhase,
} from '@/features/tasks/components/task-confirm-dialogs'

type ViewMode = 'flat' | 'tag' | 'group'
const VIEW_OPTIONS: Array<{ value: ViewMode; label: string }> = [
  { value: 'flat', label: '平铺' },
  { value: 'tag', label: '标签' },
  { value: 'group', label: '分组' },
]

/**
 * 选项 value 为英文枚举（对齐 case.execution_status / evaluation_status 实测值）。
 * INT-1492：补 execution_failed / evaluation_failed 两个独立项（V9.7.10 TestExecutionComponent.vue:204-205 基线），
 * 与「已失败」（任务级合并态 status=failed）并存——任务 526 摘要「评估失败 1737 条」可直接筛出。
 */
const CASE_STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'all', label: '全部状态' },
  { value: 'pending', label: '等待中' },
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '执行中' },
  { value: 'evaluating', label: '计算指标中' },
  { value: 'completed', label: '已完成' },
  { value: 'execution_failed', label: '执行失败' },
  { value: 'evaluation_failed', label: '评估失败' },
  { value: 'failed', label: '已失败' },
  { value: 'skipped', label: '已跳过' },
  { value: 'stopped', label: '已停止' },
  { value: 'deleted', label: '已删除' },
]

/** 行高（V9.7.10 caseItemHeight=54，虚拟滚动切片基准） */
const CASE_ROW_HEIGHT = 54
/** 用例区可视高度（09_任务域 §4.4 平铺 max-h-[400px]） */
const CASE_LIST_MAX_HEIGHT = 400
/** 虚拟滚动缓冲行数（上下各 5 行，基线 visibleCases 同口径） */
const CASE_ROW_OVERSCAN = 5

/**
 * 状态筛选（V9.7.10 filteredAssociatedCases 口径）：
 * 执行失败 = execution_status=failed（不论评估态）；评估失败 = evaluation_status=failed 且执行未失败
 * （两类互斥）；其余按任务级/执行/评估任一命中（保留 React 侧既有 OR 口径）。
 */
function matchesStatusFilter(c: TaskCaseBrief, status: string): boolean {
  if (status === 'all') return true
  if (status === 'execution_failed') return c.execution_status === 'failed'
  if (status === 'evaluation_failed')
    return c.evaluation_status === 'failed' && c.execution_status !== 'failed'
  return c.status === status || c.execution_status === status || c.evaluation_status === status
}

/**
 * 执行/评估两列共用的状态徽章（INT-1492：failed 按列区分为「执行失败」「评估失败」）。
 * 评估列按「执行是否已开始」纠偏：未执行（pending/queued）时不显示评估中，
 * 统一落「待评估」（后端多目标聚合可能因个别行评估中把整例标成 running）。
 */
function CaseStatusBadge({
  status,
  kind,
  executionStatus,
}: {
  status: string | null
  /** execution=执行状态列 / evaluation=评估状态列 */
  kind: 'execution' | 'evaluation'
  /** 评估列纠偏所需的用例级执行状态 */
  executionStatus?: string | null
}) {
  if (kind === 'evaluation') {
    return (
      <StatusBadge
        label={caseEvaluationStatusLabel(executionStatus, status)}
        variant={caseEvaluationStatusTone(executionStatus, status)}
      />
    )
  }
  const map: Record<string, { label: string; variant: 'success' | 'danger' | 'info' | 'neutral' | 'warning' }> = {
    pending: { label: '等待中', variant: 'neutral' },
    queued: { label: '排队中', variant: 'info' },
    running: { label: '执行中', variant: 'info' },
    evaluating: { label: '计算指标中', variant: 'info' },
    calculating: { label: '计算指标中', variant: 'info' },
    completed: { label: '已完成', variant: 'success' },
    failed: { label: '执行失败', variant: 'danger' },
    skipped: { label: '已跳过', variant: 'neutral' },
    stopped: { label: '已停止', variant: 'neutral' },
    deleted: { label: '已删除', variant: 'neutral' },
  }
  const meta = map[status ?? ''] ?? { label: status ?? '—', variant: 'neutral' as const }
  return <StatusBadge label={meta.label} variant={meta.variant} />
}

/** 终态任务（review_service TaskStatus.is_terminal 口径：completed/failed/stopped/skipped） */
const TERMINAL_STATUSES = ['completed', 'failed', 'stopped', 'skipped']

interface ReviewTarget {
  caseId: string
  caseName?: string
  results: CaseResultForReview[]
  evaluationStatus: string | null
  caseNameByResultId?: Record<number, string>
  preset?: { evaluationStatus?: string; comment?: string }
  /** INT-1279：用例评估维度 id（AI 复核按用例评估维度显式传 dimension_ids，真实库无 LLM 判分维度时避免 400） */
  dimensionIds?: number[]
}

/** 行式列表列网格（平铺表头与行、标签/分组组内行共用；列：名称/执行状态/评估状态/耗时/轮次/目标/操作） */
const CASE_ROW_GRID =
  'grid grid-cols-[minmax(0,1fr)_5.75rem_5.75rem_4.25rem_5.25rem_7.5rem_7rem] items-center gap-2 px-2'

/** 目标展示名：API 名/设备名，缺失时按类型 + id 兜底 */
function targetLabel(t: TaskCaseTarget): string {
  if (t.target_name) return t.target_name
  return t.target_type === 'api' ? `API ${t.api_id ?? t.device_id ?? '—'}` : `设备 ${t.device_id ?? '—'}`
}

/**
 * 关联用例行（INT-1492 对照 V9.7.10 `progress-item-small`：一行放下
 * 名称 / 执行状态 / 评估状态 / 耗时 / 轮次 / 操作，行高 54px）。
 * 任务域专属标记保留：分组名（名称次行）、「人工复核」Badge、第 x/y 轮进度、
 * 人工/AI/快速复核钮（终态任务）、移除钮。
 */
function TaskCaseRow({
  c,
  selected,
  onToggle,
  onCaseSelect,
  onRemove,
  canReview,
  canAiReview,
  isTerminal,
  reviewLoading,
  reviewed,
  onReview,
  onAiReview,
  onQuickReview,
}: {
  c: TaskCaseBrief
  selected: boolean
  onToggle: (checked: boolean) => void
  onCaseSelect?: (caseId: string) => void
  onRemove: () => void
  canReview: boolean
  canAiReview: boolean
  isTerminal: boolean
  reviewLoading: boolean
  /** 该用例是否存在人工复核（普通任务取 TaskCaseBrief.reviewed；容器任务按来源任务留痕派生） */
  reviewed: boolean
  onReview: () => void
  onAiReview: () => void
  onQuickReview: () => void
}) {
  /** 耗时：任务侧 ms → 秒（features/testcases 口径格式化，null 落「—」） */
  const durationSeconds = c.duration != null ? Math.round(c.duration / 1000) : null
  /** 轮次：分母 = 用例真实轮次数（rounds_count）；未执行（无耗时）不显示轮次 */
  const roundTotal = c.rounds_count != null && c.rounds_count > 0 ? c.rounds_count : 1
  const roundsExecuted = c.duration != null
  const roundPercent = roundsExecuted ? 100 : 0

  return (
    <div
      role='row'
      data-testid='task-case-row'
      data-case-id={c.case_id}
      style={{ height: CASE_ROW_HEIGHT }}
      className={cn(
        'hover:bg-muted/40 border-b transition-colors last:border-0',
        CASE_ROW_GRID,
        selected && 'bg-accent/40'
      )}
    >
      {/* 名称 + 用例 ID/分组次行 */}
      <div role='cell' className='flex min-w-0 items-center gap-2'>
        <Checkbox
          checked={selected}
          aria-label={`选择 ${c.name}`}
          onCheckedChange={(checked) => onToggle(checked)}
        />
        <div className='min-w-0'>
          <div className='flex min-w-0 items-center gap-1.5'>
            {onCaseSelect ? (
              <button
                type='button'
                className='hover:text-primary truncate text-left font-medium'
                title={`查看用例详情：${c.name}`}
                onClick={() => onCaseSelect(c.case_id)}
              >
                {c.name}
              </button>
            ) : (
              <span className='truncate font-medium' title={c.name}>
                {c.name}
              </span>
            )}
            {reviewed && <ReviewBadge />}
          </div>
          <div className='text-muted-foreground flex min-w-0 items-center gap-2 text-[11px]'>
            <button
              type='button'
              className='hover:text-foreground shrink-0 font-mono tabular-nums hover:underline'
              title='点击复制用例 ID'
              onClick={() => {
                void navigator.clipboard?.writeText(c.case_id)
                toast.success('已复制')
              }}
            >
              {c.case_id.slice(0, 8)}
            </button>
            {c.group_name && <span className='truncate'>{c.group_name}</span>}
          </div>
        </div>
      </div>

      {/* 执行状态（failed → 执行失败） */}
      <div role='cell' data-column='execution'>
        <CaseStatusBadge status={c.execution_status} kind='execution' />
      </div>

      {/* 评估状态（failed → 评估失败；未执行不显示评估中） */}
      <div role='cell' data-column='evaluation'>
        <CaseStatusBadge
          status={c.evaluation_status}
          kind='evaluation'
          executionStatus={c.execution_status}
        />
      </div>

      {/* 耗时 */}
      <div
        role='cell'
        data-column='duration'
        className='text-muted-foreground font-mono text-xs tabular-nums'
      >
        {formatCaseDuration(durationSeconds)}
      </div>

      {/* 轮次（第 x/y 轮 + Progress h-1，§4.4；y = 用例真实轮次数，未执行显示 —） */}
      <div role='cell' data-column='rounds' className='flex items-center gap-1.5'>
        <span className='text-muted-foreground font-mono text-xs whitespace-nowrap tabular-nums'>
          {roundsExecuted ? `第 ${roundTotal}/${roundTotal} 轮` : '—'}
        </span>
        <Progress value={roundPercent} size='xs' className='w-6 shrink-0' />
      </div>

      {/* 设备/API：合并后按执行行统计「已完成/总数」，hover 看每个设备/API 明细 */}
      <div role='cell' data-column='targets' className='min-w-0'>
        {(() => {
          const targets = c.targets ?? []
          if (targets.length === 0) {
            return <span className='text-muted-foreground text-xs'>—</span>
          }
          const done = targets.filter((t) => t.execution_status === 'completed').length
          const failed = targets.some((t) => t.execution_status === 'failed')
          const finished = done === targets.length
          return (
            <span
              className={cn(
                'font-mono text-xs tabular-nums',
                failed ? 'text-destructive' : finished ? 'text-emerald-600' : 'text-muted-foreground'
              )}
              title={targets
                .map((t) => `${targetLabel(t)}：执行 ${t.execution_status ?? '—'} / 评估 ${t.evaluation_status ?? '—'}`)
                .join('\n')}
            >
              {done}/{targets.length}
            </span>
          )
        })()}
      </div>

      {/* 操作：人工复核 / AI 复核 / 快速复核（终态任务）+ 移除用例 */}
      <div role='cell' className='flex items-center justify-end gap-0.5'>
        {canReview && isTerminal && (
          <Button
            variant='ghost'
            size='icon-sm'
            disabled={reviewLoading}
            aria-label='人工复核'
            title='人工复核该用例结果'
            onClick={onReview}
          >
            <ClipboardCheck aria-hidden='true' className='size-3.5' />
          </Button>
        )}
        {canAiReview && isTerminal && (
          <Button
            variant='ghost'
            size='icon-sm'
            className='text-muted-foreground'
            disabled={reviewLoading}
            aria-label='AI 复核'
            title='AI 复核（灵犀Agent 对话式复核，可追问）'
            onClick={onAiReview}
          >
            <Sparkles aria-hidden='true' className='size-3.5' />
          </Button>
        )}
        {canAiReview && isTerminal && (
          <Button
            variant='ghost'
            size='icon-sm'
            className='text-muted-foreground/70'
            disabled={reviewLoading}
            aria-label='快速复核'
            title='快速复核（一次性状态机，无需追问的快速复检）'
            onClick={onQuickReview}
          >
            <Zap aria-hidden='true' className='size-3.5' />
          </Button>
        )}
        <Button
          variant='ghost'
          size='icon-sm'
          className='text-destructive hover:text-destructive'
          aria-label='移除用例'
          title='移除用例'
          onClick={onRemove}
        >
          <Trash2 aria-hidden='true' className='size-3.5' />
        </Button>
      </div>
    </div>
  )
}

export function CaseAssociation({
  detail,
  onCaseSelect,
}: {
  detail: TaskDetailData
  /** 用例行点击回调（10_测试执行.md §3.7：步骤四关联用例行点击 → 用例详情弹窗 §5.2） */
  onCaseSelect?: (caseId: string) => void
}) {
  const { hasPermission } = usePermissions()
  const actions = useTaskActions()
  const [tab, setTab] = useState('cases')
  const [view, setView] = useState<ViewMode>('flat')
  const [status, setStatus] = useState('all')
  /** INT-1492：搜索（按用例名称或用例 ID，V9.7.10 caseSearchQuery 口径） */
  const [keyword, setKeyword] = useState('')
  /** INT-1492：平铺虚拟滚动窗口起点（scrollTop / CASE_ROW_HEIGHT） */
  const [scrollTop, setScrollTop] = useState(0)
  const caseListRef = useRef<HTMLDivElement>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [reviewTarget, setReviewTarget] = useState<ReviewTarget | null>(null)
  const [aiReviewTarget, setAiReviewTarget] = useState<ReviewTarget | null>(null)
  const [quickReviewTarget, setQuickReviewTarget] = useState<ReviewTarget | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [reviewLoading, setReviewLoading] = useState(false)
  /** INT-949 移除用例确认（§5.9：两段后果文案 + 末例二次确认） */
  const [caseRemoveTarget, setCaseRemoveTarget] = useState<{
    caseId: string
    phase: CaseRemovePhase
    isLast: boolean
  } | null>(null)
  const [lastCaseOpen, setLastCaseOpen] = useState(false)
  const [caseRemovePending, setCaseRemovePending] = useState(false)

  const cases = detail.cases ?? []
  /** 状态筛选 + 搜索（名称/ID 子串，忽略大小写） */
  const filtered = cases.filter((c) => {
    if (!matchesStatusFilter(c, status)) return false
    const q = keyword.trim().toLowerCase()
    if (!q) return true
    return c.name.toLowerCase().includes(q) || c.case_id.toLowerCase().includes(q)
  })

  /** 虚拟滚动窗口（上下各 CASE_ROW_OVERSCAN 行缓冲，基线 visibleCases 同口径） */
  const windowStart = Math.max(
    0,
    Math.floor(scrollTop / CASE_ROW_HEIGHT) - CASE_ROW_OVERSCAN
  )
  const windowSize =
    Math.ceil(CASE_LIST_MAX_HEIGHT / CASE_ROW_HEIGHT) + CASE_ROW_OVERSCAN * 2 + 1
  const windowEnd = Math.min(filtered.length, windowStart + windowSize)
  const visibleCases = filtered.slice(windowStart, windowEnd)

  /** 视图/筛选/搜索变化时回到列表顶部（避免深滚动位置落到过滤后越界） */
  useEffect(() => {
    setScrollTop(0)
    if (caseListRef.current) caseListRef.current.scrollTop = 0
  }, [view, status, keyword])

  // INT-1241：任务类型概念已移除（负责人 2026-10-22 口径）——关联资源区标题/空态统一中性「关联资源」
  const resourceLabel = '关联资源'
  const isTerminal = TERMINAL_STATUSES.includes(detail.status)
  // 人工复核提交权限（task.result.review）；AI 复核发起/对话/保存结论/驳回（task.result.ai_review，INT-800 已注册）
  const canReview = hasPermission('task.result.review')
  const canAiReview = hasPermission('task.result.ai_review')

  // INT-1626：挑选合并容器不拥有 test_results（引用源结果），复核留痕落在源任务下，
  // 容器详情 review_count 恒 0 → 容器按「结果归属任务」聚合历史后再算已复核条数；
  // 普通任务保持后端 review_count 口径（不为计数多发历史请求）。
  const reviewScope = useReviewRecordScope(detail.id)
  const containerHistory = useScopedReviewHistory(detail.id, reviewScope.isContainer)
  const reviewCount = reviewScope.isContainer
    ? containerHistory.reviewedResultCount
    : detail.review_count
  /** 容器任务：用例行「人工复核」标记按来源任务留痕派生（TaskCaseBrief.reviewed 由容器 id 算恒 false） */
  const reviewedCaseIds = new Set(
    (containerHistory.data ?? []).map((item) => item.testCaseId)
  )

  // 标签分组（按用例 tags 首标签粗分）
  const tagGroups = filtered.reduce<Record<string, typeof filtered>>((acc, c) => {
    const key = c.tags[0] ?? '未分组'
    acc[key] ??= []
    acc[key].push(c)
    return acc
  }, {})
  // 用例分组（按后端 group_name；无分组归「未分组」，INT-1033 对齐用例管理分组口径）
  const groupGroups = filtered.reduce<Record<string, typeof filtered>>((acc, c) => {
    const key = c.group_name ?? '未分组'
    acc[key] ??= []
    acc[key].push(c)
    return acc
  }, {})

  const toggleRow = (caseId: string, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (checked) next.add(caseId)
      else next.delete(caseId)
      return next
    })
  }

  /** 移除用例确认（INT-949，§5.9）：先弹后果文案；末例转二次确认，取消不发请求 */
  const handleRemoveCase = async () => {
    if (!caseRemoveTarget) return
    // 末例：首段确认后关首弹窗，弹二次确认（§5.9「移除并停止任务 / 仅移除用例」）
    if (caseRemoveTarget.isLast) {
      setLastCaseOpen(true)
      return
    }
    setCaseRemovePending(true)
    try {
      await actions.removeCase.mutateAsync({
        taskId: detail.id,
        caseId: caseRemoveTarget.caseId,
      })
      setSelected((prev) => {
        const next = new Set(prev)
        next.delete(caseRemoveTarget.caseId)
        return next
      })
      setCaseRemoveTarget(null)
    } catch {
      // mutation onError 已 toast
    } finally {
      setCaseRemovePending(false)
    }
  }

  /** 末例二次确认副钮「仅移除用例」（§5.9） */
  const handleLastCaseOnly = async () => {
    if (!caseRemoveTarget) return
    setCaseRemovePending(true)
    try {
      await actions.removeCase.mutateAsync({
        taskId: detail.id,
        caseId: caseRemoveTarget.caseId,
      })
      setSelected((prev) => {
        const next = new Set(prev)
        next.delete(caseRemoveTarget.caseId)
        return next
      })
      setCaseRemoveTarget(null)
      setLastCaseOpen(false)
    } catch {
      // mutation onError 已 toast
    } finally {
      setCaseRemovePending(false)
    }
  }

  /** 末例二次确认主钮「移除并停止任务」（§5.9：移除成功后连带停止） */
  const handleLastCaseRemoveAndStop = async () => {
    if (!caseRemoveTarget) return
    setCaseRemovePending(true)
    try {
      await actions.removeCase.mutateAsync({
        taskId: detail.id,
        caseId: caseRemoveTarget.caseId,
      })
      setSelected((prev) => {
        const next = new Set(prev)
        next.delete(caseRemoveTarget.caseId)
        return next
      })
      setCaseRemoveTarget(null)
      setLastCaseOpen(false)
      await actions.stop.mutateAsync(detail.id)
    } catch {
      // mutation onError 已 toast（停止失败不影响用例已移除结果）
    } finally {
      setCaseRemovePending(false)
    }
  }

  /** 单条复核入口：取该用例结果行 → §3.2 弹窗（真实结果数据，result_ids 逐条留痕） */
  const openCaseReview = async (c: TaskCaseBrief) => {
    setReviewLoading(true)
    try {
      const res = await fetchCaseResults(detail.id, c.case_id)
      // 无执行结果的用例不打开可提交的复核弹窗（旧 Vue 基线 TestCaseDetailModal 同口径收口，INT-795 P2-1）
      if (res.results.length === 0) {
        toast.error('该用例无执行结果，无法复核')
        return
      }
      setReviewTarget({
        caseId: c.case_id,
        caseName: res.caseName || c.name,
        results: res.results,
        evaluationStatus: c.evaluation_status,
      })
    } catch (err) {
      toast.error(
        err instanceof Error ? `用例结果加载失败：${err.message}` : '用例结果加载失败'
      )
    } finally {
      setReviewLoading(false)
    }
  }

  /** AI 复核入口（主形态）：取该用例结果行校验有结果 → 打开灵犀Agent 复核会话（§5.2，可追问） */
  const openAiReview = async (c: TaskCaseBrief) => {
    setReviewLoading(true)
    try {
      const res = await fetchCaseResults(detail.id, c.case_id)
      // 无执行结果不发起 AI 复核（§5.2 可发起对象须有结果；INT-795 P2-1）
      if (res.results.length === 0) {
        toast.error('该用例无执行结果，无法复核')
        return
      }
      setAiReviewTarget({
        caseId: c.case_id,
        caseName: res.caseName || c.name,
        results: res.results,
        evaluationStatus: c.evaluation_status,
        dimensionIds: toAiReviewDimensionIds(c.evaluation_dimensions),
      })
    } catch (err) {
      toast.error(
        err instanceof Error ? `用例结果加载失败：${err.message}` : '用例结果加载失败'
      )
    } finally {
      setReviewLoading(false)
    }
  }

  /** 快速复核入口（次要形态）：一次性状态机弹窗（批量/低分初筛，§5.1 裁定） */
  const openQuickReview = async (c: TaskCaseBrief) => {
    setReviewLoading(true)
    try {
      const res = await fetchCaseResults(detail.id, c.case_id)
      if (res.results.length === 0) {
        toast.error('该用例无执行结果，无法复核')
        return
      }
      setQuickReviewTarget({
        caseId: c.case_id,
        caseName: res.caseName || c.name,
        results: res.results,
        evaluationStatus: c.evaluation_status,
        dimensionIds: toAiReviewDimensionIds(c.evaluation_dimensions),
      })
    } catch (err) {
      toast.error(
        err instanceof Error ? `用例结果加载失败：${err.message}` : '用例结果加载失败'
      )
    } finally {
      setReviewLoading(false)
    }
  }

  /** 批量复核入口（勾选多行 → 底部浮条）：并行取各用例结果行聚合 → §3.3 批量弹窗 */
  const openBatchReview = async () => {
    setReviewLoading(true)
    try {
      const entries = await Promise.all(
        [...selected].map(async (caseId) => {
          const c = cases.find((x) => x.case_id === caseId)
          const res = await fetchCaseResults(detail.id, caseId)
          return {
            caseName: c?.name ?? res.caseName,
            evaluationStatus: c?.evaluation_status ?? null,
            results: res.results,
          }
        })
      )
      const caseNameByResultId: Record<number, string> = {}
      for (const e of entries) {
        for (const r of e.results) caseNameByResultId[r.id] = e.caseName
      }
      const results = entries.flatMap((e) => e.results)
      // 勾选用例均无执行结果时不打开可提交的批量复核弹窗（INT-795 P2-1）
      if (results.length === 0) {
        toast.error('勾选用例均无执行结果，无法复核')
        return
      }
      setReviewTarget({
        caseId: '',
        caseName: undefined,
        results,
        evaluationStatus: null,
        caseNameByResultId,
      })
    } catch (err) {
      toast.error(
        err instanceof Error ? `用例结果加载失败：${err.message}` : '用例结果加载失败'
      )
    } finally {
      setReviewLoading(false)
    }
  }

  /**
   * 用例行渲染（平铺虚拟窗口与标签/分组组内行共用）。
   * key 必须全局唯一：任务 526 中同一 case_id 会重复出现（1749 条记录 / 1737 个用例），
   * 只用 case_id 作 key 会在虚拟窗口移动时复用错节点、残留旧行并把容器 scrollHeight 撑大。
   */
  const renderCaseRow = (c: TaskCaseBrief, key: string) => (
    <TaskCaseRow
      key={key}
      c={c}
      selected={selected.has(c.case_id)}
      onToggle={(checked) => toggleRow(c.case_id, checked)}
      onCaseSelect={onCaseSelect}
      onRemove={() => {
        // INT-949：走 §5.9 移除确认（两段后果文案 + 末例二次确认）→ actions.removeCase API，
        // 不沿用设计分支仅 toast 的占位实现（接线保留 wiring/react 接口调用）
        setCaseRemoveTarget({
          caseId: c.case_id,
          phase: getCaseRemovePhase(detail.execution_status ?? detail.status),
          isLast: cases.length === 1,
        })
      }}
      canReview={canReview}
      canAiReview={canAiReview}
      isTerminal={isTerminal}
      reviewLoading={reviewLoading}
      reviewed={
        c.reviewed ||
        (reviewScope.isContainer && reviewedCaseIds.has(c.case_id))
      }
      onReview={() => openCaseReview(c)}
      onAiReview={() => openAiReview(c)}
      onQuickReview={() => openQuickReview(c)}
    />
  )

  return (
    <Card size='sm' className='gap-3 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='flex items-center gap-2 text-sm font-medium'>
          {tab === 'cases' ? '关联用例' : resourceLabel}
          {/* 用例计数（筛选/搜索后由 n 变「命中 n / 共 m」，作为筛选结果的可见证据） */}
          {tab === 'cases' && cases.length > 0 && (
            <Badge
              variant='secondary'
              className='rounded-md px-1.5 font-mono text-[11px] tabular-nums'
              data-slot='case-count-badge'
            >
              {filtered.length === cases.length
                ? cases.length
                : `${filtered.length} / ${cases.length}`}
            </Badge>
          )}
        </CardTitle>
        <div data-slot='card-action' className='flex items-center gap-1.5'>
          {tab === 'cases' && (
            <>
              {/* INT-1492：搜索（名称或 ID，V9.7.10 基线搜索框；1737 条用例定位） */}
              <div className='relative'>
                <Search
                  aria-hidden='true'
                  className='text-muted-foreground pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2'
                />
                <Input
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  placeholder='搜索用例名称或 ID…'
                  aria-label='搜索用例'
                  className='h-8 w-52 pl-7 text-xs'
                />
              </div>
              <Tabs
                value={view}
                onValueChange={(v) => setView(v as ViewMode)}
                className='group/tabs'
              >
                <TabsList variant='line' className='h-8'>
                  {VIEW_OPTIONS.map((option) => (
                    <TabsTrigger key={option.value} value={option.value} className='px-2 text-xs'>
                      {option.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              <Select value={status} onValueChange={(value) => setStatus(value ?? 'all')}>
                <SelectTrigger size='sm' className='h-8 gap-1.5 px-2.5' aria-label='状态筛选'>
                  <SelectValue>
                    {CASE_STATUS_OPTIONS.find((option) => option.value === status)?.label ?? '全部状态'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent align='end'>
                  {CASE_STATUS_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {/* INT-795：任务复核计数 + 查看复核历史（task:read；review_count 驱动，§3.5）
                  INT-1626：容器任务按来源任务聚合，容器 id 直查恒空 */}
              {reviewCount > 0 && (
                <>
                  <Badge
                    variant='secondary'
                    className='h-6 gap-1 rounded-md px-2 text-[11px]'
                    data-slot='review-count-badge'
                  >
                    <ClipboardCheck aria-hidden='true' className='size-3' />
                    已复核 {reviewCount} 条
                  </Badge>
                  <Button
                    variant='ghost'
                    size='sm'
                    className='text-muted-foreground h-7 gap-1 text-xs'
                    onClick={() => setHistoryOpen(true)}
                  >
                    <History aria-hidden='true' className='size-3.5' />
                    查看复核历史
                  </Button>
                </>
              )}
            </>
          )}
        </div>
      </CardHeader>

      <Tabs value={tab} onValueChange={setTab} className='px-4 group/tabs'>
        <TabsList variant='line' className='h-8'>
          <TabsTrigger value='cases' className='px-2.5 text-xs'>
            关联用例
          </TabsTrigger>
          <TabsTrigger value='resources' className='px-2.5 text-xs'>
            {resourceLabel}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <CardContent className='px-4 pb-1'>
        {tab === 'resources' ? (
          detail.devices.length > 0 || detail.apis.length > 0 ? (
            <div className='flex flex-col gap-1.5'>
              {detail.devices.map((device) => (
                <div key={device.id} className='flex items-center gap-2 rounded-lg border px-3 py-2 text-sm'>
                  <span aria-hidden='true' className={cn('size-2 rounded-full', device.status === 'online' ? 'bg-success' : 'bg-muted')} />
                  <span className='font-medium'>{device.name}</span>
                  <span className='text-muted-foreground text-xs'>
                    {device.status === 'online' ? '在线' : '离线'} · {device.model ?? '—'}
                  </span>
                </div>
              ))}
              {detail.apis.map((api) => (
                <div key={api.id} className='flex items-center gap-2 rounded-lg border px-3 py-2 text-sm'>
                  <span aria-hidden='true' className={cn('size-2 rounded-full', api.status === 'online' ? 'bg-success' : 'bg-muted')} />
                  <span className='font-medium'>{api.name}</span>
                  <span className='text-muted-foreground text-xs'>
                    {api.status === 'online' ? '在线' : '离线'}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className='text-muted-foreground py-6 text-center text-sm'>
              暂无关联资源
            </p>
          )
        ) : filtered.length === 0 ? (
          <p className='text-muted-foreground py-6 text-center text-sm'>暂无关联用例</p>
        ) : view === 'flat' ? (
          /* INT-1492：平铺 = 紧凑行式列表 + 虚拟滚动（max-h-[400px]，只渲染可视窗口行） */
          <div
            ref={caseListRef}
            role='table'
            aria-label='关联用例列表'
            data-testid='task-case-list'
            className='max-h-[400px] overflow-y-auto rounded-lg border'
            onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
          >
            {/* 列头（sticky，列与行共用 CASE_ROW_GRID） */}
            <div
              role='row'
              className={cn(
                'bg-muted/60 text-muted-foreground sticky top-0 z-10 border-b text-xs font-medium backdrop-blur',
                CASE_ROW_GRID,
                'h-8'
              )}
            >
              <div role='columnheader'>用例名称</div>
              <div role='columnheader'>执行状态</div>
              <div role='columnheader'>评估状态</div>
              <div role='columnheader'>耗时</div>
              <div role='columnheader'>轮次</div>
              <div role='columnheader'>设备/API</div>
              <div role='columnheader' className='text-right'>
                操作
              </div>
            </div>
            {/* 虚拟滚动占位：总高 = 命中条数 × 行高；渲染窗口整体 translateY */}
            <div
              style={{ height: filtered.length * CASE_ROW_HEIGHT, position: 'relative' }}
              data-testid='task-case-list-spacer'
            >
              <div style={{ transform: `translateY(${windowStart * CASE_ROW_HEIGHT}px)` }}>
                {visibleCases.map((c, index) =>
                  renderCaseRow(c, `${windowStart + index}-${c.case_id}`)
                )}
              </div>
            </div>
          </div>
        ) : (
          /* 标签/分组态：分组卡内同样用紧凑行（基线组内 progress-item-small 口径），区高受控 */
          <div
            className='max-h-[400px] overflow-y-auto'
            data-testid='task-case-grouped-list'
          >
            <div className='flex flex-col gap-2'>
              {Object.entries(view === 'group' ? groupGroups : tagGroups).map(([group, rows]) => (
                <Collapsible key={group} className='rounded-lg border'>
                  <CollapsibleTrigger className='hover:bg-muted/40 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors'>
                    {group}
                    <Badge className='rounded-sm px-1 font-normal'>{rows.length}</Badge>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    {rows.map((c, index) =>
                      renderCaseRow(c, `${group}-${index}-${c.case_id}`)
                    )}
                  </CollapsibleContent>
                </Collapsible>
              ))}
            </div>
          </div>
        )}
      </CardContent>

      {/* INT-795：批量复核浮条（勾选多行 → §3.3） */}
      <ManualReviewBatchBar
        selectedCount={selected.size}
        onClear={() => setSelected(new Set())}
        onBatchReview={() => void openBatchReview()}
        disabled={!canReview || !isTerminal || reviewLoading}
      />

      {/* §3.2/§3.3 复核弹窗（单条=results 长度 1，批量=results[n]；AI 采纳时 preset 预填） */}
      <ManualReviewDialog
        open={reviewTarget != null}
        onOpenChange={(next) => {
          if (!next) setReviewTarget(null)
        }}
        taskId={detail.id}
        taskName={detail.name}
        caseName={reviewTarget?.caseName}
        caseNameByResultId={reviewTarget?.caseNameByResultId}
        results={reviewTarget?.results ?? []}
        evaluationStatus={reviewTarget?.evaluationStatus}
        preset={reviewTarget?.preset}
      />

      {/* §5.2 AI 复核主入口（灵犀Agent 复核会话，可追问；上下文由会话自身预填 §5.3） */}
      <AiReviewSessionDialog
        open={aiReviewTarget != null}
        onOpenChange={(next) => {
          if (!next) setAiReviewTarget(null)
        }}
        taskId={detail.id}
        caseId={aiReviewTarget?.caseId ?? ''}
        caseName={aiReviewTarget?.caseName}
        dimensionIds={aiReviewTarget?.dimensionIds}
      />

      {/* §5.1 快速复核次要入口（一次性状态机，批量/低分初筛场景） */}
      <QuickAiReviewDialog
        open={quickReviewTarget != null}
        onOpenChange={(next) => {
          if (!next) setQuickReviewTarget(null)
        }}
        taskId={detail.id}
        caseId={quickReviewTarget?.caseId ?? ''}
        caseName={quickReviewTarget?.caseName}
        results={quickReviewTarget?.results ?? []}
        evaluationStatus={quickReviewTarget?.evaluationStatus}
        dimensionIds={quickReviewTarget?.dimensionIds}
      />

      {/* §3.4 任务复核历史抽屉 */}
      <ReviewHistoryDrawer
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        taskId={detail.id}
        taskName={detail.name}
        caseNameMap={buildCaseNameMap(cases)}
      />

      {/* §5.9 移除用例确认（INT-949：首段按任务阶段两段后果文案；末例 → 二次确认） */}
      <TaskConfirmDialog
        open={caseRemoveTarget != null && !lastCaseOpen}
        state={caseRemoveTarget ? { kind: 'remove-case', phase: caseRemoveTarget.phase } : null}
        onOpenChange={(open) => !open && setCaseRemoveTarget(null)}
        isLoading={caseRemovePending}
        onConfirm={() => void handleRemoveCase()}
      />
      {/* §5.9 末例二次确认：「移除并停止任务」主钮 destructive /「仅移除用例」副钮 */}
      <AlertDialog
        open={lastCaseOpen}
        onOpenChange={(open) => {
          if (!open) {
            setLastCaseOpen(false)
            setCaseRemoveTarget(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>移除用例</AlertDialogTitle>
            <AlertDialogDescription>
              这是任务中最后一个用例，移除后任务将不含任何用例。是否连任务一并停止（后续可在任务列表删除该任务）？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <Button
              variant='outline'
              disabled={caseRemovePending}
              onClick={() => void handleLastCaseOnly()}
            >
              仅移除用例
            </Button>
            <Button
              variant='destructive'
              disabled={caseRemovePending}
              onClick={() => void handleLastCaseRemoveAndStop()}
            >
              移除并停止任务
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
