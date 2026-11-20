/**
 * 历史会话目录（application 层用例）：GET /agent/sessions 拉取当前用户的会话列表。
 * 服务端按最近活跃倒序；发送新消息后标题可能变化，交给 query 重新拉取。
 */
import { useQuery } from '@tanstack/react-query'

import { listAgentSessions } from '@/infrastructure/api/agentApi'

export const AGENT_SESSIONS_QUERY_KEY = ['agent', 'sessions'] as const

export function useAgentSessions(enabled = true) {
  return useQuery({
    queryKey: AGENT_SESSIONS_QUERY_KEY,
    queryFn: () => listAgentSessions(50),
    enabled,
    staleTime: 5_000,
  })
}
