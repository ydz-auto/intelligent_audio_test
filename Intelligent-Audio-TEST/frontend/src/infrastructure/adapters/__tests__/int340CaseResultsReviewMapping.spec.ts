/**
 * INT-340 回归（P1-3）：用例结果 case-results 适配器透传人工复核字段。
 *
 * 缺陷背景：后端 case-results 端点已返回 reviewed / reviewed_by_user_id /
 * reviewed_at / last_review_comment / last_review_action / review_history，
 * 但 toExecutionResult 未映射且 CaseExecutionResult 未声明 → 前端 r.reviewed
 * 恒 undefined →「已复核」徽标 / 复核历史永不渲染（浏览器实测阻断）。
 * 本测试锁定 snake_case → camelCase 映射不被回退。
 */
import { describe, it, expect } from 'vitest'
import { toCaseResults } from '../taskAdapter'

describe('INT-340：toCaseResults 人工复核字段映射', () => {
  it('snake_case 复核字段 → camelCase（reviewed 标记 + 留痕历史）', () => {
    const domain = toCaseResults({
      task_id: '101',
      case_id: 'INT340-C1',
      case_name: '用例1',
      results: [
        {
          id: 5001,
          device_id: 7,
          device_name: '设备A',
          execution_status: 'completed',
          reviewed: true,
          reviewed_by_user_id: 42,
          reviewed_at: '2026-10-16T09:00:00',
          last_review_comment: '复核通过',
          last_review_action: 'execution_status:failed→completed',
          review_history: [
            {
              id: 9001,
              result_id: 5001,
              field_name: 'execution_status',
              old_value: 'failed',
              new_value: 'completed',
              comment: '复核通过',
              created_by_user_id: 42,
              created_at: '2026-10-16T09:00:00',
            },
          ],
        },
        {
          id: 5002,
          device_id: 8,
          device_name: '设备B',
          execution_status: 'failed',
          reviewed: false,
        },
      ],
    })
    const [r1, r2] = domain.results
    // 已复核结果
    expect(r1.reviewed).toBe(true)
    expect(r1.reviewedByUserId).toBe(42)
    expect(r1.reviewedAt).toBe('2026-10-16T09:00:00')
    expect(r1.lastReviewComment).toBe('复核通过')
    expect(r1.lastReviewAction).toBe('execution_status:failed→completed')
    expect(r1.reviewHistory).toHaveLength(1)
    expect(r1.reviewHistory?.[0]).toMatchObject({
      id: 9001,
      resultId: 5001,
      fieldName: 'execution_status',
      oldValue: 'failed',
      newValue: 'completed',
      comment: '复核通过',
      createdAt: '2026-10-16T09:00:00',
    })
    // 未复核结果（reviewed=false 显式）
    expect(r2.reviewed).toBe(false)
    expect(r2.reviewHistory).toBeUndefined()
  })

  it('未复核结果缺省容错（reviewed 缺省 undefined、备注缺省 null）', () => {
    const domain = toCaseResults({
      task_id: '102',
      case_id: 'INT340-C2',
      case_name: '用例2',
      results: [{ id: 6001, device_id: 9, execution_status: 'failed' }],
    })
    const [r] = domain.results
    expect(r.reviewed).toBeUndefined()
    expect(r.reviewHistory).toBeUndefined()
    expect(r.lastReviewComment).toBeNull()
    expect(r.lastReviewAction).toBeNull()
  })
})
