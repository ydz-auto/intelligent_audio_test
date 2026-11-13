/**
 * 待审批写操作筛选（INT-2473「与审批卡联动」）：文档面板只统计 PENDING，
 * 已批准 / 已拒绝 / 已过期不重复计入。
 */
import { describe, expect, it } from 'vitest'

import type { AgentApproval } from '@/domain/models/agent'
import { pendingApprovals } from '@/features/ai-chat/hooks/use-pending-approvals'

function approval(id: string, status: AgentApproval['status']): AgentApproval {
  return { id, runId: 'run-1', status }
}

describe('pendingApprovals', () => {
  it('只保留 PENDING', () => {
    const result = pendingApprovals([
      approval('a', 'PENDING'),
      approval('b', 'APPROVED'),
      approval('c', 'REJECTED'),
      approval('d', 'EXPIRED'),
      approval('e', 'PENDING'),
    ])
    expect(result.map((item) => item.id)).toEqual(['a', 'e'])
  })

  it('空列表返回空', () => {
    expect(pendingApprovals([])).toEqual([])
  })
})
