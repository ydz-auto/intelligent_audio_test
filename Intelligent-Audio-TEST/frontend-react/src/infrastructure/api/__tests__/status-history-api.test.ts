/**
 * INT-2671 设备历史监控取数契约：fetchStatusHistory 按事件类型下推 event_type
 * （后端单值），多类型分次拉取后按时间倒序合并——只取最新一页再前端过滤时，
 * 高频 health_check 会把 online/offline/operation 挤出窗口，导致状态/操作页签恒空。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setSessionExpiredHandler } from '@/infrastructure/api/client'
import { fetchStatusHistory } from '@/infrastructure/api/devicesApi'
import { authTokenStore } from '@/infrastructure/storage/auth-token'

const fetchMock = vi.fn()

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function paginated(items: unknown[]): Response {
  return jsonResponse({
    success: true,
    code: 0,
    data: { items, total: items.length, page: 1, per_page: 200, pages: 1 },
  })
}

/** 后端 status-history 实响应行（_event_to_dict：无 device_name、无 result，有 success） */
function historyRow(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    device_id: 79,
    device_kind: 'test',
    event_type: 'online',
    from_status: 'offline',
    to_status: 'online',
    source: 'monitor',
    success: true,
    detail: null,
    created_at: '2026-11-19T11:19:08',
    ...overrides,
  }
}

function queueResponses(...responses: Response[]): void {
  fetchMock.mockImplementation(() => {
    const next = responses.shift()
    if (!next) throw new Error('fetch 调用超出 mock 队列')
    return Promise.resolve(next)
  })
}

function callUrl(index: number): URL {
  const [url] = fetchMock.mock.calls[index] as [string, RequestInit]
  return new URL(url, 'http://localhost')
}

describe('fetchStatusHistory（INT-2671）', () => {
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

  it('未指定事件类型：单次请求不带 event_type（全量最新一页）', async () => {
    queueResponses(paginated([historyRow()]))
    const events = await fetchStatusHistory()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const url = callUrl(0)
    expect(url.pathname).toBe('/api/v1/test-devices/status-history')
    expect(url.searchParams.get('page')).toBe('1')
    expect(url.searchParams.get('per_page')).toBe('200')
    expect(url.searchParams.has('event_type')).toBe(false)
    expect(events).toHaveLength(1)
  })

  it('多类型按类型分次请求，逐类带 event_type 并合并后按时间倒序', async () => {
    queueResponses(
      paginated([historyRow({ id: 1, event_type: 'online', created_at: '2026-11-19T11:19:08' })]),
      paginated([historyRow({ id: 2, event_type: 'offline', created_at: '2026-11-20T09:00:00' })])
    )
    const events = await fetchStatusHistory({ eventTypes: ['online', 'offline'] })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(callUrl(0).searchParams.get('event_type')).toBe('online')
    expect(callUrl(1).searchParams.get('event_type')).toBe('offline')
    expect(events.map((event) => event.id)).toEqual([2, 1])
    expect(events.map((event) => event.eventType)).toEqual(['offline', 'online'])
  })

  it('success 布尔映射到 result；设备名不在事件行里（只有 device_id）', async () => {
    queueResponses(
      paginated([
        historyRow({ id: 1, success: true }),
        historyRow({ id: 2, success: false }),
        historyRow({ id: 3, success: null }),
      ])
    )
    const events = await fetchStatusHistory({ eventTypes: ['health_check'] })

    expect(events.map((event) => event.result)).toEqual(['success', 'failed', null])
    expect(events.every((event) => event.deviceId === 79)).toBe(true)
    expect(events.every((event) => !('deviceName' in event))).toBe(true)
  })

  it('per_page 不超过后端上限 500', async () => {
    queueResponses(paginated([]))
    await fetchStatusHistory({ eventTypes: ['operation'], perPage: 5000 })

    expect(callUrl(0).searchParams.get('per_page')).toBe('500')
  })

  it('重复事件类型去重，不重复发请求', async () => {
    queueResponses(paginated([historyRow()]))
    await fetchStatusHistory({ eventTypes: ['operation', 'operation'] })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(callUrl(0).searchParams.get('event_type')).toBe('operation')
  })
})
