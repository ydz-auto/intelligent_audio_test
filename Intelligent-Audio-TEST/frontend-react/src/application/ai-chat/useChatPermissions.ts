/**
 * AI 对话能力权限派生（application 层；08_AI对话页.md §5 表单一来源）。
 * 能力 → 权限码映射在 domain（AGENT_CAPABILITY_PERMISSIONS），本 hook 供
 * 空态 starter 过滤 / 报告工作模式显隐使用；report:update 为过渡口径（待后端立项替换）。
 */
import { usePermissions } from '@/application/hooks/use-permissions'
import { AGENT_CAPABILITY_PERMISSIONS } from '@/domain/models/aiChat'

export function useChatPermissions() {
  const { hasPermission } = usePermissions()

  return {
    canGenerate: hasPermission(AGENT_CAPABILITY_PERMISSIONS.generate),
    canCompare: hasPermission(AGENT_CAPABILITY_PERMISSIONS.compare),
    canRead: hasPermission(AGENT_CAPABILITY_PERMISSIONS.read),
    canUpdate: hasPermission(AGENT_CAPABILITY_PERMISSIONS.update),
    hasPermission,
  }
}
