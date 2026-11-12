/**
 * 对话通道切换器（interfaces 层 ai-chat/input；INT-2457 §12.2 双通道过渡）。
 * 位置：紧邻模型/供应商切换器（同一工具行），默认值来自配置（DEFAULT_CHAT_CHANNEL）。
 * 平台 Agent 为默认通道；自带供应商直连为降级模式，P0-1 拍板后二选一，不长期双轨。
 */
import { Bot, PlugZap } from 'lucide-react'

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { CHAT_CHANNEL, type ChatChannel } from '@/domain/models/aiChat'
import { CHAT_CHANNEL_COPY } from '@/features/ai-chat/constants'
import { cn } from '@/lib/utils'

const CHANNEL_OPTIONS: Array<{
  value: ChatChannel
  label: string
  hint: string
  icon: typeof Bot
}> = [
  {
    value: CHAT_CHANNEL.PLATFORM,
    label: CHAT_CHANNEL_COPY.platform,
    hint: CHAT_CHANNEL_COPY.platformHint,
    icon: Bot,
  },
  {
    value: CHAT_CHANNEL.PROVIDER,
    label: CHAT_CHANNEL_COPY.provider,
    hint: CHAT_CHANNEL_COPY.providerHint,
    icon: PlugZap,
  },
]

type ChatChannelSwitcherProps = {
  channel: ChatChannel
  onChannelChange: (channel: ChatChannel) => void
  disabled?: boolean
}

export function ChatChannelSwitcher({
  channel,
  onChannelChange,
  disabled = false,
}: ChatChannelSwitcherProps) {
  return (
    <div
      aria-label={CHAT_CHANNEL_COPY.label}
      className='border-border/60 bg-background/80 flex items-center gap-0.5 rounded-md border p-0.5'
      role='radiogroup'
    >
      {CHANNEL_OPTIONS.map((option) => {
        const isActive = channel === option.value
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
                  disabled={disabled}
                  onClick={() => onChannelChange(option.value)}
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
