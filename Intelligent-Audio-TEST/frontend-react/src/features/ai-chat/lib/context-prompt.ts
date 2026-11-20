/**
 * 绑定上下文 → Agent 请求前缀（interfaces 层 lib/context-prompt）。
 * 报告工作模式选中的报告/任务原先只留在会话 config（徽标 + Studio 面板），
 * 请求体只有用户输入，模型只能按任务名/最近报告自行改选（选 #420 却分析 #426）。
 * 发送时把绑定上下文拼进本轮 message，用户气泡仍显示原输入。
 */
import type { ChatConfig, ChatMessage } from '@/domain/models/aiChat'
import { CHAT_MESSAGE_STATUS } from '@/domain/models/aiChat'
import { BOUND_CONTEXT_COPY, SIDE_CONTEXT_COPY } from '@/features/ai-chat/constants'

export function buildBoundContextPrefix(config: ChatConfig): string | null {
  const id = config.reportContextId?.trim()
  if (!id) return null

  const kind = BOUND_CONTEXT_COPY.kindLabels[config.reportContextType ?? 'task']
  const label = config.reportContextLabel?.trim() ?? ''
  // 名称未解析时 label 就是降级名（如「报告 #420」），不再重复拼接
  const name = label && !label.includes(`#${id}`) ? `「${label}」` : ''

  return BOUND_CONTEXT_COPY.prefaceTemplate
    .replaceAll('{kind}', kind)
    .replace('{id}', id)
    .replace('{name}', name)
}

/**
 * 侧边会话上下文前缀（照 Codex 侧边对话）：把主对话最近若干条拼成本轮请求的前缀，
 * 让侧边线程「读得到」主线程上下文，但侧边问答只落在侧边会话、不写回主对话。
 * 无可带内容时返回 null（不注入空前缀）。
 */
export function buildSideConversationContext(
  messages: ChatMessage[]
): string | null {
  const lines: string[] = []
  for (const message of messages) {
    if (message.from !== 'user' && message.from !== 'assistant') continue
    if (
      message.status === CHAT_MESSAGE_STATUS.LOADING ||
      message.status === CHAT_MESSAGE_STATUS.ERROR
    ) {
      continue
    }
    const content = (message.versions[message.versions.length - 1]?.content ?? '').trim()
    if (!content) continue
    const clipped =
      content.length > SIDE_CONTEXT_COPY.maxCharsPerMessage
        ? `${content.slice(0, SIDE_CONTEXT_COPY.maxCharsPerMessage)}…`
        : content
    lines.push(`${SIDE_CONTEXT_COPY.roleLabels[message.from]}：${clipped}`)
  }

  const recent = lines.slice(-SIDE_CONTEXT_COPY.maxMessages)
  if (recent.length === 0) return null
  return `${SIDE_CONTEXT_COPY.preface}\n\n${recent.join('\n')}`
}
