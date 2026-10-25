/**
 * INT-1834：页签行展开按合并方式自适应（规范 18 §3 落点③ / §8.3）。
 *
 * 验收口径对比：
 * - `picked`（结果挑选）行展开 = 组成区树（ContainerTraceExpand，首次展开补拉详情）；
 * - `whole`（整任务合并）行展开 = 源任务列表（保持现状，不补拉详情）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const api = vi.hoisted(() => ({ getSource: vi.fn(), getOne: vi.fn() }))

vi.mock('../../../infrastructure/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../infrastructure/api')>()
  return {
    ...actual,
    cherryPickApi: { ...actual.cherryPickApi, getSource: api.getSource },
    tasksApi: { ...actual.tasksApi, getOne: api.getOne },
  }
})
vi.mock('../../../components/task/TaskCard.vue', () => ({
  default: { template: '<div class="task-card-stub" />' },
}))
vi.mock('../../../components/common/test-case/TestCaseCard.vue', () => ({
  default: { template: '<div class="test-case-card-stub" />' },
}))
vi.mock('../../../composables/task/usePickCart', () => ({
  usePickCart: () => ({
    cartCount: { value: 0 },
    refreshCart: vi.fn(async () => {}),
    refreshSets: vi.fn(async () => {}),
    sets: { value: [] },
    restoreSetToCart: vi.fn(async () => {}),
    deleteSet: vi.fn(async () => {}),
  }),
}))
vi.mock('../../../composables/task/cartDrawerState', () => ({
  useCartDrawerState: () => ({ visible: { value: false }, open: vi.fn(), close: vi.fn() }),
}))
vi.mock('../../../store/authStore', () => ({
  useAuthStore: () => ({ hasPermission: () => true }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}))

import CherryPickPanel from '../CherryPickPanel.vue'
import { clearContainerCompositionCache } from '../../../composables/task/useContainerComposition'

const PICKED = {
  id: 601,
  name: '结果挑选容器601',
  status: 'completed',
  mergeType: 'picked',
  sourceTaskCount: 1,
  sourceResultCount: 1,
}
const WHOLE = {
  id: 602,
  name: '整任务合并容器602',
  status: 'completed',
  mergeType: 'whole',
  sourceTaskCount: 1,
  sourceResultCount: 2,
  sourceTasks: [{ id: 20, name: '整任务来源20', resultCount: 3 }],
}

function mountPanel() {
  return mount(CherryPickPanel, {
    props: {
      containers: {
        items: [PICKED, WHOLE],
        loading: false,
        total: 2,
        page: 1,
        perPage: 10,
        pages: 1,
        stats: null,
        filters: { mergeType: 'all' },
        fetchList: vi.fn(async () => {}),
        setPage: vi.fn(),
        setPageSize: vi.fn(),
        apply: vi.fn(),
        refresh: vi.fn(),
      },
      taskActions: [],
      isFavorite: () => false,
    },
    global: { stubs: { PaginationComponent: true } },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  clearContainerCompositionCache()
  api.getSource.mockImplementation(async (id: number) => ({
    taskId: id,
    isCherryPick: true,
    total: 1,
    groups: [{
      sourceTaskId: id + 100,
      sourceTaskName: `来源任务${id}`,
      results: [{ id: id, resultId: id, sourceCaseId: 'C1', missing: false }],
    }],
  }))
  api.getOne.mockImplementation(async (id: number) => ({
    id,
    name: `容器${id}`,
    status: 'completed',
    cases: [{ caseId: 'C1', name: '用例一', groupName: '分组A', tags: [], executionStatus: 'completed', evaluationStatus: 'completed' }],
    devices: [],
    apis: [],
  }))
})

describe('INT-1834 行展开按合并方式自适应', () => {
  it('picked 行展开 = 组成区树；whole 行展开 = 源任务列表（对比）', async () => {
    const w = mountPanel()
    await flushPromises()

    const toggles = w.findAll('.cpp-source-toggle')
    expect(toggles.length).toBe(2)

    // picked（第一行）：组成区树
    await toggles[0].trigger('click')
    await flushPromises()
    const cards = w.findAll('.cpp-card')
    expect(cards[0].find('[data-testid="container-trace-expand"]').exists()).toBe(true)
    expect(cards[0].text()).toContain('来源任务601')
    expect(cards[0].text()).not.toContain('源任务列表')

    // whole（第二行）：源任务列表不变
    await w.findAll('.cpp-source-toggle')[1].trigger('click')
    await flushPromises()
    const cardsAfter = w.findAll('.cpp-card')
    expect(cardsAfter[1].find('[data-testid="container-trace-expand"]').exists()).toBe(false)
    expect(cardsAfter[1].text()).toContain('源任务列表（1 个）')
    expect(cardsAfter[1].text()).toContain('整任务来源20')
    expect(cardsAfter[1].text()).toContain('结果 3 条')
  })

  it('whole 行展开不补拉详情（只有 picked 走 GET /tasks/{id}）', async () => {
    const w = mountPanel()
    await flushPromises()

    // 只展开 whole 行
    await w.findAll('.cpp-source-toggle')[1].trigger('click')
    await flushPromises()

    expect(api.getOne).not.toHaveBeenCalled()
    expect(w.text()).toContain('整任务来源20')
  })
})
