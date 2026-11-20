/**
 * 当前 run 的待审批写操作（interfaces 层 hooks；INT-2473「与审批卡联动」）。
 * 生成 / 导出等写操作由 Agent Loop 落 agent_approval，审批前不执行；工作台文档面板
 * 读取同一 run 的待审批提案数，提示「写操作待审批 N 项」，批准后文档版本 / 导出
 * 产物才会出现。审批卡与决策流程属 INT-2472，本 hook 只读列表，不渲染审批交互。
 */
import { useQuery } from '@tanstack/react-query'

import type { AgentApproval } from '@/domain/models/agent'
import { listAgentApprovals } from '@/infrastructure/api/agentApi'

/** 待审批轮询间隔（ms）：run 在跑时审批状态可能随时变化 */
const APPROVAL_POLL_INTERVAL_MS = 5_000

export function pendingApprovals(approvals: AgentApproval[]): AgentApproval[] {
  return approvals.filter((approval) => approval.status === 'PENDING')
}

export function usePendingApprovals(runId: string | null) {
  const query = useQuery({
    queryKey: ['agent', 'approvals', runId ?? ''],
    queryFn: () => listAgentApprovals(runId as string),
    enabled: Boolean(runId),
    staleTime: 0,
    retry: false,
    refetchInterval: runId ? APPROVAL_POLL_INTERVAL_MS : false,
  })

  const pending = pendingApprovals(query.data ?? [])
  return {
    pending,
    pendingCount: pending.length,
    isLoading: Boolean(runId) && query.isLoading,
    isError: Boolean(runId) && query.isError,
  }
}
