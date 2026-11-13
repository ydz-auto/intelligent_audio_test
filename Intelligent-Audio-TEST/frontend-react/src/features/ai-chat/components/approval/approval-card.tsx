/**
 * 写操作审批卡（interfaces 层 ai-chat/approval；方案 §12.2 / §9.4）。
 *
 * 展示：提案工具 + 风险等级（WRITE / DESTRUCTIVE）、脱敏参数、变更预览（diff）、
 * 过期倒计时；批准 / 拒绝按钮在同一张单上只发一次决策请求（store 的决策闸 +
 * 按钮禁用双重防重复）；过期后卡片失效、按钮不可再点（服务端 409 兜底）。
 *
 * 粒度（§9.4）：每张卡对应一条 tool call 提案，批准只作用于这一条 —— 计划级批量
 * 展示在审批面板里按步骤分组，但**不提供「一次批准多项」**：>20 对象 / 跨租户 /
 * 导出敏感数据 / 删除类必须单条，DESTRUCTIVE 永远单条，因此这里不做批量决策。
 */
import { useEffect, useMemo, useState } from 'react'
import { ShieldAlert, ShieldX } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Loader } from '@/components/ai-elements/loader'
import {
  AGENT_APPROVAL_COPY,
  AGENT_APPROVAL_DECISION,
  AGENT_APPROVAL_STATUS,
  AGENT_TOOL_LABELS,
  AGENT_TOOL_RISK,
  AGENT_TOOL_RISK_LABELS,
  isApprovalExpired,
  type AgentApproval,
  type AgentApprovalDecision,
  type AgentApprovalStatus,
} from '@/domain/models/agent'
import { cn } from '@/lib/utils'

import { formatClock } from '@/application/agent/agent-timeline'
import { ApprovalDiffPreview } from './diff-preview'

type ApprovalCardProps = {
  approval: AgentApproval
  /** 决策请求在途（store 中该审批单已登记，按钮立即禁用） */
  deciding: boolean
  onDecide: (
    approvalId: string,
    decision: AgentApprovalDecision
  ) => Promise<string | null>
}

const STATUS_META: Record<
  AgentApprovalStatus,
  { label: string; variant: 'warning' | 'secondary' | 'destructive' | 'outline' }
> = {
  PENDING: { label: AGENT_APPROVAL_COPY.pending, variant: 'warning' },
  APPROVED: { label: AGENT_APPROVAL_COPY.approved, variant: 'secondary' },
  REJECTED: { label: AGENT_APPROVAL_COPY.rejected, variant: 'destructive' },
  EXPIRED: { label: AGENT_APPROVAL_COPY.expired, variant: 'outline' },
}

/** 过期倒计时（mm:ss；超过 1 小时用 h:mm:ss） */
function formatRemaining(remainingMs: number): string {
  const total = Math.max(0, Math.floor(remainingMs / 1000))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(seconds)}`
    : `${pad(minutes)}:${pad(seconds)}`
}

/** 每秒刷新当前时间（仅待审批且有 expiresAt 时走定时器，静止卡片不空转） */
function useNowTicker(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    setNow(Date.now())
    const timer = setInterval(() => setNow(Date.now()), 1_000)
    return () => clearInterval(timer)
  }, [active])
  return now
}

export function ApprovalCard({
  approval,
  deciding,
  onDecide,
}: ApprovalCardProps) {
  const [error, setError] = useState<string | null>(null)
  const [pendingDecision, setPendingDecision] =
    useState<AgentApprovalDecision | null>(null)

  const status = approval.status
  const isPending = status === AGENT_APPROVAL_STATUS.PENDING
  const expiresAtMs = approval.expiresAt ? Date.parse(approval.expiresAt) : null
  const now = useNowTicker(isPending && expiresAtMs !== null)
  /** 本地倒计时到点即视为失效（服务端 409 仍是最终口径） */
  const isExpired = isApprovalExpired(approval, now)
  const effectiveStatus: AgentApprovalStatus = isExpired
    ? AGENT_APPROVAL_STATUS.EXPIRED
    : status
  const meta = STATUS_META[effectiveStatus]
  const actionDisabled = !isPending || isExpired || deciding

  const tool = approval.proposal?.tool
  const risk = approval.proposal?.risk
  const toolLabel = tool ? (AGENT_TOOL_LABELS[tool] ?? tool) : '写操作'
  const isDestructive = risk === AGENT_TOOL_RISK.DESTRUCTIVE

  const remainingText = useMemo(() => {
    if (!isPending || expiresAtMs === null || isExpired) return null
    return formatRemaining(expiresAtMs - now)
  }, [isPending, expiresAtMs, isExpired, now])

  const runDecision = async (decision: AgentApprovalDecision) => {
    if (actionDisabled) return
    setError(null)
    setPendingDecision(decision)
    const failure = await onDecide(approval.id, decision)
    setPendingDecision(null)
    if (failure) setError(failure)
  }

  return (
    <div
      className={cn(
        'rounded-lg border p-3',
        effectiveStatus === AGENT_APPROVAL_STATUS.PENDING
          ? isDestructive
            ? 'border-destructive/40 bg-destructive/5'
            : 'border-warning/40 bg-warning/5'
          : 'border-border/60 bg-muted/20'
      )}
      data-approval-id={approval.id}
      data-approval-status={effectiveStatus}
      data-approval-risk={risk ?? ''}
    >
      <div className='flex flex-wrap items-center gap-2'>
        {isDestructive ? (
          <ShieldX className='text-destructive size-4' />
        ) : (
          <ShieldAlert className='text-warning size-4' />
        )}
        <span className='text-sm font-medium'>{AGENT_APPROVAL_COPY.title}</span>
        {risk && (
          <Badge
            variant={isDestructive ? 'destructive' : 'warning'}
            data-approval-risk-badge={risk}
          >
            {AGENT_TOOL_RISK_LABELS[risk]}
          </Badge>
        )}
        <Badge variant={meta.variant} data-approval-status-badge={effectiveStatus}>
          {meta.label}
        </Badge>
        <span className='text-muted-foreground ml-auto text-xs'>{toolLabel}</span>
      </div>

      <div className='text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]'>
        {tool && <code className='font-mono'>{tool}</code>}
        {approval.proposal?.stepId && (
          <span>步骤 {approval.proposal.stepId}</span>
        )}
        {approval.proposal?.turn !== undefined && (
          <span>第 {approval.proposal.turn} 轮</span>
        )}
        {isPending && expiresAtMs !== null && (
          <span data-approval-countdown>
            {isExpired
              ? AGENT_APPROVAL_COPY.expiredHint
              : `${AGENT_APPROVAL_COPY.expiresIn} ${remainingText} · ${AGENT_APPROVAL_COPY.expiresAt} ${formatClock(approval.expiresAt)}`}
          </span>
        )}
        {!isPending && approval.decidedAt && (
          <span data-approval-decided>
            {AGENT_APPROVAL_COPY.decidedBy} {approval.decidedBy ?? '-'} ·{' '}
            {AGENT_APPROVAL_COPY.decidedAt} {formatClock(approval.decidedAt)}
          </span>
        )}
      </div>

      <div className='mt-2 space-y-2'>
        <ApprovalDiffPreview
          argumentsValue={approval.proposal?.arguments}
          diff={approval.diff}
        />
      </div>

      {error && (
        <p className='text-destructive mt-2 text-xs' role='alert'>
          {error}
        </p>
      )}

      {isPending && (
        <div className='mt-3 flex flex-wrap items-center gap-2'>
          <Button
            disabled={actionDisabled}
            onClick={() => void runDecision(AGENT_APPROVAL_DECISION.APPROVE)}
            size='sm'
            type='button'
            variant='default'
          >
            {deciding && pendingDecision === AGENT_APPROVAL_DECISION.APPROVE ? (
              <>
                <Loader />
                {AGENT_APPROVAL_COPY.approving}
              </>
            ) : (
              AGENT_APPROVAL_COPY.approve
            )}
          </Button>
          <Button
            disabled={actionDisabled}
            onClick={() => void runDecision(AGENT_APPROVAL_DECISION.REJECT)}
            size='sm'
            type='button'
            variant='outline'
          >
            {deciding && pendingDecision === AGENT_APPROVAL_DECISION.REJECT ? (
              <>
                <Loader />
                {AGENT_APPROVAL_COPY.rejecting}
              </>
            ) : (
              AGENT_APPROVAL_COPY.reject
            )}
          </Button>
          {isExpired && (
            <span className='text-destructive text-xs'>
              {AGENT_APPROVAL_COPY.expiredHint}
            </span>
          )}
        </div>
      )}

      {!isPending && effectiveStatus === AGENT_APPROVAL_STATUS.APPROVED && (
        <p className='text-muted-foreground mt-2 text-xs'>
          {AGENT_APPROVAL_COPY.approvedHint}
        </p>
      )}
      {!isPending && effectiveStatus === AGENT_APPROVAL_STATUS.REJECTED && (
        <p className='text-muted-foreground mt-2 text-xs'>
          {AGENT_APPROVAL_COPY.rejectedHint}
        </p>
      )}
    </div>
  )
}
