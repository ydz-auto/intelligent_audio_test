/**
 * features/ai-chat/lib/approval 纯函数测试（INT-2472 审计返修 P3-2/3/4 + P2 §9.4）：
 * 轮次 0 起转 1 起、内部步骤 UUID 截断、决策人只解析当前用户为「我」、
 * 提案影响对象数统计（>20 对象必须单条审批）；INT-2573 §9.4.1 拆单批次
 * 分组 / 序号 / all-or-nothing 状态 / 对象摘要。
 */
import { describe, expect, it } from 'vitest'

import { AGENT_APPROVAL_STATUS, type AgentApproval } from '@/domain/models/agent'
import {
  formatApprovalApprover,
  formatApprovalBatchHeader,
  formatApprovalBatchIndex,
  formatApprovalStepId,
  formatApprovalTurn,
  groupApprovalBatches,
  isBatchedApproval,
  resolveApprovalBatchObjectCount,
  resolveApprovalBatchState,
  summarizeApprovalObjectRef,
  summarizeApprovalTargets,
} from '@/features/ai-chat/lib/approval'

/** 只带 proposal 的最小审批单（统计函数只读 proposal.arguments） */
function approvalWith(argumentsValue: Record<string, unknown>) {
  return { proposal: { tool: 'x', arguments: argumentsValue } }
}

/** 拆单批次里的一张单（默认待审批、5 分钟后过期） */
function batchApproval(
  index: number,
  overrides: Partial<AgentApproval> = {}
): AgentApproval {
  return {
    id: `ap-${index}`,
    runId: 'r-1',
    toolCallId: 'tc-1',
    status: AGENT_APPROVAL_STATUS.PENDING,
    batchId: 'batch-1',
    batchIndex: index,
    batchTotal: 3,
    proposal: {
      tool: 'tag_group_manage',
      arguments: { ids: [`c-${index}`] },
      objectCount: 3,
    },
    objectRef: { kind: 'testcase', ids: [`c-${index}`] },
    expiresAt: new Date(Date.now() + 5 * 60_000).toISOString(),
    ...overrides,
  }
}

describe('formatApprovalTurn', () => {
  it('后端 turn 从 0 起，展示 1 起', () => {
    expect(formatApprovalTurn(0)).toBe('第 1 轮')
    expect(formatApprovalTurn(2)).toBe('第 3 轮')
  })

  it('缺失 / 非数字不展示', () => {
    expect(formatApprovalTurn(undefined)).toBeNull()
    expect(formatApprovalTurn(Number.NaN)).toBeNull()
  })
})

describe('formatApprovalStepId', () => {
  it('长 UUID 截断到前 8 位，短 id 原样展示', () => {
    expect(formatApprovalStepId('8dd2ee8d-1c4e-4b7a-9f00-112233445566')).toBe(
      '8dd2ee8d…'
    )
    expect(formatApprovalStepId('step-1')).toBe('step-1')
  })

  it('缺失 / 空白返回 null', () => {
    expect(formatApprovalStepId(undefined)).toBeNull()
    expect(formatApprovalStepId('   ')).toBeNull()
  })
})

describe('formatApprovalApprover', () => {
  it('当前用户显示「我」，其他用户不直出数字 id', () => {
    expect(formatApprovalApprover(7, '7')).toBe('我')
    expect(formatApprovalApprover(7, '8')).toBe('其他用户')
  })

  it('当前用户未知时按其他用户处理；决策人缺失返回 null', () => {
    expect(formatApprovalApprover(7, undefined)).toBe('其他用户')
    expect(formatApprovalApprover(undefined, '7')).toBeNull()
  })
})

describe('summarizeApprovalTargets（§9.4 批量粒度）', () => {
  it('顶层 *_ids 数组：按元素个数计，超过 20 判 overLimit', () => {
    const summary = summarizeApprovalTargets(
      approvalWith({ action: 'batch', device_ids: Array.from({ length: 21 }, (_, i) => i + 1) })
    )
    expect(summary.count).toBe(21)
    expect(summary.overLimit).toBe(true)
    expect(summary.fields).toEqual(['device_ids'])
    expect(summary.targets).toHaveLength(21)
    expect(summary.targets[0]).toBe('1')
  })

  it('嵌套 body.task_ids 同样识别；正好 20 个不超限', () => {
    const summary = summarizeApprovalTargets(
      approvalWith({
        action: 'merge',
        body: { task_ids: Array.from({ length: 20 }, (_, i) => i + 1) },
      })
    )
    expect(summary.count).toBe(20)
    expect(summary.overLimit).toBe(false)
    expect(summary.fields).toEqual(['body.task_ids'])
  })

  it('多个数组并存取最大值（不重复计数），对象数组按对象个数计', () => {
    const summary = summarizeApprovalTargets(
      approvalWith({
        device_ids: [1, 2, 3],
        body: { cases: [{ id: 'c-1' }, { id: 'c-2' }, { id: 'c-3' }, { id: 'c-4' }] },
      })
    )
    expect(summary.count).toBe(4)
    expect(summary.overLimit).toBe(false)
    expect(summary.fields).toEqual(['device_ids', 'body.cases'])
    expect(summary.targets).toEqual(['c-1', 'c-2', 'c-3', 'c-4'])
  })

  it('无对象数组 / 无参数：计数 0，不触发逐项核对', () => {
    expect(
      summarizeApprovalTargets(approvalWith({ section: 'USER_PROFILE', content: 'x' }))
    ).toMatchObject({ count: 0, overLimit: false, fields: [] })
    expect(summarizeApprovalTargets({ proposal: { tool: 'x' } })).toMatchObject({
      count: 0,
      overLimit: false,
    })
  })
})

describe('拆单批次（§9.4.1）', () => {
  it('isBatchedApproval：batchTotal > 1 才算批次，旧单张（缺字段 / 1）不算', () => {
    expect(isBatchedApproval({ batchTotal: 3 })).toBe(true)
    expect(isBatchedApproval({ batchTotal: 1 })).toBe(false)
    expect(isBatchedApproval({})).toBe(false)
  })

  it('formatApprovalBatchIndex：单卡标「本批第 i/N 条」，单张不展示', () => {
    expect(formatApprovalBatchIndex(2, 3)).toBe('本批第 2/3 条')
    expect(formatApprovalBatchIndex(1, 1)).toBeNull()
    expect(formatApprovalBatchIndex(undefined, 3)).toBeNull()
    expect(formatApprovalBatchIndex(1, undefined)).toBeNull()
  })

  it('resolveApprovalBatchState：全批准才待执行，任一拒绝 / 过期即整批不执行', () => {
    expect(
      resolveApprovalBatchState([
        batchApproval(1),
        batchApproval(2, { status: AGENT_APPROVAL_STATUS.APPROVED }),
      ])
    ).toBe(AGENT_APPROVAL_STATUS.PENDING)

    expect(
      resolveApprovalBatchState([
        batchApproval(1, { status: AGENT_APPROVAL_STATUS.APPROVED }),
        batchApproval(2, { status: AGENT_APPROVAL_STATUS.APPROVED }),
      ])
    ).toBe(AGENT_APPROVAL_STATUS.APPROVED)

    expect(
      resolveApprovalBatchState([
        batchApproval(1, { status: AGENT_APPROVAL_STATUS.APPROVED }),
        batchApproval(2, { status: AGENT_APPROVAL_STATUS.REJECTED }),
      ])
    ).toBe(AGENT_APPROVAL_STATUS.REJECTED)

    expect(
      resolveApprovalBatchState([
        batchApproval(1),
        batchApproval(2, { status: AGENT_APPROVAL_STATUS.EXPIRED }),
      ])
    ).toBe(AGENT_APPROVAL_STATUS.EXPIRED)

    // 本地倒计时到点也算过期：整批不执行，不停在「等审批」
    expect(
      resolveApprovalBatchState([
        batchApproval(1, { expiresAt: '2020-01-01T00:00:00Z' }),
        batchApproval(2),
      ])
    ).toBe(AGENT_APPROVAL_STATUS.EXPIRED)
  })

  it('summarizeApprovalObjectRef：kind + ids 摘要；非枚举范围显示「按范围执行」', () => {
    expect(summarizeApprovalObjectRef({ kind: 'testcase', ids: ['c-1'] })).toBe(
      'testcase · c-1'
    )
    expect(
      summarizeApprovalObjectRef({
        kind: 'audio',
        ids: ['a-1', 'a-2', 'a-3', 'a-4', 'a-5', 'a-6'],
      })
    ).toBe('audio · a-1, a-2, a-3, a-4, a-5…（共 6 个）')
    expect(summarizeApprovalObjectRef({ kind: 'testcase', ids: [] })).toBe(
      'testcase · 按范围执行'
    )
    expect(summarizeApprovalObjectRef(undefined)).toBeNull()
  })

  it('resolveApprovalBatchObjectCount：优先 proposal.objectCount，缺失时回退 ids 之和', () => {
    expect(
      resolveApprovalBatchObjectCount([batchApproval(1), batchApproval(2)])
    ).toBe(3)

    expect(
      resolveApprovalBatchObjectCount([
        batchApproval(1, { proposal: { tool: 'x' } }),
        batchApproval(2, { proposal: { tool: 'x' } }),
      ])
    ).toBe(2)

    // 有单缺 object_ref 时不猜数量
    expect(
      resolveApprovalBatchObjectCount([
        batchApproval(1, { proposal: { tool: 'x' } }),
        batchApproval(2, { proposal: { tool: 'x' }, objectRef: undefined }),
      ])
    ).toBeUndefined()
  })

  it('groupApprovalBatches：同批按 batchIndex 升序聚组、块落首卡位置、旧单张原样透传', () => {
    const blocks = groupApprovalBatches([
      batchApproval(2),
      { id: 'single', runId: 'r-1', status: AGENT_APPROVAL_STATUS.PENDING },
      batchApproval(1),
      batchApproval(3),
    ])

    expect(blocks.map((block) => block.kind)).toEqual(['batch', 'single'])
    const batch = blocks[0]
    expect(batch.kind).toBe('batch')
    if (batch.kind !== 'batch') return
    expect(batch.batchId).toBe('batch-1')
    expect(batch.approvals.map((item) => item.batchIndex)).toEqual([1, 2, 3])
    expect(batch.objectCount).toBe(3)
    expect(batch.state).toBe(AGENT_APPROVAL_STATUS.PENDING)
  })

  it('formatApprovalBatchHeader：单数 / 对象数 / 批次状态口径', () => {
    expect(
      formatApprovalBatchHeader(3, 21, AGENT_APPROVAL_STATUS.PENDING)
    ).toBe('本批 3 张单 · 对象 21 个 · 本批全部批准后才执行')
    expect(
      formatApprovalBatchHeader(3, undefined, AGENT_APPROVAL_STATUS.REJECTED)
    ).toBe('本批 3 张单 · 本批不执行（任一单被拒绝）')
    expect(
      formatApprovalBatchHeader(2, 2, AGENT_APPROVAL_STATUS.APPROVED)
    ).toBe('本批 2 张单 · 对象 2 个 · 本批已全部批准，待执行')
    expect(
      formatApprovalBatchHeader(2, 2, AGENT_APPROVAL_STATUS.EXPIRED)
    ).toBe('本批 2 张单 · 对象 2 个 · 本批不执行（任一单已过期）')
  })
})
