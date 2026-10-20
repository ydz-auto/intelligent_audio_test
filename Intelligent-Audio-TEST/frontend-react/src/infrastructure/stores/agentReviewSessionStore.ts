/**
 * AI 复核会话独立 store（infrastructure/stores 层；19 规范 §5.2 会话 scope + §5.9 树）。
 * 复核会话是任务/用例级有界会话：复用全局主会话同一会话引擎（LLM 供应商切换/消息渲染/流式）
 * 但**独立会话数据**——scope 键 `iatp:ai-chat:v1:review:{taskId}:{caseId}`，不写入全局
 * `iatp:ai-chat:v1:messages` 主会话（复核是有界任务，避免污染用户主对话历史）。
 * 关闭 Dialog 即释放（resetSession 清空该 scope）；「展开到 /ai-chat」时由调用方把本
 * scope 消息并入主会话（19 §5.2/08 §3.7）。
 */
import { create } from 'zustand'

import type { ChatConfig, ChatMessage } from '@/domain/models/aiChat'
import { DEFAULT_CONFIG } from '@/features/ai-chat/constants'

/** scope 键：iatp:ai-chat:v1:review:{taskId}:{caseId}（19 §5.2 独立会话数据键） */
export function agentReviewSessionKey(taskId: number, caseId: string): string {
  return `iatp:ai-chat:v1:review:${taskId}:${caseId}`
}

/** 复核会话数据（config = 模型/供应商选择；messages = 有界会话消息流） */
export interface AgentReviewSession {
  config: ChatConfig
  messages: ChatMessage[]
}

type UpdateMessagesUpdater = (prev: ChatMessage[]) => ChatMessage[]

type AgentReviewSessionState = {
  /** scopeKey → 会话数据（仅内存态；关闭 Dialog 即释放） */
  sessions: Record<string, AgentReviewSession>
  getSession: (taskId: number, caseId: string) => AgentReviewSession
  updateMessages: (
    taskId: number,
    caseId: string,
    updater: UpdateMessagesUpdater
  ) => void
  updateConfig: <K extends keyof ChatConfig>(
    taskId: number,
    caseId: string,
    key: K,
    value: ChatConfig[K]
  ) => void
  /** 关闭复核 Dialog 即释放该 scope（§5.2「关闭即释放」） */
  resetSession: (taskId: number, caseId: string) => void
}

export const useAgentReviewSessionStore = create<AgentReviewSessionState>()(
  (set, get) => ({
    sessions: {},
    getSession: (taskId, caseId) => {
      const key = agentReviewSessionKey(taskId, caseId)
      return get().sessions[key] ?? { config: { ...DEFAULT_CONFIG }, messages: [] }
    },
    updateMessages: (taskId, caseId, updater) =>
      set((state) => {
        const key = agentReviewSessionKey(taskId, caseId)
        const current = state.sessions[key] ?? {
          config: { ...DEFAULT_CONFIG },
          messages: [],
        }
        return {
          sessions: {
            ...state.sessions,
            [key]: { config: current.config, messages: updater(current.messages) },
          },
        }
      }),
    updateConfig: (taskId, caseId, key, value) =>
      set((state) => {
        const scopeKey = agentReviewSessionKey(taskId, caseId)
        const current = state.sessions[scopeKey] ?? {
          config: { ...DEFAULT_CONFIG },
          messages: [],
        }
        return {
          sessions: {
            ...state.sessions,
            [scopeKey]: {
              config: { ...current.config, [key]: value },
              messages: current.messages,
            },
          },
        }
      }),
    resetSession: (taskId, caseId) =>
      set((state) => {
        const key = agentReviewSessionKey(taskId, caseId)
        const { [key]: _removed, ...rest } = state.sessions
        void _removed
        return { sessions: rest }
      }),
  })
)
