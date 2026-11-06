/**
 * AI 对话会话全局 store（infrastructure/stores 层；08_AI对话页.md §3.1B/§3.7）。
 * 整页（/ai-chat）与全局浮窗（AgentWorkbench）两形态共享同一会话——§3.1B「两形态同 store
 * 不分裂会话」：浮窗在登录壳全局驻留（含 /ai-chat 页），若两形态各持一套 useChatState，
 * 会分别以 500ms 防抖写同一组 iatp:ai-chat:v1:* 键、先后互覆写丢消息。收敛为 zustand
 * 全局实例 + 单写入点（订阅持久化），保证同键单实例写、切换形态不丢会话。
 * URL 契约（§3.7）：/ai-chat?report={id} / /ai-chat?task={id} 首访无存档时绑定一次上下文
 * （同上下文沿用已存 config 保持会话；换上下文按 URL 重建）。
 *
 * INT-1936：上下文名称改由真实接口解析（报告 GET /reports/{id}、任务 GET /tasks/{id}），
 * 不再引用 infrastructure/mock/ai-chat-mock——生产路径上的假报告名会让用户在真实 id
 * 上看到演示名称。接口未命中 / 失败时降级为「报告 #id」/「任务 #id」并把
 * contextStatus 置 failed（页面据此标失败态），绝不回落到 mock 表。
 */
import { create } from 'zustand'

import type { ChatConfig, ChatMessage, ReportContextType } from '@/domain/models/aiChat'
import { DEFAULT_CONFIG } from '@/features/ai-chat/constants'
import { fetchReportDetail } from '@/infrastructure/api/reports-api'
import { fetchTaskDetail } from '@/infrastructure/api/tasks-list-api'
import { aiChatPrefs } from '@/infrastructure/storage/aiChatPrefs'

/** URL 契约上下文（§3.7：/ai-chat?report={id} / /ai-chat?task={id} / /ai-chat?reviewTask={id}&reviewCase={caseId}） */
export type AiChatInitialContext = {
  report?: string
  task?: string
  /** AI 复核会话「展开到 /ai-chat」进入态（08 §3.7 URL 契约扩展） */
  reviewTask?: string
  reviewCase?: string
}

/**
 * URL 上下文名称的解析状态（INT-1936）：
 * - idle：本次没有 URL 上下文（裸入口 / 浮窗），页头不显上下文条；
 * - loading：已按请求 id 绑定降级名，真实名称解析中；
 * - resolved：真实接口返回了名称；
 * - failed：接口未命中（404）或失败，保留「报告 #id」/「任务 #id」并由页面标失败态。
 */
export type AiChatContextStatus = 'idle' | 'loading' | 'resolved' | 'failed'

/** 取不到真实名称时的降级名（INT-1936；不回落 mock 表） */
export const CONTEXT_FALLBACK_LABEL: Record<
  'report' | 'task',
  (id: number) => string
> = {
  report: (id) => `报告 #${id}`,
  task: (id) => `任务 #${id}`,
}

/** URL 请求的上下文（报告 / 任务两类，id 已归一为数字） */
type RequestedContext = { kind: 'report' | 'task'; id: number }

/** 解析 URL 上下文 id（报告优先，其次任务 / 复核任务；非数字视为无上下文） */
function parseRequestedContext(
  context?: AiChatInitialContext
): RequestedContext | null {
  const report = context?.report
  const reportId = Number(report)
  if (report && Number.isFinite(reportId)) return { kind: 'report', id: reportId }

  const task = context?.task
  const taskId = Number(task)
  if (task && Number.isFinite(taskId)) return { kind: 'task', id: taskId }

  const reviewTask = context?.reviewTask
  const reviewTaskId = Number(reviewTask)
  if (reviewTask && Number.isFinite(reviewTaskId)) {
    return { kind: 'task', id: reviewTaskId }
  }
  return null
}

/** 已存 config 是否就是本次请求的上下文（同上下文保持会话，不同则按 URL 重建） */
function isSameContext(saved: ChatConfig, requested: RequestedContext): boolean {
  if (saved.reportContextId !== String(requested.id)) return false
  const savedIsTask = saved.reportContextType === 'task_context'
  return requested.kind === 'task' ? savedIsTask : !savedIsTask
}

/**
 * 同步初始 config（§3.7）：无 URL 上下文用存档，同上下文沿用存档；
 * 换上下文时保留用户的模型/供应商选择，上下文名先落降级名，真实名称随后异步补。
 */
function buildInitialConfig(context?: AiChatInitialContext): ChatConfig {
  const saved = aiChatPrefs.loadConfig()
  const requested = parseRequestedContext(context)
  if (!requested) return saved ?? { ...DEFAULT_CONFIG }
  if (saved && isSameContext(saved, requested)) return saved

  return {
    providerId: saved?.providerId,
    modelId: saved?.modelId,
    reportContextId: String(requested.id),
    reportContextLabel: CONTEXT_FALLBACK_LABEL[requested.kind](requested.id),
    reportContextType: requested.kind === 'task' ? 'task_context' : undefined,
  }
}

/** 报告类型 → 上下文类型（benchmark 归入测试报告口径；报告类型枚举见 domain/models/report） */
function toReportContextType(type: string | undefined): ReportContextType {
  return type === 'comparison' || type === 'secondary_comparison' ? type : 'task'
}

/** 真实接口解析上下文名称：label 为 null 表示接口返回了空名称（按未取到处理） */
async function resolveContextConfig(
  requested: RequestedContext
): Promise<{ label: string | null; type: ReportContextType }> {
  if (requested.kind === 'task') {
    const task = await fetchTaskDetail(requested.id)
    const name = task.name?.trim() ?? ''
    return { label: name || null, type: 'task_context' }
  }
  const report = await fetchReportDetail(requested.id)
  const name = report.name?.trim() ?? ''
  return { label: name || null, type: toReportContextType(report.type) }
}

type UpdateMessagesFn = (updater: (prev: ChatMessage[]) => ChatMessage[]) => void

type AiChatSessionState = {
  config: ChatConfig
  messages: ChatMessage[]
  /** 已应用的 URL 上下文 id（§3.7 首访/换上下文应用一次；防重复 set） */
  appliedContextKey?: string
  /** URL 上下文名称解析状态（INT-1936；页面据此标失败态） */
  contextStatus: AiChatContextStatus
  updateMessages: UpdateMessagesFn
  updateConfig: <K extends keyof ChatConfig>(key: K, value: ChatConfig[K]) => void
  clearMessages: () => void
  /** URL 契约（§3.7）：绑定 report/task 上下文（同上下文沿用存档保持会话；名称走真实接口解析） */
  applyInitialContext: (context?: AiChatInitialContext) => void
}

export const useAiChatSession = create<AiChatSessionState>()((set, get) => {
  /**
   * 真实名称解析（INT-1936）：响应回来时若上下文已切换（appliedContextKey 变化）则丢弃，
   * 避免慢请求把上一份报告名写到当前会话上。
   */
  const resolveContext = async (
    requested: RequestedContext,
    contextKey: string
  ): Promise<void> => {
    try {
      const resolved = await resolveContextConfig(requested)
      if (get().appliedContextKey !== contextKey) return
      set((state) => ({
        config: {
          ...state.config,
          ...(resolved.label ? { reportContextLabel: resolved.label } : {}),
          reportContextType: resolved.type,
        },
        contextStatus: resolved.label ? 'resolved' : 'failed',
      }))
    } catch {
      // 404 / 无权限 / 网络失败：保留降级名，标失败态（不回落 mock 表）
      if (get().appliedContextKey !== contextKey) return
      set({ contextStatus: 'failed' })
    }
  }

  return {
    config: aiChatPrefs.loadConfig() ?? { ...DEFAULT_CONFIG },
    messages: aiChatPrefs.loadMessages() ?? [],
    appliedContextKey: undefined,
    contextStatus: 'idle',
    updateMessages: (updater) =>
      set((state) => ({ messages: updater(state.messages) })),
    updateConfig: (key, value) =>
      set((state) => ({ config: { ...state.config, [key]: value } })),
    clearMessages: () => set({ messages: [] }),
    applyInitialContext: (context) => {
      if (!context?.report && !context?.task && !context?.reviewTask) return
      const requestedId = context.report ?? context.task ?? context.reviewTask
      if (get().appliedContextKey === requestedId) return
      const requested = parseRequestedContext(context)
      set({
        config: buildInitialConfig(context),
        appliedContextKey: requestedId,
        contextStatus: requested ? 'loading' : 'idle',
      })
      if (requested) void resolveContext(requested, requestedId ?? String(requested.id))
    },
  }
})

// 单写入点持久化（§3.7）：messages 500ms 防抖、config 即时；两形态共享同一实例，无互覆写。
let messageSaveTimer: number | null = null
useAiChatSession.subscribe((state, prev) => {
  if (state.messages !== prev.messages) {
    if (messageSaveTimer !== null) window.clearTimeout(messageSaveTimer)
    messageSaveTimer = window.setTimeout(() => {
      aiChatPrefs.saveMessages(state.messages)
    }, 500)
  }
  if (state.config !== prev.config) {
    aiChatPrefs.saveConfig(state.config)
  }
})
