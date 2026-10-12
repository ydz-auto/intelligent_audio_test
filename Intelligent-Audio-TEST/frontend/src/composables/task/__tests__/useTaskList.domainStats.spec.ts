/**
 * INT-200：任务统计卡/图表走任务域全量聚合（/tasks/stats），
 * 不再由当前页 tasks 过滤计数（回归：分页下统计数字与真实总量不符）。
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

/** 全量聚合返回（数值刻意与当前页任务错开，便于区分统计口径） */
const AGG = {
  total: 25,
  deletedTotal: 4,
  statusCounts: { pending: 3, queued: 2, running: 1, completed: 10, failed: 5 },
  typeCounts: { api: 12, e2e: 8, mixed: 1 },
  trend: [{ key: '2026-10-12', count: 3 }],
  granularity: 'day',
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getDomainStats.mockResolvedValue(AGG)
  // 当前页仅 1 条 running 任务；列表分页 total=22（与全量 25 错开）
  mocks.getAll.mockResolvedValue({
    items: [{ id: 1, name: 'page-only', status: 'running', tags: [], deleted: false, devices: [], apis: [] }],
    total: 22, page: 1, perPage: 10, pages: 3,
  })
  mocks.getOptions.mockResolvedValue({ algorithms: [] })
})

describe('useTaskList 全量统计（INT-200）', () => {
  it('统计卡反映全量分布，不受当前页 1 条任务影响', async () => {
    const vm = useTaskList()
    await vm.fetchTasks()
    expect(vm.pendingTasks.value).toBe(5)      // pending 3 + queued 2
    expect(vm.queuedTasks.value).toBe(2)
    expect(vm.inProgressTasks.value).toBe(1)
    expect(vm.completedTasks.value).toBe(10)
    expect(vm.failedTasks.value).toBe(5)
    expect(vm.deletedTasks.value).toBe(4)
    expect(vm.domainTotal.value).toBe(25)
  })

  it('统计卡总任务数与列表分页 total 解耦', async () => {
    const vm = useTaskList()
    await vm.fetchTasks()
    expect(vm.totalTasks.value).toBe(22)       // 列表分页 total（分页控件用）
    expect(vm.domainTotal.value).toBe(25)      // 统计卡总任务数（全量）
    expect(vm.paginatedTasks.value).toHaveLength(1)
  })

  it('fetchTasks 后同步刷新全量统计（图表数据源）', async () => {
    const vm = useTaskList()
    await vm.fetchTasks()
    expect(mocks.getDomainStats).toHaveBeenCalledWith('day')
    expect(vm.taskStats.value?.typeCounts).toEqual({ api: 12, e2e: 8, mixed: 1 })
    expect(vm.taskStats.value?.trend).toEqual([{ key: '2026-10-12', count: 3 }])
  })

  it('统计获取失败不阻断列表加载', async () => {
    mocks.getDomainStats.mockRejectedValue(new Error('network down'))
    const vm = useTaskList()
    await vm.fetchTasks()
    expect(vm.paginatedTasks.value).toHaveLength(1)
    expect(vm.domainTotal.value).toBe(0)
  })

  it('statsGranularity 变更后按新粒度请求', async () => {
    const vm = useTaskList()
    vm.statsGranularity.value = 'month'
    await vm.fetchTaskStats()
    expect(mocks.getDomainStats).toHaveBeenCalledWith('month')
  })
})
