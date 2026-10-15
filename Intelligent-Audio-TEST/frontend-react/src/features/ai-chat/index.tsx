/**
 * /ai-chat AI 对话页（Agent 工作台）（interfaces 层；08_AI对话页.md §3.1 三段式装配）。
 * 顶部条 / 全高滚动会话区 / 底部输入区；报告工作模式双栏为增强态变体，
 * Agent 后端立项前整块隐藏（§3.6，入口钮不渲染）。
 */
import { PanelRight } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'

import { useChatHandler } from '@/features/ai-chat/hooks/use-chat-handler'
import { useChatConversation } from '@/features/ai-chat/hooks/use-chat-conversation'
import { useChatState } from '@/features/ai-chat/hooks/use-chat-state'
import { useReportContext } from '@/features/ai-chat/hooks/use-report-context'
import { AiChat } from '@/features/ai-chat/components/chat/ai-chat'
import { AiChatInput } from '@/features/ai-chat/components/input/ai-chat-input'
import { DocumentPanel } from '@/features/ai-chat/components/studio/document-panel'
import type { ReportContextOption } from '@/domain/models/aiChat'

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
  const { groups } = useReportContext()
  const {
    config,
    parameterEnabled,
    messages,
    isLoadingMessages,
    updateMessages,
    updateConfig,
    updateParameterEnabled,
    clearMessages,
  } = useChatState(initialContext)

  const { sendChat, stopGeneration, isGenerating } = useChatHandler({
    config,
    parameterEnabled,
    onMessageUpdate: updateMessages,
  })

  const {
    editingMessageKey,
    handleSendMessage,
    handleRegenerateMessage,
    handleEditMessage,
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

  /** 报告上下文选择器当前值（从 config.reportContextId 派生，选择写会话上下文不写全局算法 store） */
  const selectedContext = useMemo(() => {
    if (!config.reportContextId) return null
    for (const group of groups) {
      const found = group.options.find(
        (option) => option.id === config.reportContextId
      )
      if (found) {
        return {
          id: found.id,
          label: found.label,
          badge: found.badge,
          type: found.type,
        }
      }
    }
    return null
  }, [config.reportContextId, groups])

  const handleSelectContext = (option: ReportContextOption) => {
    updateConfig('reportContextId', option.id)
    updateConfig('reportContextLabel', option.label)
    updateConfig('reportContextType', option.type)
  }

  const handleClearMessages = () => {
    handleEditOpenChange(false)
    clearMessages()
  }

  return (
    <div className='relative flex size-full min-h-0 flex-col overflow-hidden'>
      {/* 顶部条（shrink-0，§3.1/§3.2） */}
      <div className='border-border/60 flex shrink-0 items-center justify-between gap-3 border-b px-4 py-3 sm:px-6'>
        <div className='min-w-0'>
          <h1 className='text-sm font-semibold sm:text-base'>AI 对话</h1>
          <p className='text-muted-foreground hidden text-xs sm:block'>
            用自然语言生成、对比、解读测试报告
          </p>
        </div>
        {REPORT_WORK_MODE_ENABLED && selectedContext && (
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

      {/* 会话区 + 报告工作模式双栏 */}
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
                  onRegenerateMessage={handleRegenerateMessage}
                  onSaveEdit={(content) => applyEdit(content, false)}
                  onSaveEditAndSubmit={(content) => applyEdit(content, true)}
                  onSelectPrompt={handleSendMessage}
                  onUndoMessage={handleUndoMessage}
                />
              </div>
              <div className='shrink-0'>
                <AiChatInput
                  config={config}
                  disabled={isGenerating}
                  groups={groups}
                  hasMessages={messages.length > 0}
                  isGenerating={isGenerating}
                  onClearMessages={handleClearMessages}
                  onConfigChange={updateConfig}
                  onParameterEnabledChange={updateParameterEnabled}
                  onSelectContext={handleSelectContext}
                  onStop={stopGeneration}
                  onSubmit={handleSendMessage}
                  parameterEnabled={parameterEnabled}
                  selectedContext={selectedContext}
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
              onRegenerateMessage={handleRegenerateMessage}
              onSaveEdit={(content) => applyEdit(content, false)}
              onSaveEditAndSubmit={(content) => applyEdit(content, true)}
              onSelectPrompt={handleSendMessage}
              onUndoMessage={handleUndoMessage}
            />
          </div>

          {/* 输入区（max-w-4xl 居中钳制，§3.1） */}
          <div className='mx-auto w-full max-w-4xl'>
            <AiChatInput
              config={config}
              disabled={isGenerating}
              groups={groups}
              hasMessages={messages.length > 0}
              isGenerating={isGenerating}
              onClearMessages={handleClearMessages}
              onConfigChange={updateConfig}
              onParameterEnabledChange={updateParameterEnabled}
              onSelectContext={handleSelectContext}
              onStop={stopGeneration}
              onSubmit={handleSendMessage}
              parameterEnabled={parameterEnabled}
              selectedContext={selectedContext}
            />
          </div>
        </>
      )}
    </div>
  )
}
