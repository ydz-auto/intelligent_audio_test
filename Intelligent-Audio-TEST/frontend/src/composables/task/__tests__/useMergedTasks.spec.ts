/**
 * INT-298：合并任务 composable 单测。
 *
 * 端到端锁定「merged=true 数据源契约 → 筛选参数 → wire」贯通：
 * - fetchList 恒定下发 merged=true（TaskMergeRelation 存在性判定合并容器，
 *   对齐 V9.7.10 合并页签数据源；后端契约经 tasksApi → GET /tasks?merged=true）
 * - search/status/algorithmType/timeRange 按需下发，'all' 占位不下发
 * - 排序 toggleSort 切换升降序且对当前页生效
 * - apply/setPage/setPageSize 分页语义（筛选回第一页）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAll: vi.fn(),
}))

vi.mock('@/infrastructure/api', () => ({
  tasksApi: { getAll: mocks.getAll },
}))

import { useMergedTasks } from '../useMergedTasks'

/** 合并容器任务页（含 source_tasks 的容器项） */
const MERGED_PAGE = {
  items: [
    { id: 10, name: '合并任务A', status: 'completed', sourceTasks: [{ id: 1, name: '源1', status: 'merged' }], tags: [] },
    { id: 11, name: '合并任务B', status: 'completed', sourceTasks: [{ id: 2, name: '源2', status: 'merged' }], tags: [] },
  ],
  total: 12, page: 1, perPage: 10, pages: 2,
}

/** 提取最近一次 getAll 的查询参数 */
const lastQuery = () => mocks.getAll.mock.calls[mocks.getAll.mock.calls.length - 1]?.[0] as Record<string, any>

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getAll.mockResolvedValue(MERGED_PAGE)
})

describe('useMergedTasks 数据源契约（INT-298）', () => {
  it('fetchList 恒定下发 merged=true（合并容器过滤贯通）', async () => {
    const vm = useMergedTasks()
    await vm.fetchList()

    expect(lastQuery().merged).toBe(true)
    expect(vm.items).toHaveLength(2)
    expect(vm.total).toBe(12)
  })

  it('search/status/algorithmType 按需下发，all 占位不下发', async () => {
    const vm = useMergedTasks()
    vm.filters.search = '回归'
    vm.filters.status = 'completed'
    vm.filters.algorithmType = 'all'
    await vm.fetchList()

    const q = lastQuery()
    expect(q.search).toBe('回归')
    expect(q.status).toBe('completed')
    expect(q.algorithmType).toBeUndefined()
  })

  it('自定义时间范围映射 startTime/endTime（camelCase 域契约，snake_case 化在 Infrastructure）', async () => {
    const vm = useMergedTasks()
    vm.filters.timeRange = 'custom'
    vm.filters.customRange = { start: '2026-10-01', end: '2026-10-13' }
    await vm.fetchList()

    const q = lastQuery()
    expect(q.startTime).toBeDefined()
    expect(q.endTime).toBeDefined()
  })

  it('toggleSort 切换升降序并对当前页生效（createdAt asc 首项为较早任务）', async () => {
    const vm = useMergedTasks()
    mocks.getAll.mockResolvedValue({
      items: [
        { id: 1, name: '早任务', status: 'completed', createdAt: '2026-10-01T00:00:00', tags: [] },
        { id: 2, name: '晚任务', status: 'completed', createdAt: '2026-10-02T00:00:00', tags: [] },
      ],
      total: 2, page: 1, perPage: 10, pages: 1,
    })
    await vm.fetchList()
    expect(vm.items[0].name).toBe('晚任务')   // 默认 desc

    vm.toggleSort('createdAt')
    expect(vm.filters.sort.field).toBe('createdAt')
    expect(vm.filters.sort.order).toBe('asc')
    expect(vm.items[0].name).toBe('早任务')
  })

  it('apply 回到第一页；setPage 前往指定页', async () => {
    const vm = useMergedTasks()
    await vm.fetchList()
    vm.setPage(2)
    expect(lastQuery().page).toBe(2)

    vm.filters.search = 'x'
    vm.apply()
    expect(vm.page).toBe(1)
    expect(lastQuery().search).toBe('x')
  })

  it('setPageSize 回到第一页并按新页大小拉取', async () => {
    const vm = useMergedTasks()
    await vm.fetchList()
    vm.setPageSize(20)
    expect(vm.perPage).toBe(20)
    expect(lastQuery().page).toBe(1)
  })
})
