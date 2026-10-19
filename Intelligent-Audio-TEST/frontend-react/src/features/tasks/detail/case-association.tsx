/**
 * 关联用例 / 关联设备（09_任务域.md §4.4，Card 内 Tabs）。
 * 页签「关联用例」（默认）/「关联{设备|API}」；工具行 = 视图切换（平铺/标签/分组）+ 状态筛选。
 * 平铺态 DataTable 列：用例名称/执行状态/评估状态/耗时/操作（移除用例）。
 * （轮次列 INT-932 P3-2 移除：TaskCaseBrief 无真实轮次数据，原 `第 n/2 轮` 为 mock 残留）
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
import { ClipboardCheck, History, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useTaskActions } from '@/application/tasks/use-task-actions'
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
import { cn } from '@/lib/utils'
import type { CaseResultForReview } from '@/domain/models/review'
import type { TaskCaseBrief, TaskDetailData } from '@/domain/models/task'
import { fetchCaseResults } from '@/infrastructure/api/reviewApi'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { formatDuration } from '@/features/tasks/constants'
import { AiReviewDialog } from '@/features/tasks/components/ai-review-dialog'
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

export function CaseAssociation({
  detail,
  onCaseSelect,
}: {
  detail: TaskDetailData
  /** 用例行点击回调（10_测试执行.md §3.7：步骤四关联用例行点击 → 用例详情弹窗 §5.2） */
  onCaseSelect?: (caseId: string) => void
}) {
  const { hasPermission, hasAnyPermission } = usePermissions()
  const actions = useTaskActions()
  const [tab, setTab] = useState('cases')
  const [view, setView] = useState<ViewMode>('flat')
  const [status, setStatus] = useState('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [reviewTarget, setReviewTarget] = useState<ReviewTarget | null>(null)
  const [aiReviewTarget, setAiReviewTarget] = useState<ReviewTarget | null>(null)
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
  const filtered = cases.filter(
    (c) =>
      status === 'all' ||
      c.execution_status === status ||
      c.status === status ||
      c.evaluation_status === status
  )

  const resourceLabel = detail.device_types.includes('http_api') ? '关联API' : '关联设备'
  const isTerminal = TERMINAL_STATUSES.includes(detail.status)
  // 人工复核提交权限（task.result.review）；AI 复核发起/查看结论 evaluation:execute（§6）
  const canReview = hasPermission('task.result.review')
  const canAiReview = hasAnyPermission(['task.result.review', 'evaluation:execute'])

  // 标签分组（按用例 tags 首标签粗分）
  const tagGroups = filtered.reduce<Record<string, typeof filtered>>((acc, c) => {
    const key = c.tags[0] ?? '未分组'
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

  /** AI 复核入口：取该用例结果行 → AI 复核状态机弹窗 */
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

  /** AI 采纳 → 转人工复核弹窗（预填 AI 判定的评估状态 + 备注=AI 理由，§5.2） */
  const handleAiAdopt = (preset: { evaluationStatus?: string; comment: string }) => {
    if (!aiReviewTarget) return
    setReviewTarget({ ...aiReviewTarget, preset })
    setAiReviewTarget(null)
  }

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
                  <span className='text-muted-foreground text-xs'>
                    {api.status === 'online' ? '在线' : '离线'}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className='text-muted-foreground py-6 text-center text-sm'>
              暂无关联{detail.device_types.includes('http_api') ? 'API' : '设备'}
            </p>
          )
        ) : filtered.length === 0 ? (
          <p className='text-muted-foreground py-6 text-center text-sm'>暂无关联用例</p>
        ) : view === 'flat' ? (
          <div className='overflow-x-auto'>
            <table className='w-full min-w-[720px] text-[13px]'>
              <thead>
                <tr className='bg-[var(--table-header)] text-xs'>
                  <th className='w-11 px-3 py-2'>
                    <Checkbox
                      checked={filtered.length > 0 && filtered.every((c) => selected.has(c.case_id))}
                      aria-label='全选用例'
                      onCheckedChange={(checked) =>
                        setSelected(checked ? new Set(filtered.map((c) => c.case_id)) : new Set())
                      }
                    />
                  </th>
                  <th className='px-3 py-2 text-left font-medium'>用例名称</th>
                  <th className='px-3 py-2 text-left font-medium'>执行状态</th>
                  <th className='px-3 py-2 text-left font-medium'>评估状态</th>
                  <th className='px-3 py-2 text-left font-medium'>耗时</th>
                  <th className='min-w-28 px-3 py-2 text-right font-medium'>操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.case_id} className='hover:bg-muted/40 border-border/60 border-b transition-colors'>
                    <td className='px-3 py-2'>
                      <Checkbox
                        checked={selected.has(c.case_id)}
                        onCheckedChange={(checked) => toggleRow(c.case_id, checked)}
                        aria-label={`选择 ${c.name}`}
                      />
                    </td>
                    <td className='max-w-56 px-3 py-2'>
                      {onCaseSelect ? (
                        <button
                          type='button'
                          className='block max-w-full truncate text-left font-medium hover:text-primary'
                          title='查看用例详情'
                          onClick={() => onCaseSelect(c.case_id)}
                        >
                          {c.name}
                        </button>
                      ) : (
                        <span className='block truncate font-medium'>{c.name}</span>
                      )}
                      <span className='text-muted-foreground block truncate text-xs'>
                        {c.group_name ?? ''}
                      </span>
                    </td>
                    <td className='px-3 py-2'>
                      <div className='flex flex-wrap items-center gap-1'>
                        <CaseStatusBadge status={c.execution_status} />
                        {c.reviewed && <ReviewBadge />}
                      </div>
                    </td>
                    <td className='px-3 py-2'>
                      <CaseStatusBadge status={c.evaluation_status} />
                    </td>
                    <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                      {formatDuration(c.duration)}
                    </td>
                    <td className='px-3 py-2 text-right'>
                      <div className='flex items-center justify-end gap-1'>
                        {/* INT-795：人工复核入口（终态任务 + task.result.review；§3.1） */}
                        {canReview && isTerminal && (
                          <Button
                            variant='ghost'
                            size='sm'
                            className='h-6 gap-1 px-1.5 text-xs'
                            disabled={reviewLoading}
                            onClick={() => openCaseReview(c)}
                            title='人工复核该用例结果'
                          >
                            <ClipboardCheck aria-hidden='true' className='size-3' />
                            人工复核
                          </Button>
                        )}
                        {/* INT-795：AI 复核入口（evaluation:execute；§5.2 待后端立项） */}
                        {canAiReview && isTerminal && (
                          <Button
                            variant='ghost'
                            size='sm'
                            className='text-muted-foreground h-6 gap-1 px-1.5 text-xs'
                            disabled={reviewLoading}
                            onClick={() => openAiReview(c)}
                            title='AI 复核该用例结果（建议层，不直接修改统计）'
                          >
                            <Sparkles aria-hidden='true' className='size-3' />
                            AI 复核
                          </Button>
                        )}
                        <Button
                          variant='ghost'
                          size='icon-sm'
                          className='text-destructive hover:text-destructive'
                          aria-label='移除用例'
                          disabled={actions.removeCase.isPending || caseRemovePending}
                          onClick={() =>
                            setCaseRemoveTarget({
                              caseId: c.case_id,
                              phase: getCaseRemovePhase(detail.execution_status ?? detail.status),
                              isLast: cases.length === 1,
                            })
                          }
                        >
                          <Trash2 aria-hidden='true' />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className='flex flex-col gap-2'>
            {Object.entries(tagGroups).map(([group, rows]) => (
              <Collapsible key={group} className='rounded-lg border'>
                <CollapsibleTrigger className='hover:bg-muted/40 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors'>
                  {group}
                  <Badge className='rounded-sm px-1 font-normal'>{rows.length}</Badge>
                </CollapsibleTrigger>
                <CollapsibleContent className='px-3 pb-2'>
                  <div className='flex flex-col'>
                    {rows.map((c) => (
                      <div key={c.case_id} className='flex items-center gap-2 py-1.5 text-xs'>
                        <span className='min-w-0 flex-1 truncate'>{c.name}</span>
                        <CaseStatusBadge status={c.execution_status} />
                        {c.reviewed && <ReviewBadge />}
                      </div>
                    ))}
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

      {/* §5.2 AI 复核弹窗（状态机：待发起→执行中→已完成→已采纳/已驳回/待查） */}
      <AiReviewDialog
        open={aiReviewTarget != null}
        onOpenChange={(next) => {
          if (!next) setAiReviewTarget(null)
        }}
        taskId={detail.id}
        caseId={aiReviewTarget?.caseId ?? ''}
        caseName={aiReviewTarget?.caseName}
        results={aiReviewTarget?.results ?? []}
        evaluationStatus={aiReviewTarget?.evaluationStatus}
        onAdopt={handleAiAdopt}
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
