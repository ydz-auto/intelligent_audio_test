/**
 * 全局 Agent 工作台浮窗（interfaces 层 features/agent-workbench；08_AI对话页.md §3.1B）。
 * fixed 悬浮窗 + createPortal 到 body；渲染于 AuthenticatedLayout 根部，**不随路由卸载**——
 * 登录壳任意页面可打开，切换页面浮窗保持打开、会话不丢（照 Cloudflare dash 跨页驻留语义）。
 * 内嵌与 /ai-chat 整页同一套灵犀Agent 会话（共享 localStorage iatp:ai-chat:v1:*，切换形态不丢会话）。
 * Demo 态：头行 Demo 徽标（§3.10 落点②）；报告上下文选择器整块不渲染（§3.1B/§3.10）。
 * RBAC（§5）：report:read 门槛同整页——device_admin 无 report:read 时整窗不渲染。
 */
import { Maximize2, Minus, Sparkles, X } from 'lucide-react'
import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from '@tanstack/react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { usePermissions } from '@/application/hooks/use-permissions'

import { useChatState } from '@/features/ai-chat/hooks/use-chat-state'
import { useChatHandler } from '@/features/ai-chat/hooks/use-chat-handler'
import { useChatConversation } from '@/features/ai-chat/hooks/use-chat-conversation'
import { useLlmProviders } from '@/features/ai-chat/hooks/use-llm-providers'
import { AiChat } from '@/features/ai-chat/components/chat/ai-chat'
import { AiChatInput } from '@/features/ai-chat/components/input/ai-chat-input'
import { ProviderManager } from '@/features/ai-chat/components/input/provider-manager'
import { DEMO_COPY } from '@/features/ai-chat/constants'
import { useAgentWorkbench } from '@/infrastructure/stores/agentWorkbenchStore'

import { AgentWorkbenchCapsule } from './agent-workbench-capsule'

/** 浮窗内嵌会话（minimized 时卸载；重新展开从 localStorage 恢复，切换形态不丢会话） */
function AgentWorkbenchSession() {
  const {
    config,
    messages,
    isLoadingMessages,
    updateMessages,
    updateConfig,
    clearMessages,
  } = useChatState()
  const {
    providers,
    addProvider,
    updateProvider,
    removeProvider,
    setDefaultProvider,
    testConnection,
    fetchModels,
  } = useLlmProviders()
  const [providerManagerOpen, setProviderManagerOpen] = useState(false)

  const [draftText, setDraftText] = useState('')

  const { sendChat, stopGeneration, isGenerating } = useChatHandler({
    config,
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
  } = useChatConversation({ messages, updateMessages, sendChat })

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
    <>
      <div className='flex min-h-0 flex-1 flex-col overflow-hidden'>
        <AiChat
          compact
          editingKey={editingMessageKey}
          isGenerating={isGenerating}
          isLoadingMessages={isLoadingMessages}
          messages={messages}
          onCancelEdit={handleEditOpenChange}
          onDeleteMessage={handleDeleteMessage}
          onEditMessage={handleEditMessage}
          onEditPromptMessage={handleEditPromptMessage}
          onFillPrompt={setDraftText}
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
          value={draftText}
        />
      </div>
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
    </>
  )
}

export function AgentWorkbench() {
  const navigate = useNavigate()
  const { hasPermission } = usePermissions()
  const open = useAgentWorkbench((s) => s.open)
  const minimized = useAgentWorkbench((s) => s.minimized)
  const setMinimized = useAgentWorkbench((s) => s.setMinimized)
  const setOpen = useAgentWorkbench((s) => s.setOpen)

  // RBAC（§5）：device_admin 无 report:read 时魔法按钮与浮窗均不渲染
  if (!hasPermission('report:read') || !open) return null

  /** 展开整页（§3.1B）：关闭浮窗并导航 /ai-chat，会话保留（同 localStorage） */
  const handleExpand = () => {
    setOpen(false)
    void navigate({ to: '/ai-chat' })
  }

  const floatingWindow = (
    <div className='bg-background fixed right-4 bottom-4 z-50 flex w-[min(28rem,calc(100vw-1rem))] max-h-[min(44rem,calc(100svh-5rem))] flex-col overflow-hidden rounded-2xl border shadow-2xl'>
      {/* 头行（§3.1B）：Demo 徽标 §3.10 落点② */}
      <div className='border-b px-3 py-2.5 flex shrink-0 items-center gap-2'>
        <Sparkles className='text-primary size-4 shrink-0' />
        <span className='text-sm font-semibold'>灵犀Agent</span>
        <Tooltip>
          <TooltipTrigger
            render={
              <Badge variant='warning' className='cursor-help'>
                {DEMO_COPY.badge}
              </Badge>
            }
          />
          <TooltipContent>
            <p>{DEMO_COPY.floatingTooltip}</p>
          </TooltipContent>
        </Tooltip>
        <div className='ms-auto flex items-center gap-0.5'>
          <Button
            aria-label='最小化'
            className='text-muted-foreground hover:text-foreground size-7'
            onClick={() => setMinimized(true)}
            type='button'
            variant='ghost'
          >
            <Minus className='size-4' />
          </Button>
          <Button
            aria-label='展开整页'
            className='text-muted-foreground hover:text-foreground size-7'
            onClick={handleExpand}
            type='button'
            variant='ghost'
          >
            <Maximize2 className='size-4' />
          </Button>
          <Button
            aria-label='关闭'
            className='text-muted-foreground hover:text-foreground size-7'
            onClick={() => setOpen(false)}
            type='button'
            variant='ghost'
          >
            <X className='size-4' />
          </Button>
        </div>
      </div>

      {/* 会话区 + 输入区（浮窗内高度受限用更紧凑间距，§3.1B） */}
      <div className='flex min-h-0 flex-1 flex-col overflow-hidden'>
        <AgentWorkbenchSession />
      </div>
    </div>
  )

  return createPortal(
    minimized ? <AgentWorkbenchCapsule /> : floatingWindow,
    document.body
  )
}
