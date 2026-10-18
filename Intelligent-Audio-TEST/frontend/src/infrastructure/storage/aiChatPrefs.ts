/**
 * 灵犀Agent 本地存储（infrastructure 层；照 newAPI lib/storage 平移，§3.7）。
 * localStorage envelope {version, data} + 上限/sanitize 截断（100 条 / 1MB、
 * 载入截断 120k/40k 字符 + 截断后缀 '\n\n[...]'）。
 * 键名照 §3.7：iatp:ai-chat:v1:config / messages / providers。
 */
import type { ChatMessage } from '../../domain/model/aiChat'

export const STORAGE_VERSION = 1
export const MAX_STORED_MESSAGES = 100
export const MAX_STORED_MESSAGES_BYTES = 1 * 1024 * 1024
export const MAX_LOADED_MESSAGES_CHARS = 120_000
export const MAX_LOADED_MESSAGE_CHARS = 40_000

const TRUNCATION_SUFFIX = '\n\n[...]'

interface Envelope<T> {
  version: number
  data: T
}

function safeJsonParse<T>(raw: string | null): T | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

/** 读 envelope 数据（版本校验：不匹配返回 null，避免跨版本结构破坏） */
export function loadPrefs<T>(key: string): T | null {
  const envelope = safeJsonParse<Envelope<T>>(localStorage.getItem(key))
  if (!envelope || envelope.version !== STORAGE_VERSION) return null
  return envelope.data
}

/** 写 envelope 数据 */
export function savePrefs<T>(key: string, data: T): void {
  try {
    const envelope: Envelope<T> = { version: STORAGE_VERSION, data }
    localStorage.setItem(key, JSON.stringify(envelope))
  } catch {
    // localStorage 配额满/隐私模式：静默失败（会话内仍可用，不阻断 UI）
  }
}

/** 单条消息内容截断（40k 字符，超限加截断后缀） */
export function sanitizeMessageContent(content: string): string {
  if (content.length <= MAX_LOADED_MESSAGE_CHARS) return content
  return `${content.slice(0, MAX_LOADED_MESSAGE_CHARS)}${TRUNCATION_SUFFIX}`
}

/** 历史消息列表整体截断（120k 字符总额 + 100 条上限 + 单条 40k） */
export function sanitizeMessages(messages: ChatMessage[]): ChatMessage[] {
  let totalChars = 0
  const result: ChatMessage[] = []
  for (const message of messages) {
    const sanitized: ChatMessage = {
      ...message,
      versions: message.versions.map((v) => ({
        ...v,
        content: sanitizeMessageContent(v.content),
      })),
    }
    totalChars += sanitized.versions.reduce(
      (sum, v) => sum + v.content.length,
      0
    )
    if (totalChars > MAX_LOADED_MESSAGES_CHARS) break
    result.push(sanitized)
    if (result.length >= MAX_STORED_MESSAGES) break
  }
  return result
}

/** 估算消息序列化字节（超 1MB 触发截断保存） */
export function estimateMessagesBytes(messages: ChatMessage[]): number {
  try {
    return JSON.stringify(messages).length
  } catch {
    return Number.MAX_SAFE_INTEGER
  }
}
