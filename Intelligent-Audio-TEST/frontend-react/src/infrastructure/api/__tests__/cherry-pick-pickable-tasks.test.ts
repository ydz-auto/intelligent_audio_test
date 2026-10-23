/**
 * 阶段 1 可挑选任务清单接线（INT-1509 / INT-1496 §8.1）：
 * GET /tasks/cherry-picks/pickable-tasks 的 DTO→Domain 映射、服务端排序参数透传、
 * 按 per_page 拉齐分页（「全选当前筛选」覆盖 total，不只首页）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setSessionExpiredHandler } from '@/infrastructure/api/client'
import {
  fetchAllPickableTasks,
  fetchPickableTaskOptions,
  fetchPickableTaskPage,
} from '@/infrastructure/api/cherry-pick-api'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function ok<T>(data: T): Response {
  return jsonResponse({ success: true, code: 0, message: 'ok', data })
}

function queueResponses(...responses: Response[]): void {
  fetchMock.mockImplementation(() => {
    const next = responses.shift()
    if (!next) throw new Error('fetch 调用超出 mock 队列')
    return Promise.resolve(next)
  })
}

function callUrl(index = 0): URL {
  const raw = (fetchMock.mock.calls[index] as [string, RequestInit])[0]
  return new URL(raw, 'http://localhost')
}

function pickableItem(id: number, name: string, count: number) {
  return {
    id,
    name,
    execution_status: 'completed',
    pickable_count: count,
    created_at: '2026-10-21T09:00:00',
  }
}

describe('pickable-tasks 阶段 1 数据源（INT-1509）', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    authTokenStore.clear()
    setSessionExpiredHandler(null)
  })

  it('fetchPickableTaskPage：DTO 映射 camelCase（pickable_count→count、execution_status→executionStatus）', async () => {
    queueResponses(
      ok({ items: [pickableItem(419, '任务419', 138)], total: 117, page: 1, per_page: 200 })
    )
    const page = await fetchPickableTaskPage({ page: 1, perPage: 200 })

    expect(page.total).toBe(117)
    expect(page.items).toEqual([
      {
        taskId: 419,
        taskName: '任务419',
        executionStatus: 'completed',
        createdAt: '2026-10-21T09:00:00',
        count: 138,
      },
    ])
    // 单次请求只打 pickable-tasks，不请求 candidates 做聚合
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(callUrl().pathname).toBe('/api/v1/tasks/cherry-picks/pickable-tasks')
  })

  it('fetchPickableTaskPage：服务端排序/过滤参数透传（sort_by/sort_order/status/keyword）', async () => {
    queueResponses(ok({ items: [], total: 0, page: 1, per_page: 50 }))
    await fetchPickableTaskPage({
      page: 1,
      perPage: 50,
      sortBy: 'created_at',
      sortOrder: 'desc',
      status: 'failed',
      keyword: '  拒识  ',
    })
    const url = callUrl()
    expect(url.searchParams.get('sort_by')).toBe('created_at')
    expect(url.searchParams.get('sort_order')).toBe('desc')
    expect(url.searchParams.get('status')).toBe('failed')
    expect(url.searchParams.get('keyword')).toBe('拒识')
  })

  it('fetchAllPickableTasks：total 超过单页上限时按 per_page 拉齐全部任务', async () => {
    queueResponses(
      ok({ items: [pickableItem(1, '任务1', 10)], total: 250, page: 1, per_page: 200 }),
      ok({ items: [pickableItem(2, '任务2', 20)], total: 250, page: 2, per_page: 200 })
    )
    const { items, total } = await fetchAllPickableTasks({ sortBy: 'status', sortOrder: 'asc' })

    expect(total).toBe(250)
    expect(items.map((t) => t.taskId)).toEqual([1, 2])
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(callUrl(1).searchParams.get('page')).toBe('2')
  })

  it('fetchPickableTaskOptions：「来源任务」下拉与清单同源（id/name）', async () => {
    queueResponses(
      ok({
        items: [pickableItem(419, '任务419', 138), pickableItem(418, '任务418', 62)],
        total: 2,
        page: 1,
        per_page: 200,
      })
    )
    const options = await fetchPickableTaskOptions()
    expect(options).toEqual([
      { id: 419, name: '任务419' },
      { id: 418, name: '任务418' },
    ])
    expect(callUrl().pathname).toBe('/api/v1/tasks/cherry-picks/pickable-tasks')
  })
})
