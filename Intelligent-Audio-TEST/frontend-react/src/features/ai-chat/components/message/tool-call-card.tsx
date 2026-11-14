/**
 * 工具执行卡（interfaces 层 ai-chat/message；08_AI对话页.md §3.4 照 newAPI ai-elements/tool）：
 * Collapsible 卡 + 状态徽章（等待中/执行中/已完成/失败）+ 工具中文名 + 摘要与 sourceRefs。
 */
import { Badge } from '@/components/ui/badge'
import {
  Tool,
  ToolBody,
  ToolContent,
  ToolHeader,
} from '@/components/ai-elements/tool'
import {
  AGENT_APPROVAL_COPY,
  AGENT_TOOL_LABELS,
  AGENT_TOOL_RISK,
  AGENT_TOOL_RISK_LABELS,
  type AgentApprovalStatus,
} from '@/domain/models/agent'
import type { AgentToolCall } from '@/domain/models/aiChat'

type ToolCallCardProps = {
  call: AgentToolCall
}

/** 审批状态 → 工具卡徽标（与审批面板同一份状态，计数不重复） */
const APPROVAL_BADGE: Record<
  AgentApprovalStatus,
  { label: string; variant: 'warning' | 'secondary' | 'destructive' | 'outline' }
> = {
  PENDING: { label: AGENT_APPROVAL_COPY.pending, variant: 'warning' },
  APPROVED: { label: AGENT_APPROVAL_COPY.approved, variant: 'secondary' },
  REJECTED: { label: AGENT_APPROVAL_COPY.rejected, variant: 'destructive' },
  EXPIRED: { label: AGENT_APPROVAL_COPY.expired, variant: 'outline' },
}

export function ToolCallCard({ call }: ToolCallCardProps) {
  const approvalBadge = call.approvalStatus
    ? APPROVAL_BADGE[call.approvalStatus]
    : null
  return (
    <Tool defaultOpen={call.status === 'completed'}>
      <ToolHeader status={call.status} title={AGENT_TOOL_LABELS[call.tool] ?? call.label} />
      <ToolContent>
        <ToolBody>
          {(call.risk || approvalBadge) && (
            <div className='flex flex-wrap items-center gap-1.5'>
              {call.risk && call.risk !== AGENT_TOOL_RISK.READ && (
                <Badge
                  data-tool-risk={call.risk}
                  variant={
                    call.risk === AGENT_TOOL_RISK.DESTRUCTIVE
                      ? 'destructive'
                      : 'warning'
                  }
                >
                  {AGENT_TOOL_RISK_LABELS[call.risk]}
                </Badge>
              )}
              {approvalBadge && (
                <Badge
                  data-tool-approval-status={call.approvalStatus}
                  variant={approvalBadge.variant}
                >
                  {approvalBadge.label}
                </Badge>
              )}
            </div>
          )}
          {call.summary && (
            <p className='text-foreground/90 text-xs leading-5'>{call.summary}</p>
          )}
          {call.errorCode && (
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
        </ToolBody>
      </ToolContent>
    </Tool>
  )
}
