/**
 * 全局 Agent 工作台浮窗（interfaces 层 features/agent-workbench；08_AI对话页.md §3.1B）。
 * fixed 悬浮窗 + createPortal 到 body；渲染于 AuthenticatedLayout 根部，**不随路由卸载**——
 * 登录壳任意页面可打开，切换页面浮窗保持打开、会话不丢（照 Cloudflare dash 跨页驻留语义）。
 * 内嵌与 /ai-chat 整页同一套灵犀Agent 会话（共享 localStorage iatp:ai-chat:v1:*，切换形态不丢会话）。
 * Demo 态：头行 Demo 徽标（§3.10 落点②）；报告上下文选择器整块不渲染（§3.1B/§3.10）。
 * RBAC（§5）：report:read 门槛同整页——device_admin 无 report:read 时整窗不渲染。
 */
import { KeyRound, Maximize2, Minus, Sparkles, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useLocation, useNavigate } from '@tanstack/react-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useAgentRunHost } from '@/application/agent/use-agent-run'
import { useAgentRunStore } from '@/application/agent/agent-run-store'
import { AgentConnectButton } from '@/components/layout/components/agent-connect-button'
import {
  AGENT_PROVIDERS_COPY,
  AGENT_PROVIDERS_ROUTE,
  AGENT_PROVIDER_MANAGE_PERMISSION,
} from '@/features/agent-providers/constants'

import {
  normalizeChatChannel,
  type ChatChannel,
} from '@/domain/models/aiChat'
import { useChatState } from '@/features/ai-chat/hooks/use-chat-state'
import { useChatHandler } from '@/features/ai-chat/hooks/use-chat-handler'
import { useChatConversation } from '@/features/ai-chat/hooks/use-chat-conversation'
import { useLlmProviders } from '@/features/ai-chat/hooks/use-llm-providers'
import { AiChat } from '@/features/ai-chat/components/chat/ai-chat'
import { AiChatInput } from '@/features/ai-chat/components/input/ai-chat-input'
import { ProviderManager } from '@/features/ai-chat/components/input/provider-manager'
import { DEFAULT_CHAT_CHANNEL, DEMO_COPY } from '@/features/ai-chat/constants'
import { useAgentWorkbench } from '@/infrastructure/stores/agentWorkbenchStore'

import { AgentWorkbenchCapsule } from './agent-workbench-capsule'
import {
  getPageAgentCapability,
  type PageAgentCapability,
} from './page-agent-capabilities'

/** 浮窗内嵌会话（minimized 时卸载；重新展开从 localStorage 恢复，切换形态不丢会话） */
function AgentWorkbenchSession({
  pageCtx,
}: {
  /** 本页 Agent 能力（§3.1B 2026-10-17 负责人口径：每页可做的事不同；null=不渲染专页条） */
  pageCtx: PageAgentCapability | null
}) {
  const {
    config,
    messages,
    isLoadingMessages,
    updateMessages,
    updateConfig,
    clearMessages,
  } = useChatState()

  // 宿主登记（INT-2521 按 A5–A7 收窄）：最小化 / 展开整页都是暂时卸载，传 'keep' 不取消在办
  // run；浮窗「关闭」由头行关闭钮先声明取消语义（见 AgentWorkbench 的 handleClose）。
  useAgentRunHost('workbench', 'keep')
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

  const [draftText, setDraftText] = useState('')

  /** 当前会话供应商（config.providerId 命中或默认；§3.11 Demo 直连驱动对话） */
  const currentProvider =
    providers.find((p) => p.id === config.providerId) ??
    defaultProvider ??
    null

  /** 配置即用（§3.11/INT-1032 走查）：供应商带模型而会话未选模型/所选模型已不在
   * 清单时自动落首个模型——与 /ai-chat 整页同口径，添加供应商后无需再手动选模型
   * 即可对话；手动切换模型后命中校验、效果不再覆写。 */
  useEffect(() => {
    if (!currentProvider) return
    const modelValid = currentProvider.models.includes(config.modelId ?? '')
    if (currentProvider.models.length > 0 && !modelValid) {
      updateConfig('providerId', currentProvider.id)
      updateConfig('modelId', currentProvider.models[0])
    }
  }, [currentProvider, config.modelId, updateConfig])

  /** 对话通道（INT-2457）：与整页同一 config.chatMode，两形态不分裂通道 */
  const channel = normalizeChatChannel(config.chatMode ?? DEFAULT_CHAT_CHANNEL)
  const handleChannelChange = (next: ChatChannel) => {
    updateConfig('chatMode', next)
  }

  const {
    sendChat,
    stopGeneration,
    isGenerating,
    isCancelling,
    runPhase,
    run,
    approvals,
    approvalsLoading,
    approvalsError,
    decidingApprovalIds,
    timeline,
    decideApproval,
    refreshApprovals,
    resetChat,
  } = useChatHandler({
    channel,
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
    // 平台通道同时结束会话上下文（两形态共享 store，清空后下次发送新建会话）
    resetChat()
    clearMessages()
  }

  return (
    <>
      {pageCtx && (
        <div className='border-border/60 bg-muted/20 dark:bg-muted/10 border-b px-3 py-2 shrink-0'>
          <div className='flex items-center gap-1.5'>
            <span className='text-muted-foreground text-xs font-medium'>
              {DEMO_COPY.pageCapabilityTitle} · {pageCtx.domainLabel}
            </span>
            <Tooltip>
              <TooltipTrigger
                render={
                  <Badge variant='warning' className='cursor-help'>
                    {DEMO_COPY.pageCapabilityBadge}
                  </Badge>
                }
              />
              <TooltipContent>
                <p>{DEMO_COPY.pageCapabilityTooltip}</p>
              </TooltipContent>
            </Tooltip>
          </div>
          <div className='mt-1.5 flex flex-wrap gap-1'>
            {pageCtx.quickPrompts.map((prompt) => (
              <button
                key={prompt}
                className='text-muted-foreground hover:text-foreground hover:bg-accent h-6 cursor-pointer rounded-md border px-2 text-[11px] transition-colors'
                onClick={() => setDraftText(prompt)}
                type='button'
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}
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
          runPhase={runPhase}
          approvals={approvals}
          approvalsError={approvalsError}
          approvalsLoading={approvalsLoading}
          decidingApprovalIds={decidingApprovalIds}
          onDecideApproval={decideApproval}
          onRetryApprovals={() => void refreshApprovals()}
          run={run}
          timeline={timeline}
        />
      </div>
      <div className='shrink-0'>
        <AiChatInput
          channel={channel}
          compact
          config={config}
          disabled={isGenerating}
          isStopping={isCancelling}
          hasMessages={messages.length > 0}
          isGenerating={isGenerating}
          onClearMessages={handleClearMessages}
          onChannelChange={handleChannelChange}
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
  const { pathname } = useLocation()
  const { hasPermission } = usePermissions()
  const open = useAgentWorkbench((s) => s.open)
  const minimized = useAgentWorkbench((s) => s.minimized)
  const setMinimized = useAgentWorkbench((s) => s.setMinimized)
  const setOpen = useAgentWorkbench((s) => s.setOpen)

  // 本页 Agent 能力（§3.1B：每页可做的事不同，路由命中即展示；登录壳兜底为 null）
  const pageCtx = getPageAgentCapability(pathname)

  // RBAC（§5）：device_admin 无 report:read 时魔法按钮与浮窗均不渲染
  if (!hasPermission('report:read') || !open) return null

  /** 展开整页（§3.1B）：关闭浮窗并导航 /ai-chat，会话保留（同 localStorage） */
  const handleExpand = () => {
    setOpen(false)
    void navigate({ to: '/ai-chat' })
  }

  /**
   * 关闭浮窗（INT-2521 收窄的取消路径之一）：先以 `cancel` 语义注销浮窗宿主再收起——
   * 若整页 /ai-chat 仍开着，store 判定「非最后一个宿主」不取消，另一侧继续展示流式输出。
   */
  const handleClose = () => {
    useAgentRunStore.getState().detachHost('workbench', 'cancel')
    setOpen(false)
  }

  /** 模型供应商配置（INT-2493）：关闭浮窗并直达 /agent-providers */
  const handleOpenProviders = () => {
    setOpen(false)
    void navigate({ to: AGENT_PROVIDERS_ROUTE })
  }

  const floatingWindow = (
    <div className='bg-background fixed right-4 bottom-4 z-50 flex w-[min(28rem,calc(100vw-1rem))] max-h-[min(44rem,calc(100svh-5rem))] flex-col overflow-hidden rounded-2xl border shadow-2xl'>
      {/* 头行（§3.1B）：Demo 徽标 §3.10 落点②；INT-1153 二轮返工：炫彩
       * 「连接你的 agent」入口落头行右上角（最小化/展开/关闭按钮前，compact 适配头行高度） */}
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
        <div className='ms-auto flex items-center gap-1'>
          {hasPermission(AGENT_PROVIDER_MANAGE_PERMISSION) && (
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    aria-label={AGENT_PROVIDERS_COPY.pageTitle}
                    className='text-muted-foreground hover:text-foreground size-7'
                    onClick={handleOpenProviders}
                    type='button'
                    variant='ghost'
                  >
                    <KeyRound className='size-4' />
                  </Button>
                }
              />
              <TooltipContent>
                <p>{AGENT_PROVIDERS_COPY.pageTitle}</p>
              </TooltipContent>
            </Tooltip>
          )}
          <AgentConnectButton compact />
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
            onClick={handleClose}
            type='button'
            variant='ghost'
          >
            <X className='size-4' />
          </Button>
        </div>
      </div>

      {/* 会话区 + 输入区（浮窗内高度受限用更紧凑间距，§3.1B） */}
      <div className='flex min-h-0 flex-1 flex-col overflow-hidden'>
        <AgentWorkbenchSession pageCtx={pageCtx} />
      </div>
    </div>
  )

  return createPortal(
    minimized ? <AgentWorkbenchCapsule /> : floatingWindow,
    document.body
  )
}
