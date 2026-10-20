/**
 * INT-255：usePublishedTasks 列表加载错误态单测（错误态与空态分离）。
 *
 * 锁定契约：
 * 1. fetchList 失败 → loadError 置位（type 走 ListLoadErrorType 枚举，拒绝字符串魔法值），不落空态；
 * 2. 网络不可达（fetch 拒绝、无 HTTP/业务信封）→ NETWORK；服务端错误（业务系统错误码 3xx / HTTP 5xx）→ SERVER；
 * 3. 成功加载 → loadError 清空；
 * 4. 失败后重试成功 → 错误态清除、恢复正常列表。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const publishedTasksApi = vi.hoisted(() => ({
  getAll: vi.fn(),
  getOne: vi.fn(),
  publish: vi.fn(),
  execute: vi.fn(),
  createVersion: vi.fn(),
  archive: vi.fn(),
  update: vi.fn(),
}))

vi.mock('@/infrastructure/api', () => ({ publishedTasksApi }))

import { usePublishedTasks } from '../usePublishedTasks'
import { ListLoadErrorType } from '../../../domain/enums'

const PAGE_EMPTY = { items: [], total: 0, page: 1, perPage: 10, pages: 0 }
const PAGE_ONE = {
  items: [{ id: 1, name: '任务A', status: 'published', benchmark: false, version: 1, isCurrent: true }],
  total: 1, page: 1, perPage: 10, pages: 1,
}

beforeEach(() => {
  vi.clearAllMocks()
  publishedTasksApi.getAll.mockResolvedValue(PAGE_EMPTY)
})

describe('usePublishedTasks 列表加载错误态（INT-255）', () => {
  it('网络不可达（fetch 拒绝、无业务信封）→ loadError=NETWORK', async () => {
    publishedTasksApi.getAll.mockRejectedValue(new TypeError('Failed to fetch'))
    const pt = usePublishedTasks()
    await pt.fetchList()

    expect(pt.loadError).not.toBeNull()
    expect(pt.loadError?.type).toBe(ListLoadErrorType.NETWORK)
  })

  it('服务端错误（业务系统错误码 3xx）→ loadError=SERVER', async () => {
    publishedTasksApi.getAll.mockRejectedValue(Object.assign(new Error('Internal error'), { code: 304 }))
    const pt = usePublishedTasks()
    await pt.fetchList()

    expect(pt.loadError?.type).toBe(ListLoadErrorType.SERVER)
  })

  it('服务端错误（HTTP 5xx 状态）→ loadError=SERVER', async () => {
    publishedTasksApi.getAll.mockRejectedValue(Object.assign(new Error('Bad gateway'), { status: 502 }))
    const pt = usePublishedTasks()
    await pt.fetchList()

    expect(pt.loadError?.type).toBe(ListLoadErrorType.SERVER)
  })

  it('成功加载 → loadError 清空，items/total 写入', async () => {
    publishedTasksApi.getAll.mockResolvedValue(PAGE_ONE)
    const pt = usePublishedTasks()
    await pt.fetchList()

    expect(pt.loadError).toBeNull()
    expect(pt.items).toHaveLength(1)
    expect(pt.total).toBe(1)
  })

  it('失败后重试成功 → 错误态清除、恢复正常列表', async () => {
    publishedTasksApi.getAll
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(PAGE_ONE)
    const pt = usePublishedTasks()
    await pt.fetchList()
    expect(pt.loadError?.type).toBe(ListLoadErrorType.NETWORK)

    await pt.fetchList()
    expect(pt.loadError).toBeNull()
    expect(pt.items).toHaveLength(1)
  })
})
