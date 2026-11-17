/**
 * 输入区工具行（interfaces 层 ai-chat/input）：模型供应商入口 + 目标模式开关 + 清空对话。
 * 默认普通对话；「目标模式」开启后按目标多轮推进（含预算 / 暂停继续）。
 */
import { KeyRound, Trash2 } from 'lucide-react'
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
  runMode?: AgentRunMode
  onRunModeChange?: (mode: AgentRunMode) => void
  /** 打开模型供应商管理（新增 / 编辑 / 自动发现模型） */
  onManageProviders?: () => void
}

export function AiChatInputTools({
  disabled,
  hasMessages = false,
  onClearMessages,
  runMode = AGENT_RUN_MODE.CHAT,
  onRunModeChange,
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
        {onManageProviders && (
          <Tooltip>
            <TooltipTrigger
              render={
                <PromptInputButton
                  aria-label='模型供应商'
                  className='text-muted-foreground hover:text-foreground font-medium'
                  onClick={onManageProviders}
                  variant='ghost'
                >
                  <KeyRound className='size-4' />
                </PromptInputButton>
              }
            />
            <TooltipContent>
              <p>模型供应商</p>
            </TooltipContent>
          </Tooltip>
        )}

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
