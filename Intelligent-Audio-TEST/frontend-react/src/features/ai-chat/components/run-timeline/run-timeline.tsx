/**
 * Run 时间线（interfaces 层 ai-chat/run-timeline；方案 §12.2 / 拍板增补 3）。
 *
 * 事件顺序即后端 SSE 的 `sequence`（application/agent/agent-timeline 归约）：
 * run_started → message_delta（聚合）→ tool_call / tool_result →
 * approval_required（决策人与时间回填）→ context_compacted（调试标记）→ run_finished。
 * 头部展示本次 run 的预算上限与已消耗 token，便于还原一次运行的执行过程。
 *
 * 默认折叠：时间线是审计 / 排障视图，不抢占对话正文的可视空间。
 */
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Flag,
  Layers,
  MessageSquare,
  Play,
  ShieldAlert,
  Wrench,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'

import {
  AGENT_APPROVAL_COPY,
  AGENT_APPROVAL_STATUS,
  AGENT_RUN_STATUS,
  AGENT_TOOL_RESULT_STATUS,
  AGENT_TOOL_RISK_LABELS,
  type AgentApprovalStatus,
  type AgentRun,
  type AgentRunBudget,
  type AgentToolRisk,
} from '@/domain/models/agent'
import {
  formatClock,
  AGENT_TIMELINE_KIND,
  type AgentTimelineEntry,
  type AgentTimelineKind,
} from '@/application/agent/agent-timeline'
import { cn } from '@/lib/utils'

/** 时间线条目图标（按类型；错误 / 审批用语义色） */
const KIND_META: Record<
  AgentTimelineKind,
  { icon: typeof Play; className: string }
> = {
  run_started: { icon: Play, className: 'text-muted-foreground' },
  message: { icon: MessageSquare, className: 'text-muted-foreground' },
  tool_call: { icon: Wrench, className: 'text-foreground/70' },
  tool_result: { icon: CheckCircle2, className: 'text-muted-foreground' },
  approval: { icon: ShieldAlert, className: 'text-warning' },
  context_compacted: { icon: Layers, className: 'text-muted-foreground' },
  run_finished: { icon: Flag, className: 'text-muted-foreground' },
  error: { icon: AlertTriangle, className: 'text-destructive' },
}

const APPROVAL_STATUS_LABELS: Record<AgentApprovalStatus, string> = {
  PENDING: AGENT_APPROVAL_COPY.pending,
  APPROVED: AGENT_APPROVAL_COPY.approved,
  REJECTED: AGENT_APPROVAL_COPY.rejected,
  EXPIRED: AGENT_APPROVAL_COPY.expired,
}

/** 预算上限摘要（§9.3；limit<=0 表示该维度未启用） */
function budgetText(budget: AgentRunBudget | undefined): string[] {
  if (!budget) return []
  const parts: string[] = []
  if (budget.maxRounds && budget.maxRounds > 0) {
    parts.push(`轮次 ≤ ${budget.maxRounds}`)
  }
  if (budget.maxToolCalls && budget.maxToolCalls > 0) {
    parts.push(`工具 ≤ ${budget.maxToolCalls}`)
  }
  if (budget.maxTokens && budget.maxTokens > 0) {
    parts.push(`token ≤ ${budget.maxTokens}`)
  }
  if (budget.maxDurationSeconds && budget.maxDurationSeconds > 0) {
    parts.push(`时长 ≤ ${Math.round(budget.maxDurationSeconds / 60)} 分钟`)
  }
  return parts
}

function tokenUsageText(run: AgentRun | null | undefined): string | null {
  if (!run) return null
  const tokenIn = run.tokenIn ?? 0
  const tokenOut = run.tokenOut ?? 0
  if (tokenIn === 0 && tokenOut === 0) return null
  return `token ${tokenIn + tokenOut}（入 ${tokenIn} / 出 ${tokenOut}）`
}

function entryStatusBadge(
  entry: AgentTimelineEntry
): { label: string; variant: 'secondary' | 'destructive' | 'outline' | 'warning' } | null {
  if (entry.kind === AGENT_TIMELINE_KIND.APPROVAL) {
    const status = entry.status as AgentApprovalStatus | undefined
    if (!status || !(status in APPROVAL_STATUS_LABELS)) return null
    return {
      label: APPROVAL_STATUS_LABELS[status],
      variant:
        status === AGENT_APPROVAL_STATUS.PENDING
          ? 'warning'
          : status === AGENT_APPROVAL_STATUS.REJECTED
            ? 'destructive'
            : 'secondary',
    }
  }
  if (entry.kind === AGENT_TIMELINE_KIND.TOOL_RESULT) {
    const failed =
      entry.status === AGENT_TOOL_RESULT_STATUS.FAILED ||
      entry.status === AGENT_TOOL_RESULT_STATUS.CANCELLED
    return { label: entry.status ?? '', variant: failed ? 'destructive' : 'secondary' }
  }
  if (entry.kind === AGENT_TIMELINE_KIND.ERROR) {
    return { label: entry.label, variant: 'destructive' }
  }
  if (entry.kind === AGENT_TIMELINE_KIND.RUN_FINISHED) {
    const failed =
      entry.status === AGENT_RUN_STATUS.FAILED ||
      entry.status === AGENT_RUN_STATUS.BUDGET_EXCEEDED
    return { label: entry.label, variant: failed ? 'destructive' : 'secondary' }
  }
  return null
}

function TimelineEntry({ entry }: { entry: AgentTimelineEntry }) {
  const meta = KIND_META[entry.kind]
  const Icon = meta.icon
  const statusBadge = entryStatusBadge(entry)
  const risk = entry.risk as AgentToolRisk | undefined
  const sequenceText =
    entry.lastSequence !== entry.sequence
      ? `#${entry.sequence}–${entry.lastSequence}`
      : `#${entry.sequence}`

  return (
    <li
      className='flex items-start gap-2 py-1'
      data-timeline-kind={entry.kind}
      data-timeline-sequence={entry.sequence}
      data-timeline-last-sequence={entry.lastSequence}
    >
      <Icon className={cn('mt-0.5 size-3.5 shrink-0', meta.className)} />
      <span className='text-muted-foreground w-10 shrink-0 font-mono text-[10px] leading-5'>
        {sequenceText}
      </span>
      <span className='text-muted-foreground w-16 shrink-0 font-mono text-[10px] leading-5'>
        {formatClock(entry.at)}
      </span>
      <div className='min-w-0 flex-1'>
        <div className='flex flex-wrap items-center gap-1.5'>
          <span className='text-xs leading-5'>{entry.label}</span>
          {risk && (
            <Badge variant='outline'>{AGENT_TOOL_RISK_LABELS[risk]}</Badge>
          )}
          {statusBadge && (
            <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
          )}
          {entry.kind === AGENT_TIMELINE_KIND.CONTEXT_COMPACTED && entry.debug && (
            <Badge data-timeline-debug='true' variant='outline'>
              调试
            </Badge>
          )}
        </div>
        {entry.detail && (
          <p className='text-muted-foreground text-[11px] leading-5 break-words'>
            {entry.detail}
          </p>
        )}
      </div>
    </li>
  )
}

type RunTimelineProps = {
  entries: AgentTimelineEntry[]
  run?: AgentRun | null
}

export function RunTimeline({ entries, run }: RunTimelineProps) {
  if (entries.length === 0) return null
  const budget = budgetText(run?.budget)
  const tokens = tokenUsageText(run)

  return (
    <Collapsible>
      <section
        className='border-border/60 bg-muted/20 mt-3 rounded-xl border px-3 py-2'
        data-agent-run-timeline
      >
        <CollapsibleTrigger className='group flex w-full items-center gap-2 text-left'>
          <ChevronDown className='text-muted-foreground size-3.5 transition-transform group-data-[panel-open]:rotate-180' />
          <span className='text-xs font-medium'>运行时间线</span>
          <Badge variant='outline'>{entries.length} 个事件</Badge>
          {tokens && (
            <span className='text-muted-foreground text-[11px]'>{tokens}</span>
          )}
        </CollapsibleTrigger>
        <CollapsibleContent>
          {budget.length > 0 && (
            <div
              className='text-muted-foreground mt-2 flex flex-wrap items-center gap-1.5 text-[11px]'
              data-timeline-budget
            >
              <span>预算</span>
              {budget.map((item) => (
                <Badge key={item} variant='outline'>
                  {item}
                </Badge>
              ))}
            </div>
          )}
          <ol className='mt-1 divide-y divide-border/40'>
            {entries.map((entry) => (
              <TimelineEntry entry={entry} key={`${entry.kind}-${entry.sequence}`} />
            ))}
          </ol>
        </CollapsibleContent>
      </section>
    </Collapsible>
  )
}
