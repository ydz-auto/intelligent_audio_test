/**
 * 工具调用行（interfaces 层 ai-chat/message；参照 Trae / Codex 的过程折叠行）：
 * 单行「状态图标 + 工具名 + 状态」，点开才看摘要、风险、审批、来源与错误码。
 * 外层由「思考过程」（thinking-process）统一收口，不再为每次工具调用铺整宽边框卡。
 */
import {
  CheckCircle2,
  ChevronDown,
  Circle,
  Loader2,
  XCircle,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  AGENT_APPROVAL_COPY,
  AGENT_TOOL_LABELS,
  AGENT_TOOL_RISK,
  AGENT_TOOL_RISK_LABELS,
  type AgentApprovalStatus,
} from '@/domain/models/agent'
import type { AgentToolCall, AgentToolStatus } from '@/domain/models/aiChat'
import { AGENT_TOOL_STATUS_LABELS } from '@/features/ai-chat/constants'
import { cn } from '@/lib/utils'

type ToolCallCardProps = {
  call: AgentToolCall
}

/** 审批状态 → 工具行徽标（与审批面板同一份状态，计数不重复） */
const APPROVAL_BADGE: Record<
  AgentApprovalStatus,
  { label: string; variant: 'warning' | 'secondary' | 'destructive' | 'outline' }
> = {
  PENDING: { label: AGENT_APPROVAL_COPY.pending, variant: 'warning' },
  APPROVED: { label: AGENT_APPROVAL_COPY.approved, variant: 'secondary' },
  REJECTED: { label: AGENT_APPROVAL_COPY.rejected, variant: 'destructive' },
  EXPIRED: { label: AGENT_APPROVAL_COPY.expired, variant: 'outline' },
}

/** 工具状态 → 图标与配色（只用语义 token，不发明颜色） */
const STATUS_META: Record<
  AgentToolStatus,
  { icon: ReactNode; colorClass: string }
> = {
  pending: {
    icon: <Circle className='size-3.5' />,
    colorClass: 'text-muted-foreground/60',
  },
  running: {
    icon: <Loader2 className='size-3.5 animate-spin' />,
    colorClass: 'text-primary',
  },
  completed: {
    icon: <CheckCircle2 className='size-3.5' />,
    colorClass: 'text-success',
  },
  error: {
    icon: <XCircle className='size-3.5' />,
    colorClass: 'text-destructive',
  },
}

const BADGE_CLASS = 'h-4 px-1.5 text-[10px] leading-none'

export function ToolCallCard({ call }: ToolCallCardProps) {
  const statusMeta = STATUS_META[call.status]
  const approvalBadge = call.approvalStatus
    ? APPROVAL_BADGE[call.approvalStatus]
    : null
  const showRisk = Boolean(call.risk) && call.risk !== AGENT_TOOL_RISK.READ
  const hasDetail = Boolean(
    call.summary ||
      call.errorCode ||
      (call.sourceRefs && call.sourceRefs.length > 0) ||
      showRisk ||
      approvalBadge
  )

  return (
    <Collapsible className='group/tool'>
      <CollapsibleTrigger
        className={cn(
          'flex w-full min-w-0 items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-xs',
          'transition-colors hover:bg-muted/50',
          hasDetail ? 'cursor-pointer' : 'cursor-default'
        )}
      >
        <span className={cn('shrink-0', statusMeta.colorClass)} aria-hidden='true'>
          {statusMeta.icon}
        </span>
        <span className='shrink-0 font-medium text-foreground/85'>
          {AGENT_TOOL_LABELS[call.tool] ?? call.label}
        </span>
        <span className='shrink-0 text-muted-foreground'>
          {AGENT_TOOL_STATUS_LABELS[call.status]}
        </span>
        {showRisk && call.risk && (
          <Badge
            className={BADGE_CLASS}
            data-tool-risk={call.risk}
            variant={
              call.risk === AGENT_TOOL_RISK.DESTRUCTIVE ? 'destructive' : 'warning'
            }
          >
            {AGENT_TOOL_RISK_LABELS[call.risk]}
          </Badge>
        )}
        {approvalBadge && (
          <Badge
            className={BADGE_CLASS}
            data-tool-approval-status={call.approvalStatus}
            variant={approvalBadge.variant}
          >
            {approvalBadge.label}
          </Badge>
        )}
        <ChevronDown
          className={cn(
            'ml-auto size-3 shrink-0 text-muted-foreground/40 transition-transform',
            'group-data-[panel-open]/tool:rotate-180'
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent className='text-muted-foreground mt-0.5 mb-1 space-y-1.5 pl-6 pr-1.5 text-xs leading-5 outline-none'>
        {call.summary && (
          <p className='text-foreground/80 break-words'>{call.summary}</p>
        )}
        {/* 错误码只在失败时展示：成功结果的状态码（如 'OK'）不是错误，不能标红 */}
        {call.status === 'error' && call.errorCode && (
          <p className='text-destructive font-mono text-[11px] leading-5'>
            错误码：{call.errorCode}
          </p>
        )}
        {call.sourceRefs && call.sourceRefs.length > 0 && (
          <div className='flex flex-wrap gap-1.5'>
            {call.sourceRefs.map((ref, index) => (
              <Badge
                className='font-mono text-[10px]'
                key={`${ref.reportId}-${ref.metricId}-${index}`}
                variant='outline'
              >
                报告 {ref.reportId}
                {ref.metricId ? ` · ${ref.metricId}` : ''}
                {ref.dataVersion ? ` · ${ref.dataVersion}` : ''}
              </Badge>
            ))}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
