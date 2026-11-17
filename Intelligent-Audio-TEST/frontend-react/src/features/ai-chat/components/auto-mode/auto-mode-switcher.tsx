/**
 * 目标模式切换（interfaces 层 ai-chat/auto-mode；INT-2474 §9.4）。
 *
 * 默认是普通对话（不显示额外模式标签）；按钮「目标模式」用于开启/关闭
 * 目标驱动长任务（预算约束 + 进度汇报 + 暂停继续），写操作仍逐条审批。
 * 模式随会话 config 持久化：整页与浮窗两宿主同一模式。
 */
import { Bot } from 'lucide-react'

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  AGENT_AUTO_COPY,
  AGENT_RUN_MODE,
  type AgentRunMode,
} from '@/domain/models/agent'
import { cn } from '@/lib/utils'

type AutoModeSwitcherProps = {
  mode: AgentRunMode
  onModeChange: (mode: AgentRunMode) => void
  disabled?: boolean
}

export function AutoModeSwitcher({
  mode,
  onModeChange,
  disabled = false,
}: AutoModeSwitcherProps) {
  const isActive = mode === AGENT_RUN_MODE.AUTO

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            aria-pressed={isActive}
            className={cn(
              'flex items-center gap-1.5 rounded px-2 py-1 text-[11px] leading-4 font-medium transition-colors',
              isActive
                ? 'bg-primary/12 text-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            )}
            data-agent-mode-switcher={mode}
            disabled={disabled}
            onClick={() =>
              onModeChange(isActive ? AGENT_RUN_MODE.CHAT : AGENT_RUN_MODE.AUTO)
            }
            type='button'
          >
            <Bot className='size-3.5 shrink-0' />
            <span className='whitespace-nowrap'>{AGENT_AUTO_COPY.modeAuto}</span>
          </button>
        }
      />
      <TooltipContent>
        <p>{AGENT_AUTO_COPY.modeAutoHint}</p>
      </TooltipContent>
    </Tooltip>
  )
}
