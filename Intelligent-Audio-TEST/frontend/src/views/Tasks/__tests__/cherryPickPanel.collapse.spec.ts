/**
 * INT-339 P2-3 / INT-1834：挑选合并页签行展开 / 收起回归。
 *
 * 锁定口径：
 * - 溯源标题行常显（展开态不替换标题行），点击可再次收起；
 * - 展开后正文区出现（picked = 组成区树，由 ContainerTraceExpand 承载）；
 * - 收起后再展开复用缓存（按 taskId 缓存，§4.3），不重复补拉详情。
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

const containersStub = (items: any[] = []) => ({
  items,
  loading: false,
  total: items.length,
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
})

beforeEach(() => {
  vi.clearAllMocks()
  clearContainerCompositionCache()
  api.getSource.mockResolvedValue({
    taskId: 1,
    isCherryPick: true,
    total: 2,
    groups: [
      { sourceTaskId: 10, sourceTaskName: '源任务A', results: [{ id: 1, resultId: 100, sourceCaseId: 'C1' }] },
      { sourceTaskId: 11, sourceTaskName: '源任务B', results: [{ id: 2, resultId: 101, sourceCaseId: 'C2' }] },
    ],
  })
  api.getOne.mockResolvedValue({
    id: 1,
    name: '挑选任务X',
    status: 'completed',
    cases: [
      { caseId: 'C1', name: '用例一', groupName: '分组A', tags: [], executionStatus: 'completed', evaluationStatus: 'completed' },
      { caseId: 'C2', name: '用例二', groupName: '分组A', tags: [], executionStatus: 'completed', evaluationStatus: 'completed' },
    ],
    devices: [],
    apis: [],
  })
})

function mountPanel(items: any[] = []) {
  return mount(CherryPickPanel, {
    props: {
      containers: containersStub(items),
      taskActions: [],
      isFavorite: () => false,
    },
    global: { stubs: { PaginationComponent: true } },
  })
}

describe('CherryPickPanel 溯源展开/收起（P2-3）', () => {
  it('标题行常显：展开态不替换标题行，点击可再次收起', async () => {
    const w = mountPanel([{ id: 1, name: '挑选任务X', mergeType: 'picked' }])
    await flushPromises()

    // 初始：标题行存在、内容未展开
    expect(w.find('.cpp-source-toggle').exists()).toBe(true)
    expect(w.find('.cpp-source-toggle i.fa-chevron-down').exists()).toBe(true)
    expect(w.find('.cpp-source-body').exists()).toBe(false)

    // 点击展开 → 组成区树正文出现
    await w.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    expect(w.find('.cpp-source-body').exists()).toBe(true)
    expect(w.find('.cpp-source-toggle i.fa-chevron-up').exists()).toBe(true)
    expect(w.find('[data-testid="container-trace-expand"]').exists()).toBe(true)
    expect(api.getOne).toHaveBeenCalledWith(1)

    // 再点击标题 → 收起（标题行仍保留）
    await w.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    expect(w.find('.cpp-source-body').exists()).toBe(false)
    expect(w.find('.cpp-source-toggle').exists()).toBe(true)
    expect(w.find('.cpp-source-toggle i.fa-chevron-down').exists()).toBe(true)
  })

  it('收起再展开复用缓存：详情补拉只 1 次（§4.3 不重复请求）', async () => {
    const w = mountPanel([{ id: 1, name: '挑选任务X', mergeType: 'picked' }])
    await flushPromises()

    await w.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    expect(api.getOne).toHaveBeenCalledTimes(1)

    await w.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    await w.find('.cpp-source-toggle').trigger('click')
    await flushPromises()

    expect(api.getOne).toHaveBeenCalledTimes(1)
    expect(api.getSource).toHaveBeenCalledTimes(1)
    expect(w.find('.cpp-source-body').exists()).toBe(true)
  })
})
