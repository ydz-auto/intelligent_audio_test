/**
 * 输入区工具行（interfaces 层 ai-chat/input）：运行模式（对话 / Auto）+ 清空对话。
 * 对话只有平台 Agent 一条通道，不再渲染通道切换与供应商选择。
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

import {
  AGENT_RUN_MODE,
  type AgentRunMode,
} from '@/domain/models/agent'
import { AutoModeSwitcher } from '../auto-mode/auto-mode-switcher'

type AiChatInputToolsProps = {
  disabled?: boolean
  hasMessages?: boolean
  onClearMessages?: () => void
  /** 运行模式（INT-2474；平台 Agent 通道的对话 / Auto） */
  runMode?: AgentRunMode
  onRunModeChange?: (mode: AgentRunMode) => void
}

export function AiChatInputTools({
  disabled,
  hasMessages = false,
  onClearMessages,
  runMode = AGENT_RUN_MODE.CHAT,
  onRunModeChange,
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
        {/* 运行模式（INT-2474）：Auto 只在平台 Agent 通道可选 */}
        {onRunModeChange && (
          <AutoModeSwitcher
            disabled={disabled}
            mode={runMode}
            onModeChange={onRunModeChange}
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
