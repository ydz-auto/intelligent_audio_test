/**
 * 灵犀Agent 会话 Store（infrastructure/stores 单落位；08_AI对话页 §7 落位）。
 * 会话状态（config/messages/providers）单例共享——整页形态与全局浮窗共用，
 * 「切换形态不丢会话」（§3.1B 不分裂会话）；本地持久化（§3.7 localStorage，
 * 500ms 防抖 + 100 条/1MB 截断 sanitize）；Demo 态对话由用户自配 LLM 供应商直连（§3.11）。
 * Agent 工具链 / 报告工作模式数据交互面待后端立项（F6），不做假数据兜底。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type {
  ChatConfig,
  ChatMessage,
  LlmProvider,
} from '../domain/model/aiChat'
import { AI_CHAT_STORAGE_KEYS } from '../domain/model/aiChat'
import {
  DEFAULT_CONFIG,
  ERROR_MESSAGES,
  MESSAGE_STATUS,
} from '../domain/constants/aiChat'
import {
  loadPrefs,
  savePrefs,
  sanitizeMessages,
  estimateMessagesBytes,
} from '../infrastructure/storage/aiChatPrefs'
import { llmProviderApi } from '../infrastructure/api/llmProviderApi'

/** Demo 系统提示（主推全部能力；不注入杜撰报告事实，数值一律由真实回复承载） */
const SYSTEM_PROMPT =
  '你是智能音频测试平台的灵犀Agent，帮助用户完成平台各类事务：报告生成/对比/分析、用例生成、音频导入、任务管理、设备驱动、日志诊断等。回答简洁专业，不确定的信息不要编造。'

const STREAM_CHUNK_MS = 40
const STREAM_CHUNK_SIZE = 12

function createId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function buildChatHistory(
  messages: ChatMessage[],
  text: string
): Array<{ role: 'system' | 'user' | 'assistant'; content: string }> {
  const history: Array<{ role: 'system' | 'user' | 'assistant'; content: string }> = [
    { role: 'system', content: SYSTEM_PROMPT },
  ]
  for (const message of messages) {
    if (message.from !== 'user' && message.from !== 'assistant') continue
    if (message.status === 'loading' || message.status === 'error') continue
    const content = message.versions[message.versions.length - 1]?.content
    if (!content) continue
    history.push({
      role: message.from === 'user' ? 'user' : 'assistant',
      content,
    })
  }
  history.push({ role: 'user', content: text })
  return history
}

/** 消息成对删除：删除 assistant 消息时连同上一条 user 消息一并移除（playground 语义） */
function removeMessageByKey(
  messages: ChatMessage[],
  key: string
): ChatMessage[] {
  const index = messages.findIndex((m) => m.key === key)
  if (index === -1) return messages
  const from = messages[index].from
  const result = messages.filter((m) => m.key !== key)
  if (from === 'assistant') {
    for (let i = index - 1; i >= 0; i -= 1) {
      const prev = messages[i]
      if (prev.from === 'user') {
        return result.filter((m) => m.key !== prev.key)
      }
      break
    }
  }
  return result
}

export const useAiChatStore = defineStore('aiChat', () => {
  // ===== 会话配置（模型/供应商选择 + 报告上下文 id；无模型参数，§3.5/§3.7） =====
  const config = ref<ChatConfig>({
    ...DEFAULT_CONFIG,
    ...(loadPrefs<ChatConfig>(AI_CHAT_STORAGE_KEYS.config) || {}),
  })

  // ===== 消息列表（本地草稿缓存；云端会话待后端立项） =====
  const messages = ref<ChatMessage[]>(
    sanitizeMessages(
      loadPrefs<ChatMessage[]>(AI_CHAT_STORAGE_KEYS.messages) || []
    )
  )

  // ===== LLM 供应商清单（用户自管，§3.11） =====
  const providers = ref<LlmProvider[]>(
    loadPrefs<LlmProvider[]>(AI_CHAT_STORAGE_KEYS.providers) || []
  )

  const isGenerating = ref(false)
  const editingMessageKey = ref<string | null>(null)

  let runId: number | null = null
  let abortController: AbortController | null = null
  const timers: ReturnType<typeof setTimeout>[] = []
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  const defaultProvider = ref<LlmProvider | null>(null)

  function recomputeDefault(): void {
    defaultProvider.value =
      providers.value.find((p) => p.isDefault) ?? providers.value[0] ?? null
  }

  /** 当前会话供应商（config.providerId 命中或默认；§3.11 Demo 直连驱动对话） */
  function resolveCurrentProvider(): LlmProvider | null {
    return (
      providers.value.find((p) => p.id === config.value.providerId) ??
      defaultProvider.value
    )
  }

  /**
   * 配置即用（§3.11/INT-1032 走查对齐）：供应商带模型而会话未选模型/所选模型已不在
   * 清单时自动落首个模型——添加供应商后无需再手动选模型即可对话；手动切换模型后
   * 命中校验、效果不再覆写。整页与全局浮窗共用本 store，两形态同口径。
   */
  function autoSelectModel(): void {
    const currentProvider = resolveCurrentProvider()
    if (!currentProvider) return
    const modelValid = currentProvider.models.includes(config.value.modelId ?? '')
    if (currentProvider.models.length > 0 && !modelValid) {
      config.value = {
        ...config.value,
        providerId: currentProvider.id,
        modelId: currentProvider.models[0],
      }
      savePrefs(AI_CHAT_STORAGE_KEYS.config, config.value)
    }
  }

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      const next = sanitizeMessages(messages.value)
      if (estimateMessagesBytes(next) > 1 * 1024 * 1024) {
        savePrefs(AI_CHAT_STORAGE_KEYS.messages, next.slice(0, 100))
      } else {
        savePrefs(AI_CHAT_STORAGE_KEYS.messages, next)
      }
    }, 500)
  }

  function cancelTimers(): void {
    timers.forEach((id) => clearTimeout(id))
    timers.length = 0
  }

  // ===== 消息操作 =====
  function updateMessages(updater: (prev: ChatMessage[]) => ChatMessage[]): void {
    messages.value = updater(messages.value)
    scheduleSave()
  }

  function updateConfig(patch: Partial<ChatConfig>): void {
    config.value = { ...config.value, ...patch }
    savePrefs(AI_CHAT_STORAGE_KEYS.config, config.value)
  }

  /** URL 契约上下文绑定（§3.7：report/task 进入态） */
  function bindContext(context: { report?: string; task?: string }): void {
    if (context.report) {
      updateConfig({
        reportContextId: context.report,
        reportContextLabel: `报告 #${context.report}`,
        reportContextType: 'task',
      })
    } else if (context.task) {
      updateConfig({
        reportContextId: context.task,
        reportContextLabel: `任务 #${context.task}`,
        reportContextType: 'task_context',
      })
    }
  }

  function clearMessages(): void {
    messages.value = []
    try {
      localStorage.removeItem(AI_CHAT_STORAGE_KEYS.messages)
    } catch {
      // 隐私模式等场景忽略
    }
  }

  // ===== 发送 / 停止（Demo 直连用户供应商，§3.8 Demo 可先行） =====
  function stopGeneration(): void {
    if (runId === null) return
    runId = null
    cancelTimers()
    abortController?.abort()
    abortController = null
    updateMessages((prev) =>
      prev.map((message) => {
        if (
          message.status === MESSAGE_STATUS.LOADING ||
          message.status === MESSAGE_STATUS.STREAMING
        ) {
          return {
            ...message,
            status: MESSAGE_STATUS.COMPLETE,
            completedAt: Date.now(),
            durationMs: message.startedAt
              ? Date.now() - message.startedAt
              : 0,
          }
        }
        return message
      })
    )
    isGenerating.value = false
  }

  function sendChat(text: string, options: { historyMessages?: ChatMessage[]; appendUserMessage?: boolean } = {}): void {
    if (runId !== null) return
    const appendUserMessage = options.appendUserMessage ?? true
    const userKey = createId('user')
    const assistantKey = createId('assistant')
    const userMessage: ChatMessage = {
      key: userKey,
      from: 'user',
      versions: [{ id: `${userKey}-v1`, content: text }],
      createdAt: Date.now(),
    }
    const now = Date.now()
    const loadingMessage: ChatMessage = {
      key: assistantKey,
      from: 'assistant',
      versions: [{ id: `${assistantKey}-v1`, content: '' }],
      createdAt: now,
      startedAt: now,
      status: MESSAGE_STATUS.LOADING,
    }
    updateMessages((prev) => [
      ...(appendUserMessage ? [...prev, userMessage] : prev),
      loadingMessage,
    ])
    isGenerating.value = true

    const currentRunId = Date.now()
    runId = currentRunId
    const isInterrupted = () => runId !== currentRunId

    const patch = (partial: Partial<ChatMessage>) => {
      if (isInterrupted()) return
      updateMessages((prev) =>
        prev.map((message) =>
          message.key === assistantKey ? { ...message, ...partial } : message
        )
      )
    }

    const fail = (message: string) => {
      if (isInterrupted()) return
      patch({
        versions: [{ id: `${assistantKey}-v1`, content: message }],
        status: MESSAGE_STATUS.ERROR,
        completedAt: Date.now(),
      })
      runId = null
      abortController = null
      isGenerating.value = false
    }

    const currentProvider = resolveCurrentProvider()
    const currentModel = config.value.modelId
    if (!currentProvider || !currentProvider.baseUrl || !currentProvider.apiKey) {
      fail(ERROR_MESSAGES.noProviderChat)
      return
    }
    if (!currentModel) {
      fail(ERROR_MESSAGES.noModel)
      return
    }

    const abort = new AbortController()
    abortController = abort

    void (async () => {
      try {
        const content = await llmProviderApi.sendChatCompletion({
          baseUrl: currentProvider.baseUrl,
          apiKey: currentProvider.apiKey,
          model: currentModel,
          messages: buildChatHistory(
            options.historyMessages ?? messages.value,
            text
          ),
          signal: abort.signal,
        })
        if (isInterrupted()) return

        let index = 0
        patch({
          versions: [{ id: `${assistantKey}-v1`, content: '' }],
          status: MESSAGE_STATUS.STREAMING,
        })
        const stream = () => {
          if (isInterrupted()) return
          index += STREAM_CHUNK_SIZE
          patch({
            versions: [
              { id: `${assistantKey}-v1`, content: content.slice(0, index) },
            ],
          })
          if (index < content.length) {
            timers.push(setTimeout(stream, STREAM_CHUNK_MS))
          } else {
            patch({
              status: MESSAGE_STATUS.COMPLETE,
              completedAt: Date.now(),
              durationMs: Date.now() - (loadingMessage.startedAt ?? Date.now()),
            })
            runId = null
            abortController = null
            isGenerating.value = false
          }
        }
        timers.push(setTimeout(stream, 120))
      } catch (err) {
        if (isInterrupted()) return
        const message =
          err instanceof Error && err.message
            ? err.message
            : ERROR_MESSAGES.generic
        fail(message)
      }
    })()
  }

  // ===== 会话编排（发送 / 重生成 / 编辑 / 删除，§3.4） =====
  function handleSendMessage(text: string): void {
    const trimmed = text.trim()
    if (!trimmed) return
    sendChat(trimmed)
  }

  function handleRegenerateMessage(messageKey: string): void {
    const index = messages.value.findIndex((m) => m.key === messageKey)
    if (index === -1) return
    const history = messages.value.slice(0, index)
    const originalUser = [...history].reverse().find((m) => m.from === 'user')
    if (!originalUser) return
    sendChat(
      originalUser.versions[originalUser.versions.length - 1].content,
      { historyMessages: history, appendUserMessage: false }
    )
  }

  function handleEditMessage(messageKey: string): void {
    editingMessageKey.value = messageKey
  }

  function handleEditOpenChange(open: boolean): void {
    if (!open) editingMessageKey.value = null
  }

  function applyEdit(content: string, resend: boolean): void {
    const key = editingMessageKey.value
    if (!key) return
    const index = messages.value.findIndex((m) => m.key === key)
    if (index === -1) {
      editingMessageKey.value = null
      return
    }
    const target = messages.value[index]
    const trimmed = content.trim()
    const patched: ChatMessage = {
      ...target,
      versions: [
        ...target.versions,
        { id: `${key}-v${target.versions.length + 1}`, content: trimmed },
      ],
      status: MESSAGE_STATUS.COMPLETE,
    }
    const history = messages.value.slice(0, index)
    updateMessages((prev) => prev.map((m) => (m.key === key ? patched : m)))
    editingMessageKey.value = null
    if (resend) {
      sendChat(trimmed, {
        historyMessages: [...history, patched],
        appendUserMessage: false,
      })
    }
  }

  function handleDeleteMessage(messageKey: string): void {
    if (editingMessageKey.value === messageKey) editingMessageKey.value = null
    updateMessages((prev) => removeMessageByKey(prev, messageKey))
  }

  function handleUndoMessage(_messageKey: string): void {
    // 待后端立项：studio_restore_version（恢复产生新版本不覆盖，Studio §15.3）；立项前无操作
  }

  // ===== 供应商管理（§3.11） =====
  function addProvider(input: Omit<LlmProvider, 'id' | 'isDefault'>): LlmProvider {
    const created: LlmProvider = {
      ...input,
      id: createId('provider'),
      isDefault: providers.value.length === 0,
    }
    providers.value = [...providers.value, created]
    savePrefs(AI_CHAT_STORAGE_KEYS.providers, providers.value)
    recomputeDefault()
    autoSelectModel()
    return created
  }

  function updateProvider(id: string, patch: Partial<LlmProvider>): void {
    providers.value = providers.value.map((p) =>
      p.id === id ? { ...p, ...patch, id } : p
    )
    savePrefs(AI_CHAT_STORAGE_KEYS.providers, providers.value)
    recomputeDefault()
    autoSelectModel()
  }

  function removeProvider(id: string): void {
    providers.value = providers.value.filter((p) => p.id !== id)
    savePrefs(AI_CHAT_STORAGE_KEYS.providers, providers.value)
    recomputeDefault()
    autoSelectModel()
  }

  function setDefaultProvider(id: string): void {
    providers.value = providers.value.map((p) => ({
      ...p,
      isDefault: p.id === id,
    }))
    savePrefs(AI_CHAT_STORAGE_KEYS.providers, providers.value)
    recomputeDefault()
    autoSelectModel()
  }

  async function testConnection(
    provider: Pick<LlmProvider, 'baseUrl' | 'apiKey'>
  ): Promise<number> {
    const models = await llmProviderApi.fetchProviderModels(
      provider.baseUrl,
      provider.apiKey
    )
    return models.length
  }

  async function fetchModels(provider: LlmProvider): Promise<string[]> {
    const models = await llmProviderApi.fetchProviderModels(
      provider.baseUrl,
      provider.apiKey
    )
    updateProvider(provider.id, { models })
    return models
  }

  function initialize(): void {
    recomputeDefault()
    autoSelectModel()
  }

  return {
    // state
    config,
    messages,
    providers,
    defaultProvider,
    isGenerating,
    editingMessageKey,
    // 会话
    bindContext,
    updateConfig,
    clearMessages,
    sendChat,
    stopGeneration,
    handleSendMessage,
    handleRegenerateMessage,
    handleEditMessage,
    handleEditOpenChange,
    applyEdit,
    handleDeleteMessage,
    handleUndoMessage,
    // 供应商
    addProvider,
    updateProvider,
    removeProvider,
    setDefaultProvider,
    testConnection,
    fetchModels,
    initialize,
  }
})
