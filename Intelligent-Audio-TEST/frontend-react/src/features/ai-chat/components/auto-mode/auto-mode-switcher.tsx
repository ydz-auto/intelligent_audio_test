/**
 * Auto 模式切换（interfaces 层 ai-chat/auto-mode；INT-2474 §9.4）。
 *
 * 平台 Agent 通道下提供「对话 / Auto」两种运行模式：
 * - 对话（默认）：单轮问答，与既有行为完全一致；
 * - Auto：目标驱动长任务（预算约束 + 进度汇报 + 暂停继续），
 *   写操作仍逐条审批、不提供「全部自动批准」。
 * 模式随会话 config 持久化：整页与浮窗两宿主同一模式，关掉 Auto 不影响普通对话。
 */
import { Bot, MessagesSquare } from 'lucide-react'

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

const MODE_OPTIONS: Array<{
  value: AgentRunMode
  label: string
  hint: string
  icon: typeof Bot
}> = [
  {
    value: AGENT_RUN_MODE.CHAT,
    label: AGENT_AUTO_COPY.modeChat,
    hint: AGENT_AUTO_COPY.modeChatHint,
    icon: MessagesSquare,
  },
  {
    value: AGENT_RUN_MODE.AUTO,
    label: AGENT_AUTO_COPY.modeAuto,
    hint: AGENT_AUTO_COPY.modeAutoHint,
    icon: Bot,
  },
]

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
  return (
    <div
      aria-label={AGENT_AUTO_COPY.modeLabel}
      className='border-border/60 bg-background/80 flex items-center gap-0.5 rounded-md border p-0.5'
      data-agent-mode-switcher={mode}
      role='radiogroup'
    >
      {MODE_OPTIONS.map((option) => {
        const isActive = mode === option.value
        const Icon = option.icon
        return (
          <Tooltip key={option.value}>
            <TooltipTrigger
              render={
                <button
                  aria-checked={isActive}
                  className={cn(
                    'flex items-center gap-1.5 rounded px-2 py-1 text-[11px] leading-4 font-medium transition-colors',
                    isActive
                      ? 'bg-primary/12 text-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  )}
                  data-agent-mode-option={option.value}
                  disabled={disabled}
                  onClick={() => onModeChange(option.value)}
                  role='radio'
                  type='button'
                >
                  <Icon className='size-3.5 shrink-0' />
                  <span className='whitespace-nowrap'>{option.label}</span>
                </button>
              }
            />
            <TooltipContent>
              <p>{option.hint}</p>
            </TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}
