/**
 * INT-973：任务列表加载/错误态锁定。
 *
 * 回归口径：
 * - fetchTasks 进行中 loading=true（首次进入不闪空态）；
 * - fetchTasks 失败置 error（用户可见错误信息，不再仅 console.error 静默落空态）；
 * - 失败后保留旧数据不清空（列表内容不清空，仅叠加错误条）；
 * - 下次成功拉取 error 复位。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

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

const EMPTY_STATS = {
  total: 0, deletedTotal: 0, statusCounts: {}, typeCounts: {},
  trend: [], granularity: 'day',
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  mocks.getDomainStats.mockResolvedValue(EMPTY_STATS)
  mocks.getOptions.mockResolvedValue({ algorithms: [] })
  mocks.getAll.mockResolvedValue({
    items: [{ id: 1, name: 't1', status: 'completed', tags: [], deleted: false, devices: [], apis: [] }],
    total: 1, page: 1, perPage: 10, pages: 1,
  })
})

describe('useTaskList 加载/错误态（INT-973）', () => {
  it('成功拉取：loading 复位为 false、error 为 null', async () => {
    const vm = useTaskList()
    expect(vm.loading.value).toBe(false)
    await vm.fetchTasks()
    expect(vm.loading.value).toBe(false)
    expect(vm.error.value).toBeNull()
    expect(vm.paginatedTasks.value).toHaveLength(1)
  })

  it('拉取失败：置错误信息（用户可见），不静默落空态', async () => {
    mocks.getAll.mockRejectedValue(new Error('network down'))
    const vm = useTaskList()
    await vm.fetchTasks()
    expect(vm.loading.value).toBe(false)
    expect(vm.error.value).toBe('任务列表加载失败，请稍后重试')
  })

  it('拉取失败保留旧数据不清空（仅叠加错误条，不误清列表）', async () => {
    const vm = useTaskList()
    await vm.fetchTasks()
    expect(vm.paginatedTasks.value).toHaveLength(1)

    mocks.getAll.mockRejectedValue(new Error('network down'))
    await vm.fetchTasks()
    expect(vm.error.value).toBe('任务列表加载失败，请稍后重试')
    expect(vm.paginatedTasks.value).toHaveLength(1)
  })

  it('失败后重试成功：error 复位、列表恢复', async () => {
    const vm = useTaskList()
    mocks.getAll.mockRejectedValueOnce(new Error('network down'))
    await vm.fetchTasks()
    expect(vm.error.value).toBe('任务列表加载失败，请稍后重试')

    await vm.fetchTasks()
    expect(vm.error.value).toBeNull()
    expect(vm.paginatedTasks.value).toHaveLength(1)
  })

  it('统计失败不阻断列表加载，也不置列表错误（INT-200 口径）', async () => {
    mocks.getDomainStats.mockRejectedValue(new Error('stats down'))
    const vm = useTaskList()
    await vm.fetchTasks()
    expect(vm.paginatedTasks.value).toHaveLength(1)
    expect(vm.error.value).toBeNull()
  })
})
