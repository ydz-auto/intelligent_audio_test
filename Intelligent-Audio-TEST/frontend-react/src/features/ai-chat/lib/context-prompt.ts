/**
 * 绑定上下文 → Agent 请求前缀（interfaces 层 lib/context-prompt）。
 * 报告工作模式选中的报告/任务原先只留在会话 config（徽标 + Studio 面板），
 * 请求体只有用户输入，模型只能按任务名/最近报告自行改选（选 #420 却分析 #426）。
 * 发送时把绑定上下文拼进本轮 message，用户气泡仍显示原输入。
 */
import type { ChatConfig } from '@/domain/models/aiChat'
import { BOUND_CONTEXT_COPY } from '@/features/ai-chat/constants'

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
