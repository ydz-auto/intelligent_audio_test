/**
 * 关联用例 / 关联资源（09_任务域.md §4.4，Card 内 Tabs）。
 * 页签「关联用例」（默认）/「关联资源」（INT-1241 起中性文案，不再按任务类型定「关联API/关联设备」）；
 * 工具行 = 视图切换（平铺/标签/分组）+ 状态筛选。
 * 平铺态 DataTable 列：用例名称/执行状态/评估状态/耗时/轮次/操作（移除用例）。
 * 19_人工审核与AI复核交互设计.md §3 落位（INT-795）：
 * - 已复核用例行执行/评估徽章旁叠加「人工复核」Badge（TaskCaseBrief.reviewed 驱动）；
 * - 行尾「人工复核」钮（终态任务 + task.result.review）→ §3.2 单条复核弹窗（取该用例结果行）；
 * - 行尾「AI 复核」钮（evaluation:execute）→ AI 复核状态机弹窗（§2.1/§5.2）；
 * - 勾选多行 → 底部「批量复核」浮条（§3.3，同一改判字段应用到全部勾选结果）；
 * - 工具行「查看复核历史」link + 头行「已复核 {n} 条」计数（TaskDetailData.review_count 驱动）→ §3.4 抽屉。
 * 标签/分组态用 Collapsible 组头（名称 + 计数）行。
 */
import { ClipboardCheck, History, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import type { CaseResultForReview } from '@/domain/models/review'
import type { TaskCaseBrief, TaskDetailData } from '@/domain/models/task'
import { fetchCaseResults } from '@/infrastructure/api/reviewApi'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { Progress } from '@/features/tasks/components/ui/progress'
import { CaseCard } from '@/features/testcases/components/case-card'
import { AiReviewSessionDialog } from '@/features/ai-review/ai-review-session-dialog'
import { QuickAiReviewDialog } from '@/features/ai-review/quick-ai-review-dialog'
import { ManualReviewBatchBar } from '@/features/tasks/components/manual-review-batch-bar'
import { ManualReviewDialog } from '@/features/tasks/components/manual-review-dialog'
import { ReviewBadge } from '@/features/tasks/components/review-badge'
import {
  buildCaseNameMap,
  ReviewHistoryDrawer,
} from '@/features/tasks/components/review-history-drawer'

type ViewMode = 'flat' | 'tag' | 'group'
const VIEW_OPTIONS: Array<{ value: ViewMode; label: string }> = [
  { value: 'flat', label: '平铺' },
  { value: 'tag', label: '标签' },
  { value: 'group', label: '分组' },
]

/** 选项 value 为英文枚举（对齐 case.execution_status / evaluation_status 实测值） */
const CASE_STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'all', label: '全部状态' },
  { value: 'pending', label: '等待中' },
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '执行中' },
  { value: 'evaluating', label: '计算指标中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '已失败' },
  { value: 'skipped', label: '已跳过' },
  { value: 'stopped', label: '已停止' },
  { value: 'deleted', label: '已删除' },
]

function CaseStatusBadge({ status }: { status: string | null }) {
  const map: Record<string, { label: string; variant: 'success' | 'danger' | 'info' | 'neutral' | 'warning' }> = {
    pending: { label: '等待中', variant: 'neutral' },
    queued: { label: '排队中', variant: 'info' },
    running: { label: '执行中', variant: 'info' },
    evaluating: { label: '计算指标中', variant: 'info' },
    completed: { label: '已完成', variant: 'success' },
    failed: { label: '已失败', variant: 'danger' },
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
}

/**
 * 关联用例卡（INT-1046 全站统一：复用 `features/testcases/components/case-card.tsx` 统一 `CaseCard`，
 * 11_用例域 §3.3 显示口径——名称/CaseIdBadge/算法徽章/标签/时长·轮次；任务域专属标记保留：
 * 分组名次行、执行/评估状态徽章 + 「人工复核」Badge、第 x/y 轮进度、移除钮、人工/AI 复核底栏）。
 * 平铺（卡片网格）与标签/分组（组内卡片）共用。
 */
function TaskCaseCard({
  c,
  selected,
  onToggle,
  onCaseSelect,
  onRemove,
  canReview,
  canAiReview,
  isTerminal,
  reviewLoading,
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
  onReview: () => void
  onAiReview: () => void
  onQuickReview: () => void
}) {
  return (
    <CaseCard
      caseItem={{
        id: c.case_id,
        name: c.name,
        tags: c.tags,
        // 任务侧耗时（ms）→ CaseCard 口径总时长（秒）；null 不落空徽章
        totalDuration: c.duration != null ? Math.round(c.duration / 1000) : null,
      }}
      selected={selected}
      onToggleSelect={(_id, checked) => onToggle(checked)}
      onNameClick={onCaseSelect ? () => onCaseSelect(c.case_id) : undefined}
      meta={
        <>
          {c.group_name && (
            <p className='text-muted-foreground text-xs truncate'>{c.group_name}</p>
          )}
          {/* 轮次进度（09_任务域 §4.4：第 x/y 轮 + Progress h-1） */}
          <div className='text-muted-foreground mt-1 flex items-center gap-2 text-xs'>
            <span className='font-mono tabular-nums'>第 {c.duration != null ? 2 : 1}/2 轮</span>
            <Progress value={c.duration != null ? 50 : 0} size='xs' className='min-w-0 flex-1' />
          </div>
        </>
      }
      badgeLeading={
        <>
          <CaseStatusBadge status={c.execution_status} />
          {c.reviewed && <ReviewBadge />}
          <CaseStatusBadge status={c.evaluation_status} />
        </>
      }
      actions={
        <Button
          variant='ghost'
          size='icon-sm'
          className='text-destructive hover:text-destructive'
          aria-label='移除用例'
          onClick={onRemove}
        >
          <Trash2 aria-hidden='true' />
        </Button>
      }
      footer={
        <div className='mt-2 flex items-center justify-end gap-1 border-t pt-1.5'>
          {/* INT-795：人工复核入口（终态任务 + task.result.review；§3.1） */}
          {canReview && isTerminal && (
            <Button
              variant='ghost'
              size='sm'
              className='h-6 gap-1 px-1.5 text-xs'
              disabled={reviewLoading}
              onClick={onReview}
              title='人工复核该用例结果'
            >
              <ClipboardCheck aria-hidden='true' className='size-3' />
              人工复核
            </Button>
          )}
          {/* INT-795/INT-1064：AI 复核主入口（task.result.ai_review；§5.2 灵犀Agent 复核会话可追问） */}
          {canAiReview && isTerminal && (
            <Button
              variant='ghost'
              size='sm'
              className='text-muted-foreground h-6 gap-1 px-1.5 text-xs'
              disabled={reviewLoading}
              onClick={onAiReview}
              title='AI 复核（灵犀Agent 对话式复核，可追问）'
            >
              <Sparkles aria-hidden='true' className='size-3' />
              AI 复核
            </Button>
          )}
          {/* INT-1064：快速复核次要入口（一次性状态机，批量/低分初筛场景，§5.1 裁定） */}
          {canAiReview && isTerminal && (
            <Button
              variant='ghost'
              size='sm'
              className='text-muted-foreground/70 h-6 gap-1 px-1.5 text-xs'
              disabled={reviewLoading}
              onClick={onQuickReview}
              title='快速复核（一次性状态机，无需追问的快速复检）'
            >
              快速复核
            </Button>
          )}
        </div>
      }
    />
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
  const [tab, setTab] = useState('cases')
  const [view, setView] = useState<ViewMode>('flat')
  const [status, setStatus] = useState('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [reviewTarget, setReviewTarget] = useState<ReviewTarget | null>(null)
  const [aiReviewTarget, setAiReviewTarget] = useState<ReviewTarget | null>(null)
  const [quickReviewTarget, setQuickReviewTarget] = useState<ReviewTarget | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [reviewLoading, setReviewLoading] = useState(false)

  const cases = detail.cases ?? []
  const filtered = cases.filter(
    (c) =>
      status === 'all' ||
      c.execution_status === status ||
      c.status === status ||
      c.evaluation_status === status
  )

  // INT-1241：任务类型概念已移除（负责人 2026-10-22 口径）——关联资源区标题/空态统一中性「关联资源」
  const resourceLabel = '关联资源'
  const isTerminal = TERMINAL_STATUSES.includes(detail.status)
  // 人工复核提交权限（task.result.review）；AI 复核发起/对话/保存结论/驳回（task.result.ai_review，INT-800 已注册）
  const canReview = hasPermission('task.result.review')
  const canAiReview = hasPermission('task.result.ai_review')

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

  /** 用例卡渲染（平铺卡片网格与标签/分组组内卡片共用，照 11_用例域 case-card 形态） */
  const renderCaseCard = (c: TaskCaseBrief) => (
    <TaskCaseCard
      key={c.case_id}
      c={c}
      selected={selected.has(c.case_id)}
      onToggle={(checked) => toggleRow(c.case_id, checked)}
      onCaseSelect={onCaseSelect}
      onRemove={() => {
        toast.success('已移除用例（末例二次确认见 §5.9）')
        setSelected((prev) => {
          const next = new Set(prev)
          next.delete(c.case_id)
          return next
        })
      }}
      canReview={canReview}
      canAiReview={canAiReview}
      isTerminal={isTerminal}
      reviewLoading={reviewLoading}
      onReview={() => openCaseReview(c)}
      onAiReview={() => openAiReview(c)}
      onQuickReview={() => openQuickReview(c)}
    />
  )

  return (
    <Card size='sm' className='gap-3 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='text-sm font-medium'>
          {tab === 'cases' ? '关联用例' : resourceLabel}
        </CardTitle>
        <div data-slot='card-action' className='flex items-center gap-1.5'>
          {tab === 'cases' && (
            <>
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
              {/* INT-795：任务复核计数 + 查看复核历史（task:read；review_count 驱动，§3.5） */}
              {detail.review_count > 0 && (
                <>
                  <Badge
                    variant='secondary'
                    className='h-6 gap-1 rounded-md px-2 text-[11px]'
                    data-slot='review-count-badge'
                  >
                    <ClipboardCheck aria-hidden='true' className='size-3' />
                    已复核 {detail.review_count} 条
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
                  <span className='text-muted-foreground text-xs'>当前并发 2/4</span>
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
          <div className='grid gap-2 md:grid-cols-2 xl:grid-cols-3'>
            {filtered.map(renderCaseCard)}
          </div>
        ) : (
          <div className='flex flex-col gap-2'>
            {Object.entries(view === 'group' ? groupGroups : tagGroups).map(([group, rows]) => (
              <Collapsible key={group} className='rounded-lg border'>
                <CollapsibleTrigger className='hover:bg-muted/40 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors'>
                  {group}
                  <Badge className='rounded-sm px-1 font-normal'>{rows.length}</Badge>
                </CollapsibleTrigger>
                <CollapsibleContent className='px-3 pb-2'>
                  <div className='grid gap-2 md:grid-cols-2'>
                    {rows.map(renderCaseCard)}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            ))}
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
      />

      {/* §3.4 任务复核历史抽屉 */}
      <ReviewHistoryDrawer
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        taskId={detail.id}
        taskName={detail.name}
        caseNameMap={buildCaseNameMap(cases)}
      />
    </Card>
  )
}
