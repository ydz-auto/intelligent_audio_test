/**
 * 输入区（interfaces 层 ai-chat/input；08_AI对话页.md §3.5 照 playground-input 逐值）：
 * PromptInput 卡壳（focus-within 主色描边 + 大阴影）+ Textarea + Footer
 * （工具行=模型/供应商切换器 + 清空对话；右区=发送/停止）。
 * Demo 态：报告上下文选择器整块不渲染（§3.10/§3.5），右区仅发送/停止。
 * compact：全局 Agent 工作台浮窗紧凑形态（§3.1B，输入区 min-h-14）。
 */
import { Send, Square } from 'lucide-react'
import { type KeyboardEvent, type RefObject } from 'react'

import {
  PromptInput,
  PromptInputButton,
  PromptInputFooter,
  PromptInputTextarea,
} from '@/components/ai-elements/prompt-input'

import { getInputControlState, getSubmittableInputText } from '@/features/ai-chat/lib/input'
import type { ChatConfig, LlmProvider } from '@/domain/models/aiChat'

import { AiChatInputTools } from './ai-chat-input-tools'

type AiChatInputProps = {
  config: ChatConfig
  onSubmit: (text: string) => void
  onStop?: () => void
  disabled?: boolean
  isGenerating?: boolean
  hasMessages?: boolean
  providers: LlmProvider[]
  onSelectProvider: (providerId: string) => void
  onSelectModel: (providerId: string, modelId: string) => void
  onManageProviders: () => void
  onClearMessages?: () => void
  /** 受控文本（页面持有：starter 回填 / 任务 URL 预填 / 提交后清空） */
  value: string
  onValueChange: (text: string) => void
  /** 输入框聚焦句柄（starter 回填后聚焦） */
  textareaRef?: RefObject<HTMLTextAreaElement | null>
  /** 全局 Agent 工作台浮窗紧凑形态（§3.1B） */
  compact?: boolean
}

export function AiChatInput({
  config,
  onSubmit,
  onStop,
  disabled,
  isGenerating = false,
  hasMessages = false,
  providers,
  onSelectProvider,
  onSelectModel,
  onManageProviders,
  onClearMessages,
  value,
  onValueChange,
  textareaRef,
  compact = false,
}: AiChatInputProps) {
  const { canSubmit, shouldShowStop } = getInputControlState({
    disabled,
    isGenerating,
    hasStopHandler: Boolean(onStop),
    text: value,
  })
  /** 无供应商时发送钮 disabled（§3.11 行为：对话由用户自配 LLM 供应商驱动） */
  const effectiveCanSubmit = canSubmit && providers.length > 0

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (providers.length === 0) return
    const submittableText = getSubmittableInputText(value, disabled)
    if (!submittableText) return
    onSubmit(submittableText)
    onValueChange('')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (providers.length === 0) return
      const submittableText = getSubmittableInputText(value, disabled)
      if (!submittableText) return
      onSubmit(submittableText)
      onValueChange('')
    }
  }

  const renderSubmitButton = () =>
    shouldShowStop ? (
      <PromptInputButton
        className='border-destructive/25 bg-destructive/10 text-destructive hover:bg-destructive/15 font-medium'
        onClick={onStop}
        variant='secondary'
      >
        <Square className='size-4 fill-current' />
        <span className='sr-only'>停止</span>
      </PromptInputButton>
    ) : (
      <PromptInputButton
        className='bg-primary text-primary-foreground hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground h-8 px-3 font-medium shadow-sm'
        disabled={!effectiveCanSubmit}
        type='submit'
        variant='default'
      >
        <Send className='size-4' />
        <span className='sr-only'>发送</span>
      </PromptInputButton>
    )

  return (
    <div className={compact ? 'grid shrink-0 gap-2 px-1 md:pb-2' : 'grid shrink-0 gap-4 px-1 md:pb-4'}>
      <PromptInput
        className='border-border/70 bg-background/95 dark:bg-background/80 ring-foreground/5 shadow-[0_18px_60px_-32px_rgba(0,0,0,0.65)] ring-1 rounded-xl overflow-hidden transition-all duration-200 focus-within:border-primary/45 focus-within:ring-primary/15 focus-within:shadow-[0_22px_70px_-34px_rgba(0,0,0,0.75)]'
        onSubmit={handleSubmit}
      >
        <PromptInputTextarea
          autoCapitalize='off'
          autoComplete='off'
          autoCorrect='off'
          className={
            compact
              ? 'min-h-14 px-4 pt-3 pb-2 leading-6 text-[0.9rem]'
              : 'min-h-20 px-5 pt-4 pb-3 leading-7 md:min-h-24 md:text-base'
          }
          disabled={disabled}
          onChange={(event) => onValueChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder='描述你的报告需求，例如：帮我把任务 #320 的测试结果生成一份报告'
          ref={textareaRef}
          spellCheck={false}
          value={value}
        />

        <PromptInputFooter className='border-border/60 bg-muted/20 dark:bg-muted/10 border-t px-3 py-2.5 backdrop-blur'>
          <div className='flex w-full flex-col gap-2.5 md:flex-row md:items-center md:justify-between'>
            <div className='flex items-center justify-between gap-2 md:justify-start'>
              <AiChatInputTools
                config={config}
                disabled={disabled}
                hasMessages={hasMessages}
                onClearMessages={onClearMessages}
                onManageProviders={onManageProviders}
                onSelectModel={onSelectModel}
                onSelectProvider={onSelectProvider}
                providers={providers}
              />
              <div className='flex items-center gap-1.5 md:hidden'>
                {renderSubmitButton()}
              </div>
            </div>

            {/* Demo 态：报告上下文选择器整块不渲染（§3.10/§3.5），右区仅发送/停止 */}
            <div className='hidden min-w-0 items-center gap-2 md:flex'>
              {renderSubmitButton()}
            </div>
          </div>
        </PromptInputFooter>
      </PromptInput>
    </div>
  )
}
