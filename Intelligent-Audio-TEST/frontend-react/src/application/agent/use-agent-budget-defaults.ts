/**
 * 目标模式预算默认值（application 层用例）：GET /agent/budget-defaults。
 *
 * 默认值只用于输入区展示「留空生效」的口径，不是上限：Auto 允许用户在默认值
 * 之上上调（消耗用户自己的 token），前端不做上限校验。
 */
import { useQuery } from '@tanstack/react-query'

import { fetchAgentBudgetDefaults } from '@/infrastructure/api/agentApi'

export const AGENT_BUDGET_DEFAULTS_QUERY_KEY = ['agent', 'budget-defaults'] as const

/** 默认值来自服务端配置、不随会话变化：5 分钟内复用缓存 */
const BUDGET_DEFAULTS_STALE_MS = 5 * 60 * 1_000

/** `enabled=false` 时不请求（仅目标模式需要展示预算默认值） */
export function useAgentBudgetDefaults(enabled = true) {
  return useQuery({
    queryKey: AGENT_BUDGET_DEFAULTS_QUERY_KEY,
    queryFn: () => fetchAgentBudgetDefaults(),
    enabled,
    staleTime: BUDGET_DEFAULTS_STALE_MS,
  })
}
