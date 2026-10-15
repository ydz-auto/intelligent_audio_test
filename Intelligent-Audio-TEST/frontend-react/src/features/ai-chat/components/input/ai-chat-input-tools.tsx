/**
 * 输入区工具行（interfaces 层 ai-chat/input；08_AI对话页.md §3.5）：
 * 生成参数面板 + 清空对话（Trash2 + ConfirmDialog destructive + toast「对话已清空」）；
 * 附件/搜索钮不引入（§2.2 Agent 域无对位能力）。
 */
import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { PromptInputButton, PromptInputTools } from '@/components/ai-elements/prompt-input'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

import type { ChatConfig, ChatParameterKey } from '@/domain/models/aiChat'
import { AgentParameterPanel } from './agent-parameter-panel'

type AiChatInputToolsProps = {
  config: ChatConfig
  disabled?: boolean
  hasMessages?: boolean
  onClearMessages?: () => void
  onConfigChange: <K extends keyof ChatConfig>(
    key: K,
    value: ChatConfig[K]
  ) => void
  onParameterEnabledChange: (key: ChatParameterKey, value: boolean) => void
  parameterEnabled: Record<ChatParameterKey, boolean>
}

export function AiChatInputTools({
  config,
  disabled,
  hasMessages = false,
  onClearMessages,
  onConfigChange,
  onParameterEnabledChange,
  parameterEnabled,
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
        <AgentParameterPanel
          config={config}
          disabled={disabled}
          onConfigChange={onConfigChange}
          onParameterEnabledChange={onParameterEnabledChange}
          parameterEnabled={parameterEnabled}
        />

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
