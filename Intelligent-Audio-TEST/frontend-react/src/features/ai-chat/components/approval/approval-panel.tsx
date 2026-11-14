/**
 * 审批面板（interfaces 层 ai-chat/approval；§9.4 审批粒度 / §12.2 审批卡 /
 * §9.4.1 拆单批次展示）。
 *
 * - 「计划级批量展示」：同一步骤（proposal.step_id）的写操作提案归到一组，
 *   一次看全该步骤的写操作与 diff/预览（§9.4）；
 * - **但决策仍逐条**：后端一张审批单对应一次 tool call 的单张单，>20 对象 /
 *   跨租户 / 导出敏感数据 / 删除类必须单条，DESTRUCTIVE 永远单条，因此这里不提供
 *   「一次批准多项」，每张卡各自防重复；
 * - §9.4.1 拆单：一次 tool call 被后端拆成 N 张单时，同 `batchId` 的卡按
 *   `batchIndex` 升序聚成一组，组头给「本批 N 张单 · 对象 P 个 · 全部批准后才执行」
 *   口径；任一单被拒 / 过期时组头显示「本批不执行」，不误导为部分执行；
 * - 已决 / 已过期的审批单收进「已处理」折叠区（重连后不重复弹出可操作卡），
 *   批次在折叠区里同样按批聚组，便于看清整批结果。
 */
import { useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Loader } from '@/components/ai-elements/loader'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ChevronDown, ShieldAlert, ShieldCheck, ShieldX } from 'lucide-react'

import {
  AGENT_APPROVAL_COPY,
  AGENT_APPROVAL_STATUS,
  isApprovalExpired,
  isPendingApprovalStatus,
  type AgentApproval,
  type AgentApprovalDecision,
} from '@/domain/models/agent'
import {
  formatApprovalBatchHeader,
  formatApprovalStepId,
  formatApprovalTurn,
  groupApprovalBatches,
  type ApprovalPanelBlock,
} from '@/features/ai-chat/lib/approval'

import { ApprovalCard } from './approval-card'

/** 有过期时间的待审批单存在时，每秒刷新一次计数（到点的卡片不计入待审批） */
function useNowTicker(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => setNow(Date.now()), 1_000)
    return () => clearInterval(timer)
  }, [active])
  return now
}

type ApprovalPanelProps = {
  approvals: AgentApproval[]
  loading?: boolean
  error?: string | null
  decidingApprovalIds?: string[]
  /** 本 run 的工具调用次数（与审批卡同源：来自同一事件流的时间线） */
  toolCallCount?: number
  /** run 已收口（已批准卡不再展示未来时的执行提示） */
  runFinished?: boolean
  onDecide: (
    approvalId: string,
    decision: AgentApprovalDecision,
    /** DESTRUCTIVE 二次确认：仅确认后带 true（后端 INT-2467 契约） */
    confirm?: boolean
  ) => Promise<string | null>
  onRetry?: () => void
}

/** 同一步骤的提案归组（step_id 缺失时按未知步骤归组） */
type ApprovalGroup = {
  key: string
  stepId?: string
  turn?: number
  items: AgentApproval[]
}

function groupApprovals(approvals: AgentApproval[]): ApprovalGroup[] {
  const groups: ApprovalGroup[] = []
  for (const approval of approvals) {
    const stepId = approval.proposal?.stepId
    const key = stepId ?? 'unknown-step'
    const existing = groups.find((group) => group.key === key)
    if (existing) {
      existing.items.push(approval)
      existing.turn = existing.turn ?? approval.proposal?.turn
    } else {
      groups.push({
        key,
        stepId,
        turn: approval.proposal?.turn,
        items: [approval],
      })
    }
  }
  return groups
}

/** 按过期时间升序（无过期时间的排后）；稳定排序保证同值不乱序 */
function sortByExpiry(items: AgentApproval[]): AgentApproval[] {
  return [...items].sort((a, b) => {
    const left = a.expiresAt ? Date.parse(a.expiresAt) : Number.MAX_SAFE_INTEGER
    const right = b.expiresAt ? Date.parse(b.expiresAt) : Number.MAX_SAFE_INTEGER
    return left - right
  })
}

export function ApprovalPanel({
  approvals,
  loading = false,
  error = null,
  decidingApprovalIds = [],
  toolCallCount = 0,
  runFinished = false,
  onDecide,
  onRetry,
}: ApprovalPanelProps) {
  const { pendingGroups, decided } = useMemo(() => {
    const pending = approvals.filter((approval) =>
      isPendingApprovalStatus(approval.status)
    )
    return {
      pendingGroups: groupApprovals(sortByExpiry(pending)),
      decided: approvals.filter(
        (approval) => !isPendingApprovalStatus(approval.status)
      ),
    }
  }, [approvals])

  const hasExpiring = useMemo(
    () =>
      approvals.some(
        (approval) =>
          isPendingApprovalStatus(approval.status) && Boolean(approval.expiresAt)
      ),
    [approvals]
  )
  const now = useNowTicker(hasExpiring)
  const pendingCount = pendingGroups.reduce(
    (total, group) =>
      total +
      group.items.filter((approval) => !isApprovalExpired(approval, now)).length,
    0
  )
  const deciding = useMemo(
    () => new Set(decidingApprovalIds),
    [decidingApprovalIds]
  )

  /**
   * 渲染一个审批块：单张卡与 INT-2472 完全一致；拆单批次先给组头再逐卡。
   * `now` 参与批次状态判定（本地倒计时到点 = 整批不执行）。
   */
  const renderBlock = (block: ApprovalPanelBlock, interactive: boolean) => {
    if (block.kind === 'single') {
      const approval = block.approval
      return (
        <ApprovalCard
          approval={approval}
          deciding={interactive && deciding.has(approval.id)}
          key={approval.id}
          onDecide={onDecide}
          runFinished={runFinished}
        />
      )
    }
    const isCancelled =
      block.state === AGENT_APPROVAL_STATUS.REJECTED ||
      block.state === AGENT_APPROVAL_STATUS.EXPIRED
    return (
      <div
        className='border-border/60 bg-muted/20 rounded-lg border p-2'
        data-approval-batch={block.batchId}
        data-approval-batch-state={block.state}
        key={`batch-${block.batchId}`}
      >
        <div
          className='text-muted-foreground mb-1.5 flex flex-wrap items-center gap-1.5 text-[11px]'
          data-approval-batch-header
        >
          {block.state === AGENT_APPROVAL_STATUS.APPROVED ? (
            <ShieldCheck className='text-muted-foreground size-3.5' />
          ) : isCancelled ? (
            <ShieldX className='text-destructive size-3.5' />
          ) : (
            <ShieldAlert className='text-warning size-3.5' />
          )}
          <span
            className={isCancelled ? 'text-destructive font-medium' : 'font-medium'}
            data-approval-batch-object-count={block.objectCount}
          >
            {formatApprovalBatchHeader(
              block.total,
              block.objectCount,
              block.state
            )}
          </span>
        </div>
        <div className='space-y-2'>
          {block.approvals.map((approval) => (
            <ApprovalCard
              approval={approval}
              batchState={block.state}
              deciding={interactive && deciding.has(approval.id)}
              key={approval.id}
              onDecide={onDecide}
              runFinished={runFinished}
            />
          ))}
        </div>
      </div>
    )
  }

  const hasContent =
    pendingGroups.length > 0 || decided.length > 0 || loading || Boolean(error)
  if (!hasContent) return null

  return (
    <section
      className='border-border/60 bg-background/70 mt-3 rounded-xl border p-3 shadow-xs'
      data-agent-approval-panel
    >
      <div className='flex flex-wrap items-center gap-2'>
        <ShieldAlert className='text-warning size-4' />
        <span className='text-sm font-semibold'>{AGENT_APPROVAL_COPY.title}</span>
        <Badge
          data-approval-pending-count={pendingCount}
          variant={pendingCount > 0 ? 'warning' : 'secondary'}
        >
          {AGENT_APPROVAL_COPY.pendingCount} {pendingCount}
        </Badge>
        <Badge data-approval-tool-count={toolCallCount} variant='outline'>
          {AGENT_APPROVAL_COPY.toolCallCount} {toolCallCount}
        </Badge>
      </div>

      {loading && (
        <div
          className='text-muted-foreground mt-2 flex items-center gap-2 text-xs'
          role='status'
        >
          <Loader />
          <span>{AGENT_APPROVAL_COPY.loading}</span>
        </div>
      )}

      {error && (
        <div
          className='text-destructive mt-2 flex flex-wrap items-center gap-2 text-xs'
          role='alert'
        >
          <span>{error}</span>
          {onRetry && (
            <Button onClick={onRetry} size='xs' type='button' variant='outline'>
              {AGENT_APPROVAL_COPY.retry}
            </Button>
          )}
        </div>
      )}

      {pendingCount === 0 && !loading && !error && (
        <p className='text-muted-foreground mt-2 text-xs'>
          {AGENT_APPROVAL_COPY.empty}
        </p>
      )}

      <div className='mt-2 space-y-3'>
        {pendingGroups.map((group) => {
          const groupStep = formatApprovalStepId(group.stepId)
          const groupTurn = formatApprovalTurn(group.turn)
          const blocks = groupApprovalBatches(group.items, now, approvals)
          return (
            <div data-approval-step={group.stepId ?? 'unknown'} key={group.key}>
              {(pendingGroups.length > 1 || group.items.length > 1) && (
                <div className='text-muted-foreground mb-1.5 flex flex-wrap items-center gap-2 text-[11px]'>
                  <span className='font-medium'>
                    {AGENT_APPROVAL_COPY.planTitle}（{group.items.length} 项）
                  </span>
                  {groupStep && <code className='font-mono'>{groupStep}</code>}
                  {groupTurn && <span>{groupTurn}</span>}
                </div>
              )}
              <div className='space-y-2'>
                {blocks.map((block) => renderBlock(block, true))}
              </div>
            </div>
          )
        })}
      </div>

      {decided.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger className='group text-muted-foreground hover:text-foreground mt-2 flex items-center gap-1 text-xs'>
            <ChevronDown className='size-3.5 transition-transform group-data-[panel-open]:rotate-180' />
            <span>
              已处理（{decided.length} 项）
            </span>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className='mt-2 space-y-2'>
              {/* 批次在折叠区同样按批聚组：整批结果（全批准 / 不执行）一眼可见 */}
              {groupApprovalBatches(decided, now, approvals).map((block) =>
                renderBlock(block, false)
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </section>
  )
}
