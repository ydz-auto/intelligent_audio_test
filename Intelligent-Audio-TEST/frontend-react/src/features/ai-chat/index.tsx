/**
 * /ai-chat AI 对话页（Agent 工作台）（interfaces 层；08_AI对话页.md §3.1 三段式装配）。
 * 顶部条 / 全高滚动会话区 / 底部输入区；报告工作模式双栏为增强态变体，
 * Agent 后端立项前整块隐藏（§3.6，入口钮不渲染）。
 * 2026-10-17 新口径：Demo 态四落点标注（顶部条/浮窗头/空态/报告工作模式页脚）；
 * 模型参数注册表移除，仅模型/供应商切换（§3.5/§3.11）；报告上下文选择器
 * Demo 态整块不渲染（§3.5/§3.10，组件树先落，数据交互待后端立项）。
 */
import { Badge } from '@/components/ui/badge'
import { PanelRight } from 'lucide-react'
import { useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

import { useChatHandler } from '@/features/ai-chat/hooks/use-chat-handler'
import { useChatConversation } from '@/features/ai-chat/hooks/use-chat-conversation'
import { useChatState } from '@/features/ai-chat/hooks/use-chat-state'
import { useLlmProviders } from '@/features/ai-chat/hooks/use-llm-providers'
import { AiChat } from '@/features/ai-chat/components/chat/ai-chat'
import { AiChatInput } from '@/features/ai-chat/components/input/ai-chat-input'
import { ProviderManager } from '@/features/ai-chat/components/input/provider-manager'
import { DocumentPanel } from '@/features/ai-chat/components/studio/document-panel'
import { DEMO_COPY } from '@/features/ai-chat/constants'

type AiChatPageProps = {
  /** URL 契约：/ai-chat?report={id} / /ai-chat?task={id}（§3.7） */
  initialContext?: {
    report?: string
    task?: string
  }
}

/** 报告工作模式开关：Agent 后端（DSH + Report Studio）立项后置 true（§3.6） */
const REPORT_WORK_MODE_ENABLED = false

/** 演示文档内容（报告工作模式右栏骨架；仅开关放开后可看） */
const DEMO_DOCUMENT = [
  '# T320 唤醒词识别回归测试报告',
  '',
  '## 摘要',
  '',
  '本次回归共执行 156 个用例，通过率 **92.3%**。',
  '',
  '| 指标 | 数值 |',
  '| --- | --- |',
  '| 通过率 | 92.3% |',
  '| 首唤醒延迟 P50 | 412ms |',
  '',
  '[chart:pass-rate]',
].join('\n')

export function AiChatPage({ initialContext }: AiChatPageProps) {
  const {
    config,
    messages,
    initialPrompt,
    isLoadingMessages,
    updateMessages,
    updateConfig,
    clearMessages,
  } = useChatState(initialContext)

  const {
    providers,
    addProvider,
    updateProvider,
    removeProvider,
    setDefaultProvider,
    defaultProvider,
    testConnection,
    fetchModels,
  } = useLlmProviders()
  const [providerManagerOpen, setProviderManagerOpen] = useState(false)

  /** 输入区受控文本（页面持有：starter 回填 / 任务 URL 预填 / 提交后清空） */
  const [draftText, setDraftText] = useState(initialPrompt ?? '')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  /** 空态 starter：回填输入框并聚焦，不自动发送（§3.3） */
  const handleFillPrompt = (prompt: string) => {
    setDraftText(prompt)
    textareaRef.current?.focus()
  }

  /** 当前会话供应商（config.providerId 命中或默认；§3.11 Demo 直连驱动对话） */
  const currentProvider =
    providers.find((p) => p.id === config.providerId) ??
    defaultProvider ??
    null

  const { sendChat, stopGeneration, isGenerating } = useChatHandler({
    config,
    provider: currentProvider,
    messages,
    onMessageUpdate: updateMessages,
  })

  const {
    editingMessageKey,
    handleSendMessage,
    handleRegenerateMessage,
    handleEditMessage,
    handleEditPromptMessage,
    handleEditOpenChange,
    applyEdit,
    handleDeleteMessage,
    handleUndoMessage,
  } = useChatConversation({
    messages,
    updateMessages,
    sendChat,
  })

  const [workModeOpen, setWorkModeOpen] = useState(false)

  /** 模型/供应商切换（§3.5/§3.11：选择写会话 config，不写全局算法 store） */
  const handleSelectProvider = (providerId: string) => {
    updateConfig('providerId', providerId)
  }
  const handleSelectModel = (providerId: string, modelId: string) => {
    updateConfig('providerId', providerId)
    updateConfig('modelId', modelId)
  }

  const handleClearMessages = () => {
    handleEditOpenChange(false)
    clearMessages()
  }

  return (
    <div className='relative flex size-full min-h-0 flex-col overflow-hidden'>
      {/* 顶部条（shrink-0，§3.1/§3.2）；Demo 徽标 §3.10 落点① */}
      <div className='border-border/60 flex shrink-0 items-center justify-between gap-3 border-b px-4 py-3 sm:px-6'>
        <div className='min-w-0'>
          <div className='flex items-center gap-2'>
            <h1 className='text-sm font-semibold sm:text-base'>灵犀Agent</h1>
            <Tooltip>
              <TooltipTrigger
                render={
                  <Badge variant='warning' className='cursor-help'>
                    {DEMO_COPY.badge}
                  </Badge>
                }
              />
              <TooltipContent>
                <p>{DEMO_COPY.tooltip}</p>
              </TooltipContent>
            </Tooltip>
          </div>
          <p className='text-muted-foreground hidden text-xs sm:block'>
            用自然语言驱动平台全部能力：报告、用例、任务、设备、日志
          </p>
        </div>
        {REPORT_WORK_MODE_ENABLED && (
          <Button
            className='h-9 shrink-0 px-4 text-sm'
            onClick={() => setWorkModeOpen((value) => !value)}
            type='button'
            variant='ghost'
          >
            <PanelRight className='size-4' />
            {workModeOpen ? '关闭文档预览' : '报告工作模式'}
          </Button>
        )}
      </div>

      {/* 会话区 + 报告工作模式双栏（§3.6：Agent 后端立项前整块不渲染） */}
      {REPORT_WORK_MODE_ENABLED && workModeOpen ? (
        <div className='flex min-h-0 flex-1'>
          <div className='grid min-h-0 min-w-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(22rem,2fr)_minmax(0,3fr)]'>
            <div className='flex min-h-0 flex-1 flex-col overflow-hidden'>
              <div className='flex min-h-0 flex-1 flex-col overflow-hidden'>
                <AiChat
                  editingKey={editingMessageKey}
                  isGenerating={isGenerating}
                  isLoadingMessages={isLoadingMessages}
                  messages={messages}
                  onCancelEdit={handleEditOpenChange}
                  onDeleteMessage={handleDeleteMessage}
                  onEditMessage={handleEditMessage}
                  onEditPromptMessage={handleEditPromptMessage}
                  onFillPrompt={handleFillPrompt}
                  onRegenerateMessage={handleRegenerateMessage}
                  onSaveEdit={(content) => applyEdit(content, false)}
                  onSaveEditAndSubmit={(content) => applyEdit(content, true)}
                  onUndoMessage={handleUndoMessage}
                />
              </div>
              <div className='shrink-0'>
                <AiChatInput
                  compact
                  config={config}
                  disabled={isGenerating}
                  hasMessages={messages.length > 0}
                  isGenerating={isGenerating}
                  onClearMessages={handleClearMessages}
                  onManageProviders={() => setProviderManagerOpen(true)}
                  onSelectModel={handleSelectModel}
                  onSelectProvider={handleSelectProvider}
                  onStop={stopGeneration}
                  onSubmit={handleSendMessage}
                  onValueChange={setDraftText}
                  providers={providers}
                  textareaRef={textareaRef}
                  value={draftText}
                />
              </div>
            </div>
            <div className='hidden min-h-0 min-w-0 lg:block'>
              <DocumentPanel
                content={DEMO_DOCUMENT}
                documentName='T320 唤醒词识别回归测试报告'
                onClose={() => setWorkModeOpen(false)}
                version={3}
              />
            </div>
          </div>
        </div>
      ) : (
        <>
          <div className='flex min-h-0 flex-1 flex-col overflow-hidden'>
            <AiChat
              editingKey={editingMessageKey}
              isGenerating={isGenerating}
              isLoadingMessages={isLoadingMessages}
              messages={messages}
              onCancelEdit={handleEditOpenChange}
              onDeleteMessage={handleDeleteMessage}
              onEditMessage={handleEditMessage}
              onEditPromptMessage={handleEditPromptMessage}
              onFillPrompt={handleFillPrompt}
              onRegenerateMessage={handleRegenerateMessage}
              onSaveEdit={(content) => applyEdit(content, false)}
              onSaveEditAndSubmit={(content) => applyEdit(content, true)}
              onUndoMessage={handleUndoMessage}
            />
          </div>

          {/* 输入区（max-w-4xl 居中钳制，§3.1） */}
          <div className='mx-auto w-full max-w-4xl'>
            <AiChatInput
              config={config}
              disabled={isGenerating}
              hasMessages={messages.length > 0}
              isGenerating={isGenerating}
              onClearMessages={handleClearMessages}
              onManageProviders={() => setProviderManagerOpen(true)}
              onSelectModel={handleSelectModel}
              onSelectProvider={handleSelectProvider}
              onStop={stopGeneration}
              onSubmit={handleSendMessage}
              onValueChange={setDraftText}
              providers={providers}
              textareaRef={textareaRef}
              value={draftText}
            />
          </div>
        </>
      )}

      {/* 供应商管理弹窗（§3.11；整页与全局浮窗共用同一供应商清单） */}
      <ProviderManager
        onAdd={addProvider}
        onFetchModels={fetchModels}
        onOpenChange={setProviderManagerOpen}
        onRemove={removeProvider}
        onSetDefault={setDefaultProvider}
        onTestConnection={testConnection}
        onUpdate={updateProvider}
        open={providerManagerOpen}
        providers={providers}
      />
    </div>
  )
}
