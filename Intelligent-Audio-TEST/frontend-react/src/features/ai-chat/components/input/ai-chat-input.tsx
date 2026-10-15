/**
 * 输入区（interfaces 层 ai-chat/input；08_AI对话页.md §3.5 照 playground-input 逐值）：
 * PromptInput 卡壳（focus-within 主色描边 + 大阴影）+ Textarea + Footer
 * （工具行 / 报告上下文选择器 / 发送·停止）；移动端选择器独立行。
 */
import { Send, Square } from 'lucide-react'
import { type KeyboardEvent, useState } from 'react'

import {
  PromptInput,
  PromptInputButton,
  PromptInputFooter,
  PromptInputTextarea,
} from '@/components/ai-elements/prompt-input'

import { getInputControlState, getSubmittableInputText } from '@/features/ai-chat/lib/input'
import type { ChatConfig, ChatParameterKey, ReportContextOption } from '@/domain/models/aiChat'
import type { ReportContextGroup } from '@/features/ai-chat/hooks/use-report-context'

import { AiChatInputTools } from './ai-chat-input-tools'
import { ReportContextSelector, type SelectedContext } from './report-context-selector'

type AiChatInputProps = {
  config: ChatConfig
  onSubmit: (text: string) => void
  onStop?: () => void
  disabled?: boolean
  isGenerating?: boolean
  hasMessages?: boolean
  groups: ReportContextGroup[]
  selectedContext: SelectedContext | null
  onSelectContext: (option: ReportContextOption) => void
  onConfigChange: <K extends keyof ChatConfig>(
    key: K,
    value: ChatConfig[K]
  ) => void
  onClearMessages?: () => void
  onParameterEnabledChange: (key: ChatParameterKey, value: boolean) => void
  parameterEnabled: Record<ChatParameterKey, boolean>
}

export function AiChatInput({
  config,
  onSubmit,
  onStop,
  disabled,
  isGenerating = false,
  hasMessages = false,
  groups,
  selectedContext,
  onSelectContext,
  onConfigChange,
  onClearMessages,
  onParameterEnabledChange,
  parameterEnabled,
}: AiChatInputProps) {
  const [text, setText] = useState('')

  const { canSubmit, shouldShowStop } = getInputControlState({
    disabled,
    isGenerating,
    hasStopHandler: Boolean(onStop),
    text,
  })

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    const submittableText = getSubmittableInputText(text, disabled)
    if (!submittableText) return
    onSubmit(submittableText)
    setText('')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      const submittableText = getSubmittableInputText(text, disabled)
      if (!submittableText) return
      onSubmit(submittableText)
      setText('')
    }
  }

  const renderSelector = () => (
    <ReportContextSelector
      disabled={disabled}
      groups={groups}
      onSelect={onSelectContext}
      value={selectedContext}
    />
  )

  const renderSubmitButton = () =>
    shouldShowStop ? (
      <PromptInputButton
        className='border-destructive/25 bg-destructive/10 text-destructive hover:bg-destructive/15 font-medium'
        onClick={onStop}
        variant='secondary'
      >
        <Square className='size-4 fill-current' />
        <span className='hidden sm:inline'>停止</span>
        <span className='sr-only sm:hidden'>停止</span>
      </PromptInputButton>
    ) : (
      <PromptInputButton
        className='bg-primary text-primary-foreground hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground h-8 px-3 font-medium shadow-sm'
        disabled={!canSubmit}
        type='submit'
        variant='default'
      >
        <Send className='size-4' />
        <span className='hidden sm:inline'>发送</span>
        <span className='sr-only sm:hidden'>发送</span>
      </PromptInputButton>
    )

  return (
    <div className='grid shrink-0 gap-4 px-1 md:pb-4'>
      <PromptInput
        className='border-border/70 bg-background/95 dark:bg-background/80 ring-foreground/5 shadow-[0_18px_60px_-32px_rgba(0,0,0,0.65)] ring-1 rounded-xl overflow-hidden transition-all duration-200 focus-within:border-primary/45 focus-within:ring-primary/15 focus-within:shadow-[0_22px_70px_-34px_rgba(0,0,0,0.75)]'
        onSubmit={handleSubmit}
      >
        <PromptInputTextarea
          autoCapitalize='off'
          autoComplete='off'
          autoCorrect='off'
          className='min-h-20 px-5 pt-4 pb-3 leading-7 md:min-h-24 md:text-base'
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder='描述你的报告需求，例如：帮我把任务 #320 的测试结果生成一份报告'
          spellCheck={false}
          value={text}
        />

        <PromptInputFooter className='border-border/60 bg-muted/20 dark:bg-muted/10 border-t px-3 py-2.5 backdrop-blur'>
          <div className='flex w-full flex-col gap-2.5 md:flex-row md:items-center md:justify-between'>
            <div className='flex min-w-0 items-center justify-end md:hidden'>
              {renderSelector()}
            </div>

            <div className='flex items-center justify-between gap-2 md:justify-start'>
              <AiChatInputTools
                config={config}
                disabled={disabled}
                hasMessages={hasMessages}
                onClearMessages={onClearMessages}
                onConfigChange={onConfigChange}
                onParameterEnabledChange={onParameterEnabledChange}
                parameterEnabled={parameterEnabled}
              />
              <div className='flex items-center gap-1.5 md:hidden'>
                {renderSubmitButton()}
              </div>
            </div>

            <div className='hidden min-w-0 items-center gap-2 md:flex'>
              {renderSelector()}
              {renderSubmitButton()}
            </div>
          </div>
        </PromptInputFooter>
      </PromptInput>
    </div>
  )
}
