/**
 * 输入区工具行（interfaces 层 ai-chat/input；08_AI对话页.md §3.5）：
 * 模型/供应商切换器 + 清空对话（Trash2 + ConfirmDialog destructive + toast「对话已清空」）；
 * 附件/搜索钮不引入（§2.2 Agent 域无对位能力）；参数面板整块移除
 * （2026-10-17 负责人口径：仅允许切换模型与供应商）。
 */
import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { PromptInputButton, PromptInputTools } from '@/components/ai-elements/prompt-input'
import { Badge } from '@/components/ui/badge'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

import { CHAT_CHANNEL, type ChatChannel, type ChatConfig, type LlmProvider } from '@/domain/models/aiChat'
import { CHAT_CHANNEL_COPY } from '@/features/ai-chat/constants'
import { ChatChannelSwitcher } from './chat-channel-switcher'
import { ModelProviderSwitcher } from './model-provider-switcher'

type AiChatInputToolsProps = {
  config: ChatConfig
  providers: LlmProvider[]
  /** 对话通道（平台 Agent / 自带供应商，INT-2457） */
  channel: ChatChannel
  onChannelChange?: (channel: ChatChannel) => void
  disabled?: boolean
  hasMessages?: boolean
  onClearMessages?: () => void
  onSelectProvider: (providerId: string) => void
  onSelectModel: (providerId: string, modelId: string) => void
  onManageProviders: () => void
}

export function AiChatInputTools({
  config,
  providers,
  channel,
  onChannelChange,
  disabled,
  hasMessages = false,
  onClearMessages,
  onSelectProvider,
  onSelectModel,
  onManageProviders,
}: AiChatInputToolsProps) {
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false)

  const handleClearMessages = () => {
    onClearMessages?.()
    setClearConfirmOpen(false)
    toast.success('对话已清空')
  }

  return (
    <>
      <PromptInputTools className='bg-background/70 border-border/60 rounded-lg border p-1 shadow-xs'>
        {onChannelChange && (
          <ChatChannelSwitcher
            channel={channel}
            disabled={disabled}
            onChannelChange={onChannelChange}
          />
        )}

        {channel === CHAT_CHANNEL.PLATFORM ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <Badge className='text-muted-foreground' variant='secondary'>
                  {CHAT_CHANNEL_COPY.platformModelBadge}
                </Badge>
              }
            />
            <TooltipContent>
              <p>{CHAT_CHANNEL_COPY.platformHint}</p>
            </TooltipContent>
          </Tooltip>
        ) : (
          <ModelProviderSwitcher
            className='bg-transparent shadow-none'
            config={config}
            disabled={disabled}
            onManageProviders={onManageProviders}
            onSelectModel={onSelectModel}
            onSelectProvider={onSelectProvider}
            providers={providers}
          />
        )}

        <Tooltip>
          <TooltipTrigger
            render={
              <PromptInputButton
                aria-label='清空对话'
                className='text-muted-foreground hover:text-destructive hover:bg-destructive/10 font-medium'
                disabled={disabled || !hasMessages || !onClearMessages}
                onClick={() => setClearConfirmOpen(true)}
                variant='ghost'
              >
                <Trash2 className='size-4' />
              </PromptInputButton>
            }
          />
          <TooltipContent>
            <p>清空对话</p>
          </TooltipContent>
        </Tooltip>
      </PromptInputTools>

      <ConfirmDialog
        destructive
        confirmText='清空'
        desc='本地保存的对话记录将被移除，此操作无法撤销。'
        handleConfirm={handleClearMessages}
        onOpenChange={setClearConfirmOpen}
        open={clearConfirmOpen}
        title='清空对话？'
      />
    </>
  )
}
