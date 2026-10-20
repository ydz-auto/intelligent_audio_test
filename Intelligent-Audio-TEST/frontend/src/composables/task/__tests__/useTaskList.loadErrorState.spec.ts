/**
 * INT-288：useTaskList 加载态 / 错误态回归。
 *
 * 缺陷：fetchTasks 失败仅 console.error，页面误导性显示「没有找到任务」空态，
 * 拉取期间零指示。验收（issue 原文）：加载态、错误态（错误条 + 重试）、
 * 错误与空态视觉区分；失败时保留旧数据不清空。
 * 锁定契约：
 * 1. isLoading 拉取期间 true，结束复位；
 * 2. 失败 → error 暴露用户可见文案，isLoading 复位，旧数据保留不清空；
 * 3. 成功后 error 清空。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAll: vi.fn(),
  getDomainStats: vi.fn(),
  getOptions: vi.fn(),
}))

vi.mock('@/composables/task/tasksPort', () => ({
  tasksPort: { getAll: mocks.getAll, getDomainStats: mocks.getDomainStats },
}))

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: { getOptions: mocks.getOptions },
}))

import { useTaskList } from '../useTaskList'

const PAGE = {
  items: [{ id: 1, name: '任务A', status: 'completed', tags: [], deleted: false }],
  total: 1, page: 1, perPage: 10, pages: 1,
}
const AGG = {
  total: 1,
  deletedTotal: 0,
  statusCounts: { pending: 0, queued: 0, running: 0, completed: 1, failed: 0 },
  typeCounts: { api: 1, e2e: 0 },
  trend: [],
  granularity: 'day',
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getAll.mockResolvedValue(PAGE)
  mocks.getDomainStats.mockResolvedValue(AGG)
  mocks.getOptions.mockResolvedValue({ algorithms: [] })
})

describe('useTaskList 加载 / 错误态（INT-288）', () => {
  it('拉取期间 isLoading 为 true，结束后复位', async () => {
    let resolveAll!: (v: any) => void
    mocks.getAll.mockReturnValue(new Promise(resolve => { resolveAll = resolve }))

    const vm = useTaskList()
    const p = vm.fetchTasks()
    expect(vm.isLoading.value).toBe(true)

    resolveAll(PAGE)
    await p
    expect(vm.isLoading.value).toBe(false)
  })

  it('拉取失败：error 置文案、isLoading 复位、旧数据保留不清空', async () => {
    const vm = useTaskList()
    await vm.fetchTasks()
    expect(vm.paginatedTasks.value).toHaveLength(1)

    mocks.getAll.mockRejectedValueOnce(new Error('net down'))
    await vm.fetchTasks()

    expect(vm.error.value).toBe('加载任务失败，请稍后重试')
    expect(vm.isLoading.value).toBe(false)
    // 旧数据保留（不再被空态「没有找到任务」误导）
    expect(vm.paginatedTasks.value).toHaveLength(1)
  })

  it('成功后 error 清空', async () => {
    const vm = useTaskList()
    mocks.getAll.mockRejectedValueOnce(new Error('net down'))
    await vm.fetchTasks()
    expect(vm.error.value).not.toBe('')

    mocks.getAll.mockResolvedValueOnce(PAGE)
    await vm.fetchTasks()
    expect(vm.error.value).toBe('')
    expect(vm.paginatedTasks.value).toHaveLength(1)
  })
})
