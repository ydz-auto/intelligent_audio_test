/**
 * 思考 / 执行过程折叠（interfaces 层 ai-chat/message；参照 Trae / Codex 的过程摘要行）。
 *
 * 平台 Agent 一轮会连续调用多次工具，逐个铺整宽卡片会把正文挤到屏幕外（阅读负担重）。
 * 这里把「思考正文 + 工具调用」统一收进一条灰字摘要行：
 * - 进行中：Shimmer「正在思考」+ 已调用次数，自动展开；
 * - 结束后：收成一行「思考了 N 秒 · 调用 N 个工具」，默认折叠；
 * - 用户点开才看思考正文与逐条工具明细（tool-call-card）。
 */
import { Brain, ChevronDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Response } from '@/components/ai-elements/response'
import { Shimmer } from '@/components/ai-elements/shimmer'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import type { AgentToolCall } from '@/domain/models/aiChat'
import { THINKING_PROCESS_COPY } from '@/features/ai-chat/constants'

import { ToolCallCard } from './tool-call-card'

type ThinkingProcessProps = {
  /** 思考正文（平台通道当前不下发推理内容，可为空） */
  reasoning: string
  /** 思考正文仍在流式输出 */
  isReasoningStreaming: boolean
  /** 思考耗时（秒；无思考正文时不展示） */
  durationSeconds: number
  toolCalls: readonly AgentToolCall[]
}

/** 仍在推进的工具状态（决定摘要行是否显示「正在思考」） */
const ACTIVE_TOOL_STATUSES: ReadonlySet<AgentToolCall['status']> = new Set([
  'pending',
  'running',
])

function fillCopy(template: string, key: string, value: number): string {
  return template.replace(`{${key}}`, String(value))
}

export function ThinkingProcess(props: ThinkingProcessProps) {
  const hasReasoning = props.reasoning.trim() !== ''
  const toolCount = props.toolCalls.length
  const isToolActive = props.toolCalls.some((call) =>
    ACTIVE_TOOL_STATUSES.has(call.status)
  )
  const isActive = props.isReasoningStreaming || isToolActive

  // 进行中自动展开、结束自动收起；用户手动展开的意图在结束后让位于「收成一行」
  const [isOpen, setIsOpen] = useState(isActive)
  const wasActiveRef = useRef(isActive)
  useEffect(() => {
    if (isActive) setIsOpen(true)
    else if (wasActiveRef.current) setIsOpen(false)
    wasActiveRef.current = isActive
  }, [isActive])

  const doneSummary = hasReasoning
    ? fillCopy(
        THINKING_PROCESS_COPY.thought,
        'seconds',
        Math.max(0, Math.round(props.durationSeconds))
      )
    : THINKING_PROCESS_COPY.toolOnly

  return (
    <Collapsible
      className='not-prose mb-2 w-full'
      onOpenChange={setIsOpen}
      open={isOpen}
    >
      <CollapsibleTrigger
        className='group flex w-fit max-w-full items-center gap-1.5 rounded-md py-1 pr-1 text-xs text-muted-foreground transition-colors hover:text-foreground'
        data-thinking-active={isActive}
      >
        <Brain className='size-3.5 shrink-0' aria-hidden='true' />
        {isActive ? (
          <Shimmer duration={1.4}>{THINKING_PROCESS_COPY.thinking}</Shimmer>
        ) : (
          <span>{doneSummary}</span>
        )}
        {toolCount > 0 && (
          <span className='shrink-0 text-muted-foreground/80'>
            · {fillCopy(THINKING_PROCESS_COPY.toolCount, 'count', toolCount)}
          </span>
        )}
        <ChevronDown
          className='size-3 shrink-0 text-muted-foreground/50 transition-transform group-data-[panel-open]:rotate-180'
          aria-hidden='true'
        />
      </CollapsibleTrigger>
      <CollapsibleContent className='mt-1 outline-none'>
        {hasReasoning && (
          <Response
            className='border-border/60 mt-0.5 mb-1.5 ml-1.5 border-l pl-3'
            compact
          >
            {props.reasoning}
          </Response>
        )}
        {toolCount > 0 && (
          <div className='divide-border/50 divide-y'>
            {props.toolCalls.map((call) => (
              <ToolCallCard call={call} key={call.id} />
            ))}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
