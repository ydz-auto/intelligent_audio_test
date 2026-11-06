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
import { AGENT_TOOL_LABELS } from '@/features/ai-chat/constants'
import type { AgentToolCall } from '@/domain/models/aiChat'

type ToolCallCardProps = {
  call: AgentToolCall
}

export function ToolCallCard({ call }: ToolCallCardProps) {
  return (
    <Tool defaultOpen={call.status === 'completed'}>
      <ToolHeader status={call.status} title={AGENT_TOOL_LABELS[call.tool] ?? call.label} />
      <ToolContent>
        <ToolBody>
          {call.summary && (
            <p className='text-foreground/90 text-xs leading-5'>{call.summary}</p>
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
