/**
 * AI 对话本地持久化（infrastructure 层；08_AI对话页.md §3.7）。
 * localStorage 三键（config/messages/providers，命名空间 iatp:ai-chat:v1）+ envelope{version,data}，
 * 上限与截断照 newAPI lib/storage 平移。2026-10-17 新口径：parameter-enabled 键废弃
 * （模型参数六项注册表整块移除），providers 为用户自管 LLM 供应商清单（§3.11，Demo 态）。
 */
import type {
  ChatConfig,
  ChatMessage,
  LlmProvider,
} from '@/domain/models/aiChat'
import { AI_CHAT_STORAGE_KEYS } from '@/domain/models/aiChat'

const STORAGE_VERSION = 1
export const MAX_STORED_MESSAGES = 100
export const MAX_STORED_MESSAGES_BYTES = 1024 * 1024 // 1MB
export const MAX_LOADED_MESSAGES_CHARS = 120_000
export const MAX_LOADED_MESSAGE_CHARS = 40_000
/** sanitize 截断后缀（照 newAPI） */
const TRUNCATION_SUFFIX = '\n\n[...]'

type StorageEnvelope<T> = { version: number; data: T }

/** 平台 Agent 会话存档（INT-2507）：服务端会话 id 与最近 run id，随会话一起持久化 */
export type StoredAgentSession = {
  sessionId: string
  runId?: string | null
}

function readEnvelope<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as StorageEnvelope<T>
    if (parsed.version !== STORAGE_VERSION) return null
    return parsed.data
  } catch {
    return null
  }
}

function writeEnvelope<T>(key: string, data: T): void {
  try {
    const envelope: StorageEnvelope<T> = { version: STORAGE_VERSION, data }
    window.localStorage.setItem(key, JSON.stringify(envelope))
  } catch {
    // 容量超限时静默丢弃（与 newAPI 同策略）
  }
}

/** 载入截断：整会话 120k 字符、单条 40k 字符，超限截断并补后缀 */
export function sanitizeMessages(messages: ChatMessage[]): ChatMessage[] {
  let totalChars = 0
  return messages.map((message) => {
    const content = message.versions[0]?.content ?? ''
    const needsTruncate = totalChars + content.length > MAX_LOADED_MESSAGES_CHARS
    if (needsTruncate) {
      return {
        ...message,
        versions: [
          {
            id: message.versions[0]?.id ?? message.key,
            content: content.slice(0, 80) + TRUNCATION_SUFFIX,
          },
        ],
      }
    }
    totalChars += content.length
    if (content.length > MAX_LOADED_MESSAGE_CHARS) {
      return {
        ...message,
        versions: [
          {
            id: message.versions[0]?.id ?? message.key,
            content: content.slice(0, MAX_LOADED_MESSAGE_CHARS) + TRUNCATION_SUFFIX,
          },
        ],
      }
    }
    return message
  })
}

export const aiChatPrefs = {
  loadConfig(): ChatConfig | null {
    return readEnvelope<ChatConfig>(AI_CHAT_STORAGE_KEYS.config)
  },
  saveConfig(config: ChatConfig): void {
    writeEnvelope(AI_CHAT_STORAGE_KEYS.config, config)
  },
  loadMessages(): ChatMessage[] | null {
    const data = readEnvelope<ChatMessage[]>(AI_CHAT_STORAGE_KEYS.messages)
    return data ? sanitizeMessages(data) : null
  },
  saveMessages(messages: ChatMessage[]): void {
    // 超限裁剪：仅保留最近 MAX_STORED_MESSAGES 条 / 1MB 内
    const clipped = messages.slice(-MAX_STORED_MESSAGES)
    writeEnvelope(AI_CHAT_STORAGE_KEYS.messages, clipped)
  },
  loadProviders(): LlmProvider[] | null {
    return readEnvelope<LlmProvider[]>(AI_CHAT_STORAGE_KEYS.providers)
  },
  saveProviders(providers: LlmProvider[]): void {
    writeEnvelope(AI_CHAT_STORAGE_KEYS.providers, providers)
  },
  /** 平台 Agent 会话 id（INT-2507）：刷新后继续同一服务端会话，不丢上下文 */
  loadAgentSession(): StoredAgentSession | null {
    return readEnvelope<StoredAgentSession>(AI_CHAT_STORAGE_KEYS.agentSession)
  },
  /** 传 null 表示结束会话（清空对话 / 服务端会话已失效），移除存档键 */
  saveAgentSession(session: StoredAgentSession | null): void {
    if (!session) {
      try {
        window.localStorage.removeItem(AI_CHAT_STORAGE_KEYS.agentSession)
      } catch {
        // 与写入同策略：存储不可用时静默
      }
      return
    }
    writeEnvelope(AI_CHAT_STORAGE_KEYS.agentSession, session)
  },
}
