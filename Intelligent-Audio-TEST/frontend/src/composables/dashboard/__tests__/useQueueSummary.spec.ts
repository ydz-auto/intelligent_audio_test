/**
 * INT-736：排队状态条——GET /tasks?status=queued 计数 + 队首 FIFO；列表端点异常时
 * 回退 /tasks/stats queued 计数（真实数据，非 mock）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useQueueSummary } from '../useQueueSummary'

const mocks = vi.hoisted(() => ({
  getAll: vi.fn(),
  getDomainStats: vi.fn(),
}))

vi.mock('@/composables/task/tasksPort', () => ({
  tasksPort: { getAll: mocks.getAll, getDomainStats: mocks.getDomainStats },
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useQueueSummary', () => {
  it('主路：/tasks?status=queued 计数 + 队首按创建时间升序', async () => {
    mocks.getAll.mockResolvedValue({
      items: [
        { id: 3, name: '任务C', status: 'queued', createdAt: '2026-10-18T10:00:00' },
        { id: 1, name: '任务A', status: 'queued', createdAt: '2026-10-18T08:00:00' },
        { id: 2, name: '任务B', status: 'queued', createdAt: '2026-10-18T09:00:00' },
      ],
      total: 3, page: 1, perPage: 20, pages: 1,
    })
    const q = useQueueSummary()
    await q.load()
    expect(q.count.value).toBe(3)
    expect(q.headName.value).toBe('任务A')
    expect(mocks.getAll).toHaveBeenCalledWith({ status: 'queued', page: 1, perPage: 20 })
    expect(mocks.getDomainStats).not.toHaveBeenCalled()
  })

  it('主路：空队列时 count=0、head 为空', async () => {
    mocks.getAll.mockResolvedValue({ items: [], total: 0, page: 1, perPage: 20, pages: 0 })
    const q = useQueueSummary()
    await q.load()
    expect(q.count.value).toBe(0)
    expect(q.headName.value).toBe('')
  })

  it('回退：/tasks 列表端点异常时取 /tasks/stats status_counts.queued（队首不可得）', async () => {
    mocks.getAll.mockRejectedValue(new Error('500 Internal Server Error'))
    mocks.getDomainStats.mockResolvedValue({
      total: 124, deletedTotal: 0,
      statusCounts: { queued: 5, running: 1, completed: 74, failed: 38 },
      typeCounts: { api: 124, e2e: 0, mixed: 0 },
      trend: [], granularity: 'day',
    })
    const q = useQueueSummary()
    await q.load()
    expect(q.count.value).toBe(5)
    expect(q.headName.value).toBe('')
    expect(mocks.getDomainStats).toHaveBeenCalledWith('day')
  })

  it('回退也失败时静默降级 0（不抛出）', async () => {
    mocks.getAll.mockRejectedValue(new Error('500'))
    mocks.getDomainStats.mockRejectedValue(new Error('500'))
    const q = useQueueSummary()
    await q.load()
    expect(q.count.value).toBe(0)
    expect(q.headName.value).toBe('')
  })
})
