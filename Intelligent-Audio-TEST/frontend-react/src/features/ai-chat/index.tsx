/**
 * /ai-chat AI 对话页（Agent 工作台）（interfaces 层；08_AI对话页.md §3.1 三段式装配）。
 * 顶部条 / 全高滚动会话区 / 底部输入区；报告工作模式双栏为增强态变体（§3.6）。
 * INT-2473 接线：报告工作模式放开，右栏为真实 Report Studio 文档面板
 * （取数 → 起草 → 版本 → 导出）；输入区左挂报告上下文选择器，数据走真实
 * GET /reports + GET /tasks，绑定后写入会话 config.reportContext*。
 */
import { Badge } from '@/components/ui/badge'
import { PanelRight } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

import { AgentConnectButton } from '@/components/layout/components/agent-connect-button'

import {
  normalizeChatChannel,
  type ChatChannel,
  type ChatConfig,
  type ReportContextOption,
} from '@/domain/models/aiChat'
import { useChatHandler } from '@/features/ai-chat/hooks/use-chat-handler'
import { useAgentRunHost } from '@/application/agent/use-agent-run'
import { useTaskReportId } from '@/application/reports/use-report-studio'
import { useChatConversation } from '@/features/ai-chat/hooks/use-chat-conversation'
import { useChatState } from '@/features/ai-chat/hooks/use-chat-state'
import { useLlmProviders } from '@/features/ai-chat/hooks/use-llm-providers'
import { useReportContextQueries } from '@/features/ai-chat/hooks/use-report-context'
import { AiChat } from '@/features/ai-chat/components/chat/ai-chat'
import { AiChatInput } from '@/features/ai-chat/components/input/ai-chat-input'
import {
  ReportContextSelector,
  type SelectedContext,
} from '@/features/ai-chat/components/input/report-context-selector'
import { ProviderManager } from '@/features/ai-chat/components/input/provider-manager'
import { DocumentPanel } from '@/features/ai-chat/components/studio/document-panel'
import { DEFAULT_CHAT_CHANNEL, DEMO_COPY } from '@/features/ai-chat/constants'
import {
  useAiChatSession,
  type AiChatContextStatus,
} from '@/infrastructure/stores/aiChatSessionStore'

/**
 * URL 上下文条（INT-1936）：显示 /ai-chat?report={id} / ?task={id} 绑定的上下文。
 * 名称来自真实接口（报告 / 任务单查），解析失败时保留「报告 #id」/「任务 #id」并标失败态——
 * 生产路径不显示任何演示名称。无 URL 上下文（裸入口 / 浮窗）时整块不渲染。
 */
function ChatContextBadge({
  config,
  status,
}: {
  config: ChatConfig
  status: AiChatContextStatus
}) {
  if (!config.reportContextId) return null
  const id = config.reportContextId
  const isTask = config.reportContextType === 'task_context'
  const kindLabel = isTask ? '任务' : '报告'
  const label = config.reportContextLabel ?? `${kindLabel} #${id}`
  const tooltip =
    status === 'failed'
      ? `${kindLabel} #${id} 不存在或加载失败，已用编号占位`
      : status === 'loading'
        ? `正在解析${kindLabel}上下文…`
        : `当前对话绑定的${kindLabel}：${label}`

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Badge
            className='max-w-[16rem] cursor-help truncate'
            data-chat-context-status={status}
            variant={status === 'failed' ? 'destructive' : 'secondary'}
          >
            {label}
          </Badge>
        }
      />
      <TooltipContent>
        <p>{tooltip}</p>
      </TooltipContent>
    </Tooltip>
  )
}

type AiChatPageProps = {
  /** URL 契约：/ai-chat?report={id} / /ai-chat?task={id} / /ai-chat?reviewTask={id}&reviewCase={caseId}（§3.7） */
  initialContext?: {
    report?: string
    task?: string
    /** AI 复核会话「展开到 /ai-chat」进入态（08 §3.7 URL 契约扩展，INT-1064） */
    reviewTask?: string
    reviewCase?: string
  }
}

/** 报告工作模式开关（INT-2473：Report Studio 前端接线完成，默认可用） */
const REPORT_WORK_MODE_ENABLED = true

export function AiChatPage({ initialContext }: AiChatPageProps) {
  // 宿主登记（INT-2521 收窄）：离开 /ai-chat 路由是明确的取消语义；浮窗若仍开着，
  // 由 store 判断「最后一个宿主才取消」，不误伤另一宿主。
  useAgentRunHost('page', 'cancel')

  const {
    config,
    messages,
    contextStatus,
    initialPrompt,
    isLoadingMessages,
    updateMessages,
    updateConfig,
    clearMessages,
  } = useChatState(initialContext)

  // 平台 Agent 会话 / run（报告工作模式读待审批写操作数）
  const agentSessionId = useAiChatSession((state) => state.agentSessionId)
  const agentRunId = useAiChatSession((state) => state.agentRunId)

  // 报告上下文选择器（真实 GET /reports + GET /tasks）
  const {
    groups: contextGroups,
    options: contextOptions,
    isLoading: isContextLoading,
    isError: isContextError,
    refetch: refetchContext,
  } = useReportContextQueries()

  /** 任务上下文 → 该任务的报告 id（Studio 文档挂在报告上） */
  const isTaskContext = config.reportContextType === 'task_context'
  const contextTaskId = Number(config.reportContextId)
  const taskReportQuery = useTaskReportId(
    isTaskContext && Number.isFinite(contextTaskId) ? contextTaskId : 0
  )
  const boundReportId = isTaskContext
    ? (taskReportQuery.data ?? null)
    : config.reportContextId && Number.isFinite(Number(config.reportContextId))
      ? Number(config.reportContextId)
      : null
  /**
   * 任务 → 报告解析态：解析中 / 接口失败要与「该任务没有报告」「未绑定上下文」
   * 分开显示（404 = 该任务确实没有报告，由 fetchReportIdByTask 吞成 null）。
   */
  const isTaskResolvePending = isTaskContext && taskReportQuery.isLoading
  const taskResolveError =
    isTaskContext && taskReportQuery.isError
      ? taskReportQuery.error instanceof Error
        ? taskReportQuery.error.message
        : '任务关联报告解析失败'
      : null

  const selectedContextOption = contextOptions.find(
    (option) => option.id === config.reportContextId
  )
  const selectedContext: SelectedContext | null = config.reportContextId
    ? {
        id: config.reportContextId,
        label:
          config.reportContextLabel ??
          `${isTaskContext ? '任务' : '报告'} #${config.reportContextId}`,
        badge: selectedContextOption?.badge ?? '',
        type: config.reportContextType ?? 'task',
      }
    : null

  /** 绑定 / 切换报告上下文：写会话 config（同一会话内的上下文，不重开会话） */
  const handleSelectContext = (option: ReportContextOption) => {
    updateConfig('reportContextId', option.id)
    updateConfig('reportContextLabel', option.label)
    updateConfig('reportContextType', option.type)
  }

  const contextSelector = (
    <ReportContextSelector
      groups={contextGroups}
      isError={isContextError}
      isLoading={isContextLoading}
      onRetry={refetchContext}
      onSelect={handleSelectContext}
      value={selectedContext}
    />
  )

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

  /** 配置即用（§3.11/INT-1032 走查）：供应商带模型而会话未选模型/所选模型已不在
   * 清单时自动落首个模型——添加供应商后无需再手动选模型即可对话；手动切换模型后
   * 命中校验、效果不再覆写。 */
  useEffect(() => {
    if (!currentProvider) return
    const modelValid = currentProvider.models.includes(config.modelId ?? '')
    if (currentProvider.models.length > 0 && !modelValid) {
      updateConfig('providerId', currentProvider.id)
      updateConfig('modelId', currentProvider.models[0])
    }
  }, [currentProvider, config.modelId, updateConfig])

  /** 对话通道（INT-2457）：默认平台 Agent；自带供应商为降级模式 */
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
    // 平台通道同时结束会话上下文（下次发送新建会话，避免服务端残留旧历史）
    resetChat()
    clearMessages()
  }

  return (
    <div className='relative flex size-full min-h-0 flex-col overflow-hidden'>
      {/* 顶部条（shrink-0，§3.1/§3.2）；Demo 徽标 §3.10 落点①；INT-1153 二轮返工：
       * 炫彩「连接你的 agent」入口落右上角（标题区右侧），点击跳转 /agent-connect */}
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
            <ChatContextBadge config={config} status={contextStatus} />
          </div>
          <p className='text-muted-foreground hidden text-xs sm:block'>
            用自然语言驱动平台全部能力：报告、用例、任务、设备、日志
          </p>
        </div>
        <div className='flex shrink-0 items-center gap-2'>
          <AgentConnectButton />
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
      </div>

      {/* 会话区 + 报告工作模式双栏（§3.6：Agent 后端立项前整块不渲染） */}
      {REPORT_WORK_MODE_ENABLED && workModeOpen ? (
        <div className='relative flex min-h-0 flex-1'>
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
                  runPhase={runPhase}
                />
              </div>
              <div className='shrink-0'>
                <AiChatInput
                  channel={channel}
                  compact
                  config={config}
                  contextSlot={contextSelector}
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
                  textareaRef={textareaRef}
                  value={draftText}
                />
              </div>
            </div>
            {/*
             * lg 以下：文档面板改为覆盖式抽屉（右对齐，占宽 ≤34rem），宽屏才与会话并排。
             * 原来 <lg 直接 hidden 右栏 → 「报告工作模式」在 <1024px 是死按钮（UX 审计 P2-1）。
             */}
            <div className='bg-background absolute inset-y-0 right-0 z-30 block w-full max-w-[34rem] min-h-0 min-w-0 shadow-xl lg:static lg:z-auto lg:w-auto lg:max-w-none lg:bg-transparent lg:shadow-none'>
              <DocumentPanel
                agentSessionId={agentSessionId}
                onClose={() => setWorkModeOpen(false)}
                onRetryResolve={() => void taskReportQuery.refetch()}
                reportId={boundReportId}
                resolveError={taskResolveError}
                resolvePending={isTaskResolvePending}
                runId={agentRunId}
                sourceId={config.reportContextId ?? null}
                sourceKind={
                  config.reportContextId
                    ? isTaskContext
                      ? 'task'
                      : 'report'
                    : null
                }
                sourceLabel={config.reportContextLabel}
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
              runPhase={runPhase}
            />
          </div>

          {/* 输入区（max-w-4xl 居中钳制，§3.1） */}
          <div className='mx-auto w-full max-w-4xl'>
            <AiChatInput
              channel={channel}
              config={config}
              contextSlot={contextSelector}
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
