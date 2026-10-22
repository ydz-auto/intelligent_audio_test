/**
 * 通知名称解析防 404 SEVERE 单测（INT-1227 缺陷回归）：
 * - 名称解析以「最近列表快照」判存在性：快照命中用真实名；未命中（环境串扰引用
 *   不存在的任务/报告）降级「任务 #id / 报告 #id」且不发 GET /{resource}/{id}——
 *   杜绝浏览器网络 404 SEVERE 控制台报错。
 * - 列表拉取失败同样降级、不发详情请求；同名重复解析走缓存不再重复拉列表。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AppNotification } from '@/domain/models/notification'

const fetchTaskListMock = vi.hoisted(() => vi.fn())
const fetchReportListMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/tasks-list-api', () => ({
  fetchTaskList: fetchTaskListMock,
}))
vi.mock('@/infrastructure/api/reports-api', () => ({
  fetchReportList: fetchReportListMock,
}))

async function importApi() {
  return await import('@/infrastructure/api/notificationApi')
}

beforeEach(() => {
  // 重置模块级快照/缓存状态（vi.resetModules + 动态导入，每次全新模块实例）
  vi.resetModules()
  fetchTaskListMock.mockReset()
  fetchReportListMock.mockReset()
})

function makeTaskItem(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 'task:419:x',
    tab: 'notice',
    kind: 'task',
    title: '任务 #419',
    content: '进度 50%',
    createdAt: '2026-10-22T00:00:00Z',
    read: false,
    taskId: '419',
    ...overrides,
  }
}

describe('resolveTaskName（INT-1227 防 404）', () => {
  it('快照命中的真实任务解析为列表 name，不发 GET /tasks/{id}', async () => {
    fetchTaskListMock.mockResolvedValue({
      items: [{ id: 419, name: '真实任务A' }],
      total: 1,
    })
    const { resolveTaskName } = await importApi()
    await expect(resolveTaskName('419')).resolves.toBe('真实任务A')
    expect(fetchTaskListMock).toHaveBeenCalledTimes(1)
  })

  it('快照未命中（环境串扰的 1/2/4/5/6）降级「任务 #id」，不发详情请求', async () => {
    fetchTaskListMock.mockResolvedValue({
      items: [{ id: 419, name: '真实任务A' }],
      total: 1,
    })
    const { resolveTaskName } = await importApi()
    await expect(resolveTaskName('1')).resolves.toBe('任务 #1')
    await expect(resolveTaskName('2')).resolves.toBe('任务 #2')
    // 列表快照只拉一次，详情请求零次（无 /tasks/1、/tasks/2 404）
    expect(fetchTaskListMock).toHaveBeenCalledTimes(1)
  })

  it('列表拉取失败时降级「任务 #id」且不发详情请求', async () => {
    fetchTaskListMock.mockRejectedValue(new Error('网络错误'))
    const { resolveTaskName } = await importApi()
    await expect(resolveTaskName('419')).resolves.toBe('任务 #419')
  })

  it('同名重复解析走缓存，不再重复拉列表', async () => {
    fetchTaskListMock.mockResolvedValue({
      items: [{ id: 419, name: '真实任务A' }],
      total: 1,
    })
    const { resolveTaskName } = await importApi()
    await resolveTaskName('419')
    await resolveTaskName('419')
    expect(fetchTaskListMock).toHaveBeenCalledTimes(1)
  })
})

describe('resolveReportName（INT-1227 同款防 404）', () => {
  it('快照命中的真实报告解析为列表 name，不发 GET /reports/{id}', async () => {
    fetchReportListMock.mockResolvedValue({
      items: [{ id: 57, name: '真实报告R', task_name: 'T' }],
      total: 1,
      page: 1,
      per_page: 100,
      pages: 1,
    })
    const { resolveReportName } = await importApi()
    await expect(resolveReportName('57')).resolves.toBe('真实报告R')
    expect(fetchReportListMock).toHaveBeenCalledTimes(1)
  })

  it('快照未命中降级「报告 #id」，不发详情请求', async () => {
    fetchReportListMock.mockResolvedValue({
      items: [{ id: 57, name: '真实报告R', task_name: 'T' }],
      total: 1,
      page: 1,
      per_page: 100,
      pages: 1,
    })
    const { resolveReportName } = await importApi()
    await expect(resolveReportName('3')).resolves.toBe('报告 #3')
  })
})

describe('resolveNotificationNames 集成', () => {
  it('真实任务事件 → 标题更新为任务名', async () => {
    fetchTaskListMock.mockResolvedValue({
      items: [{ id: 419, name: '真实任务A' }],
      total: 1,
    })
    const { resolveNotificationNames } = await importApi()
    const resolved = await resolveNotificationNames(makeTaskItem())
    expect(resolved.title).toBe('真实任务A')
  })

  it('串扰事件引用不存在任务 → 保持降级标题「任务 #id」', async () => {
    fetchTaskListMock.mockResolvedValue({
      items: [{ id: 419, name: '真实任务A' }],
      total: 1,
    })
    const { resolveNotificationNames } = await importApi()
    const resolved = await resolveNotificationNames(
      makeTaskItem({ id: 'task:1:x', taskId: '1', title: '任务 #1' })
    )
    expect(resolved.title).toBe('任务 #1')
  })
})
