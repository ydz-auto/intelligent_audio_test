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
 *
 * 二次确认（INT-2467 / §9.4）：
 * - DESTRUCTIVE 的批准必须先过二次确认弹窗，确认后请求体带 `confirm=true`
 *   （后端 `ApprovalDecisionRequest.confirm`，缺失返回 400 且不落决策）；
 * - 单次影响 >20 对象的提案（§9.4）强制逐项核对：每个对象单独勾选，
 *   全部核对完才能批准，不允许一次批量放行。
 */
import { useEffect, useMemo, useState } from 'react'
import { ShieldAlert, ShieldX } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { ConfirmDialog } from '@/components/confirm-dialog'
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
import {
  formatApprovalApprover,
  formatApprovalStepId,
  formatApprovalTurn,
  summarizeApprovalTargets,
} from '@/features/ai-chat/lib/approval'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import { ApprovalDiffPreview } from './diff-preview'

type ApprovalCardProps = {
  approval: AgentApproval
  /** 决策请求在途（store 中该审批单已登记，按钮立即禁用） */
  deciding: boolean
  /** run 已收口：已批准卡不再用「将在服务端执行」的将来时（P3-5） */
  runFinished?: boolean
  onDecide: (
    approvalId: string,
    decision: AgentApprovalDecision,
    /** DESTRUCTIVE 二次确认：仅确认后带 true（后端 INT-2467 契约） */
    confirm?: boolean
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
  runFinished = false,
  onDecide,
}: ApprovalCardProps) {
  const [error, setError] = useState<string | null>(null)
  const [pendingDecision, setPendingDecision] =
    useState<AgentApprovalDecision | null>(null)
  /** 二次确认弹窗（DESTRUCTIVE / >20 对象逐项核对 / 服务端要求补确认） */
  const [confirmOpen, setConfirmOpen] = useState(false)
  /** 服务端 400 要求补 confirm（提案没记录风险 / 风险表更新）：弹窗补确认后重发 */
  const [serverConfirmRequired, setServerConfirmRequired] = useState(false)
  /** >20 对象逐项核对的勾选状态（下标集合，允许重复 id 各自确认） */
  const [checkedTargets, setCheckedTargets] = useState<Set<number>>(
    () => new Set()
  )
  /** 当前用户 id：决策人是自己时展示「我」，不直出内部数字 id（P3-4） */
  const currentUserId = useAuthStore((state) => state.user?.id)

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
  const stepText = formatApprovalStepId(approval.proposal?.stepId)
  const turnText = formatApprovalTurn(approval.proposal?.turn)
  const approverText = formatApprovalApprover(approval.decidedBy, currentUserId)

  /** §9.4 粒度：提案影响的对象数与是否超过单次审批上限（>20） */
  const targets = useMemo(
    () => summarizeApprovalTargets(approval),
    [approval]
  )
  /** 风险未知时按高危处理（不把未知风险降级成 WRITE 直接放行） */
  const needsConfirm = isDestructive || risk === undefined
  const requiresManualConfirm =
    needsConfirm || targets.overLimit || serverConfirmRequired
  const allTargetsChecked =
    !targets.overLimit || checkedTargets.size === targets.targets.length

  const remainingText = useMemo(() => {
    if (!isPending || expiresAtMs === null || isExpired) return null
    return formatRemaining(expiresAtMs - now)
  }, [isPending, expiresAtMs, isExpired, now])

  const runDecision = async (
    decision: AgentApprovalDecision,
    confirm = false
  ) => {
    if (actionDisabled) return
    setError(null)
    setPendingDecision(decision)
    // 只有二次确认过的批准才把 confirm 传给后端（WRITE / REJECT 不带该字段）
    const failure = confirm
      ? await onDecide(approval.id, decision, true)
      : await onDecide(approval.id, decision)
    setPendingDecision(null)
    if (failure) {
      setError(failure)
      // 服务端要求二次确认（提案没记录风险 / 风险表更新）：补开确认弹窗重发
      if (failure === AGENT_APPROVAL_COPY.confirmRequired) {
        setServerConfirmRequired(true)
        setConfirmOpen(true)
      }
    }
  }

  const handleApproveClick = () => {
    if (actionDisabled) return
    if (requiresManualConfirm) {
      setCheckedTargets(new Set())
      setConfirmOpen(true)
      return
    }
    void runDecision(AGENT_APPROVAL_DECISION.APPROVE)
  }

  const handleDialogConfirm = () => {
    setConfirmOpen(false)
    // DESTRUCTIVE / 风险未知 / 服务端补确认的批准带 confirm=true；
    // 仅 >20 对象的 WRITE 批量逐项核对本身不需要 confirm。
    void runDecision(
      AGENT_APPROVAL_DECISION.APPROVE,
      needsConfirm || serverConfirmRequired
    )
  }

  const toggleTarget = (index: number) => {
    setCheckedTargets((previous) => {
      const next = new Set(previous)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  useEffect(() => {
    // 审批单变了（重连恢复换卡）就清空逐项核对状态，避免串单
    setCheckedTargets(new Set())
    setConfirmOpen(false)
    setServerConfirmRequired(false)
    setError(null)
  }, [approval.id])

  const confirmTitle = isDestructive
    ? AGENT_APPROVAL_COPY.destructiveConfirmTitle
    : targets.overLimit
      ? AGENT_APPROVAL_COPY.batchConfirmTitle
      : AGENT_APPROVAL_COPY.confirmTitle

  const confirmDesc = (
    <span className='space-y-1.5'>
      <span className='block'>
        {isDestructive
          ? AGENT_APPROVAL_COPY.destructiveConfirmDesc
          : targets.overLimit
            ? `${AGENT_APPROVAL_COPY.batchConfirmPrefix} ${targets.count} ${AGENT_APPROVAL_COPY.batchConfirmSuffix}`
            : serverConfirmRequired
              ? AGENT_APPROVAL_COPY.confirmRequired
              : AGENT_APPROVAL_COPY.unknownRiskConfirmDesc}
      </span>
      <span className='text-muted-foreground block text-xs'>
        <code className='font-mono'>{tool ?? '-'}</code>
        {stepText && ` · 步骤 ${stepText}`}
        {turnText && ` · ${turnText}`}
      </span>
      {targets.overLimit && (
        <span
          className='text-muted-foreground block text-xs'
          data-approval-target-count={targets.count}
        >
          {AGENT_APPROVAL_COPY.batchObjectCount}{' '}
          {checkedTargets.size}/{targets.targets.length}
          {targets.count > targets.targets.length &&
            `（仅展示前 ${targets.targets.length} 个）`}
        </span>
      )}
    </span>
  )

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
        {targets.count > 0 && (
          <Badge
            data-approval-object-count={targets.count}
            variant={targets.overLimit ? 'destructive' : 'outline'}
          >
            {AGENT_APPROVAL_COPY.batchObjects} {targets.count}
          </Badge>
        )}
        <span className='text-muted-foreground ml-auto text-xs'>{toolLabel}</span>
      </div>

      <div className='text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]'>
        {tool && <code className='font-mono'>{tool}</code>}
        {stepText && <span>步骤 {stepText}</span>}
        {turnText && <span>{turnText}</span>}
        {targets.overLimit && (
          <span className='text-destructive' data-approval-batch-hint>
            {AGENT_APPROVAL_COPY.batchLimitHint}
          </span>
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
            {AGENT_APPROVAL_COPY.decidedBy} {approverText ?? '-'} ·{' '}
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
            onClick={handleApproveClick}
            size='sm'
            type='button'
            variant={isDestructive ? 'destructive' : 'default'}
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

      {isPending && requiresManualConfirm && (
        <ConfirmDialog
          confirmText={
            targets.overLimit && !needsConfirm
              ? AGENT_APPROVAL_COPY.batchConfirmApprove
              : AGENT_APPROVAL_COPY.confirmApprove
          }
          desc={confirmDesc}
          destructive={isDestructive}
          disabled={!allTargetsChecked || actionDisabled}
          handleConfirm={handleDialogConfirm}
          isLoading={deciding}
          onOpenChange={setConfirmOpen}
          open={confirmOpen}
          title={confirmTitle}
        >
          {targets.overLimit && (
            <div
              className='max-h-56 space-y-1 overflow-y-auto rounded-md border p-2'
              data-approval-target-list
            >
              {targets.targets.map((target, index) => (
                <label
                  className='hover:bg-muted/60 flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs'
                  data-approval-target={target}
                  key={`${target}-${index}`}
                >
                  <Checkbox
                    checked={checkedTargets.has(index)}
                    onCheckedChange={() => toggleTarget(index)}
                  />
                  <span className='font-mono'>{target}</span>
                </label>
              ))}
            </div>
          )}
        </ConfirmDialog>
      )}

      {!isPending &&
        !runFinished &&
        effectiveStatus === AGENT_APPROVAL_STATUS.APPROVED && (
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
