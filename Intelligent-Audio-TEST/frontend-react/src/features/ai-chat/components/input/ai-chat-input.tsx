/**
 * 输入区（interfaces 层 ai-chat/input；08_AI对话页.md §3.5 照 playground-input 逐值）：
 * PromptInput 卡壳（focus-within 主色描边 + 大阴影）+ Textarea + Footer
 * （工具行=模型/供应商切换器 + 清空对话；右区=发送/停止）。
 * 报告上下文选择器不在输入区：它是报告工作模式的绑定入口（DocumentPanel 头行）。
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
import { AgentProviderModelPicker } from '@/features/agent-providers/components/agent-provider-model-picker'
import {
  CHAT_CHANNEL,
  type ChatChannel,
  type ChatConfig,
  type LlmProvider,
} from '@/domain/models/aiChat'
import {
  AGENT_AUTO_COPY,
  AGENT_RUN_MODE,
  type AgentAutoBudgetDefaults,
  type AgentRunBudget,
  type AgentRunMode,
} from '@/domain/models/agent'

import { AutoBudgetSettings } from '../auto-mode/auto-budget-settings'
import { AiChatInputTools } from './ai-chat-input-tools'

type AiChatInputProps = {
  config: ChatConfig
  onSubmit: (text: string) => void
  onStop?: () => void
  disabled?: boolean
  isGenerating?: boolean
  hasMessages?: boolean
  /** 已废弃：对话只保留平台 Agent 通道（保留可选位以兼容复核弹窗等历史调用方） */
  providers?: LlmProvider[]
  channel?: ChatChannel
  onChannelChange?: (channel: ChatChannel) => void
  onSelectProvider?: (providerId: string) => void
  onSelectModel?: (providerId: string, modelId: string) => void
  onManageProviders?: () => void
  /** 本轮模型（对话页模型下拉；留空=默认供应商配置的模型） */
  model?: string
  onModelChange?: (model: string) => void
  /** 本轮供应商（空=默认供应商；传入后展示供应商下拉） */
  providerId?: string
  onProviderChange?: (providerId: string) => void
  onClearMessages?: () => void
  /** 对话记录面板（浮窗侧边会话：同一窗口内切换历史会话） */
  historyOpen?: boolean
  onToggleHistory?: () => void
  /** 新建会话（结束当前会话上下文，下一次发送新建） */
  onNewConversation?: () => void
  /** 受控文本（页面持有：starter 回填 / 任务 URL 预填 / 提交后清空） */
  value: string
  onValueChange: (text: string) => void
  /** 输入框聚焦句柄（starter 回填后聚焦） */
  textareaRef?: RefObject<HTMLTextAreaElement | null>
  /** 取消请求在途：停止钮禁用，防重复取消（INT-2457） */
  isStopping?: boolean
  /** 全局 Agent 工作台浮窗紧凑形态（§3.1B） */
  compact?: boolean
  /** 目标模式（默认普通对话；开启后按目标多轮推进） */
  runMode?: AgentRunMode
  onRunModeChange?: (mode: AgentRunMode) => void
  /** 目标模式预算（会话 config 里的预算；可上调，留空用服务端默认） */
  autoBudget?: AgentRunBudget
  /** 服务端预算默认值（展示「留空生效」口径） */
  autoBudgetDefaults?: AgentAutoBudgetDefaults
  onAutoBudgetChange?: (budget: AgentRunBudget | undefined) => void
}

export function AiChatInput({
  onSubmit,
  onStop,
  disabled,
  isGenerating = false,
  hasMessages = false,
  providers = [],
  channel = CHAT_CHANNEL.PLATFORM,
  onClearMessages,
  onManageProviders,
  historyOpen = false,
  onToggleHistory,
  onNewConversation,
  model,
  onModelChange,
  providerId,
  onProviderChange,
  value,
  onValueChange,
  textareaRef,
  isStopping = false,
  compact = false,
  runMode = AGENT_RUN_MODE.CHAT,
  onRunModeChange,
  autoBudget,
  autoBudgetDefaults,
  onAutoBudgetChange,
}: AiChatInputProps) {
  const { canSubmit, shouldShowStop } = getInputControlState({
    disabled,
    isGenerating,
    hasStopHandler: Boolean(onStop),
    text: value,
  })
  /** 供应商通道无供应商时禁用发送（§3.11）；平台 Agent 通道不依赖本机供应商 */
  const requiresProvider = channel === CHAT_CHANNEL.PROVIDER
  const effectiveCanSubmit =
    canSubmit && (!requiresProvider || providers.length > 0)

  /** 目标模式只在平台 Agent 通道可用（供应商直连无工具/预算） */
  const isPlatform = channel === CHAT_CHANNEL.PLATFORM
  const isTargetMode = isPlatform && runMode === AGENT_RUN_MODE.AUTO

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (requiresProvider && providers.length === 0) return
    const submittableText = getSubmittableInputText(value, disabled)
    if (!submittableText) return
    onSubmit(submittableText)
    onValueChange('')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (requiresProvider && providers.length === 0) return
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
        disabled={isStopping}
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
      {/* 平台 Agent 通道：服务端供应商 + 模型选择（与供应商管理页同一 query key） */}
      {channel === CHAT_CHANNEL.PLATFORM && onProviderChange && onModelChange && (
        <div className='flex min-w-0 items-center gap-2 px-2'>
          <AgentProviderModelPicker
            compact={compact}
            model={model}
            onModelChange={onModelChange}
            onProviderChange={onProviderChange}
            providerId={providerId}
          />
        </div>
      )}
      <PromptInput
        className='border-border/70 bg-background/95 dark:bg-background/80 ring-foreground/5 shadow-[0_18px_60px_-32px_rgba(0,0,0,0.65)] ring-1 rounded-xl overflow-hidden transition-all duration-200 focus-within:border-primary/45 focus-within:ring-primary/15 focus-within:shadow-[0_22px_70px_-34px_rgba(0,0,0,0.75)]'
        onSubmit={handleSubmit}
      >
        {/* 目标模式预算：开启目标模式后、启动前即可展示 / 调整五项预算（§9.4） */}
        {isTargetMode && onAutoBudgetChange && (
          <AutoBudgetSettings
            budget={autoBudget}
            defaults={autoBudgetDefaults}
            disabled={disabled}
            onBudgetChange={onAutoBudgetChange}
          />
        )}
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
          placeholder={
            isTargetMode
              ? AGENT_AUTO_COPY.goalPlaceholder
              : '描述你的报告需求，例如：帮我把任务 #320 的测试结果生成一份报告'
          }
          ref={textareaRef}
          spellCheck={false}
          value={value}
        />

        <PromptInputFooter className='border-border/60 bg-muted/20 dark:bg-muted/10 border-t px-3 py-2.5 backdrop-blur'>
          <div className='flex w-full flex-col gap-2.5 md:flex-row md:items-center md:justify-between'>
            <div className='flex items-center justify-between gap-2 md:justify-start'>
              <AiChatInputTools
                disabled={disabled}
                hasMessages={hasMessages}
                historyOpen={historyOpen}
                onClearMessages={onClearMessages}
                onManageProviders={onManageProviders}
                onNewConversation={onNewConversation}
                onRunModeChange={onRunModeChange}
                onToggleHistory={onToggleHistory}
                runMode={runMode}
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
