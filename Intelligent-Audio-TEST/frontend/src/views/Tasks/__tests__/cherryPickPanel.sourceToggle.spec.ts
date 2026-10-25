/**
 * INT-1834：挑选合并页签 picked 行展开 = 组成区树（规范 18 §3 落点③）。
 *
 * 锁定口径：
 * - 行展开渲染 `ContainerTraceExpand` + 组成区树（任务视图默认），与容器详情同源；
 * - 首次展开补 1 次 `GET /tasks/{id}`（+ 1 次 source 溯源），收起再展开不重复请求；
 * - 多行展开互不覆盖，各自按 taskId 补拉一次。
 *
 * INT-401 / INT-552 时期的平铺「源结果溯源」已由本卡替换为组成区树；本文件同步改写为
 * 组成树的展开 / 缓存回归（原文件名的 P1-2 展开回归语义保留：点开必须有内容、再点必须收起）。
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
  default: {
    name: 'TaskCard',
    props: ['task', 'actions', 'isFavorite', 'showCheckbox', 'showConfig'],
    template: '<div class="task-card-stub"><div class="task-title">{{ task.name }}</div></div>',
  },
}))
// 组成区 → CartTree → PickCaseCard → TestCaseCard（会走算法标签 API），桩掉只保留树结构
vi.mock('../../../components/common/test-case/TestCaseCard.vue', () => ({
  default: { template: '<div class="test-case-card-stub" />' },
}))
vi.mock('../../../components/common/data/PaginationComponent.vue', () => ({
  default: { name: 'PaginationComponent', template: '<div />' },
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

const CONTAINER = {
  id: 501,
  name: '挑选合并容器501',
  status: 'completed',
  mergeType: 'picked',
  sourceTaskCount: 1,
  sourceResultCount: 2,
  totalCases: 2,
  completedCases: 1,
}

function makeProps(overrides: Record<string, any> = {}) {
  return {
    containers: {
      loading: false,
      items: [CONTAINER],
      total: 1,
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
      ...overrides,
    },
    taskActions: [],
    isFavorite: () => false,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  clearContainerCompositionCache()
  api.getSource.mockResolvedValue({
    taskId: 501,
    isCherryPick: true,
    total: 2,
    groups: [{
      sourceTaskId: 10,
      sourceTaskName: '来源任务10',
      results: [
        { id: 1001, resultId: 1001, sourceCaseId: 'C1', missing: false },
        { id: 1002, resultId: 1002, sourceCaseId: 'C2', missing: true },
      ],
    }],
  })
  api.getOne.mockImplementation(async (id: number) => ({
    id,
    name: '挑选合并容器501',
    status: 'completed',
    cases: [
      { caseId: 'C1', name: 'JS177 拒识用例', groupName: '拒识', tags: ['标签A'], executionStatus: 'completed', evaluationStatus: 'completed' },
      { caseId: 'C2', name: 'JS062 拒识用例', groupName: '拒识', tags: ['标签A'], executionStatus: 'failed', evaluationStatus: 'completed' },
    ],
    devices: [{ id: 9, name: 'pura90小艺' }],
    apis: [],
  }))
})

describe('CherryPickPanel picked 行展开 = 组成区树（INT-1834 落点③）', () => {
  it('点击展开：渲染组成区树（任务层 + 计数），首次补拉 source + 详情各 1 次', async () => {
    const wrapper = mount(CherryPickPanel, { props: makeProps() })
    await flushPromises()

    // 默认收起：仅标题条，无展开内容
    expect(wrapper.find('.cpp-source-toggle').exists()).toBe(true)
    expect(wrapper.find('.cpp-source-body').exists()).toBe(false)
    expect(wrapper.find('[data-testid="container-trace-expand"]').exists()).toBe(false)

    await wrapper.find('.cpp-source-toggle').trigger('click')
    await flushPromises()

    expect(api.getSource).toHaveBeenCalledWith(501)
    expect(api.getOne).toHaveBeenCalledWith(501)
    expect(api.getOne).toHaveBeenCalledTimes(1)

    // 组成区树 + 计数（任务视图任务层首级）
    expect(wrapper.find('[data-testid="container-trace-expand"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('组成')
    expect(wrapper.text()).toContain('来源 1 个任务')
    expect(wrapper.text()).toContain('结果 2 条')
    expect(wrapper.text()).toContain('来源任务10')
    // 平铺「源结果溯源」旧结构不再存在
    expect(wrapper.find('.cpp-source-results').exists()).toBe(false)
  })

  it('收起再展开：复用缓存，不再请求详情', async () => {
    const wrapper = mount(CherryPickPanel, { props: makeProps() })
    await flushPromises()

    await wrapper.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    expect(api.getOne).toHaveBeenCalledTimes(1)

    // 收起
    await wrapper.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    expect(wrapper.find('.cpp-source-body').exists()).toBe(false)

    // 再展开：缓存命中，零新请求
    await wrapper.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="container-trace-expand"]').exists()).toBe(true)
    expect(api.getOne).toHaveBeenCalledTimes(1)
    expect(api.getSource).toHaveBeenCalledTimes(1)
  })

  it('多卡同时展开互不覆盖：每行各补拉 1 次，各自展示自己的来源任务', async () => {
    api.getSource.mockImplementation(async (id: number) => ({
      taskId: id,
      isCherryPick: true,
      total: 1,
      groups: [{
        sourceTaskId: Number(id) * 10,
        sourceTaskName: `来源${id}`,
        results: [{ id: id, resultId: id, sourceCaseId: 'C1', missing: false }],
      }],
    }))
    const wrapper = mount(CherryPickPanel, {
      props: makeProps({
        items: [
          { ...CONTAINER, id: 501 },
          { ...CONTAINER, id: 502, name: '挑选合并容器502' },
        ],
        total: 2,
        pages: 1,
      }),
    })
    await flushPromises()

    const toggles = wrapper.findAll('.cpp-source-toggle')
    expect(toggles.length).toBe(2)

    await toggles[0].trigger('click')
    await flushPromises()
    await wrapper.findAll('.cpp-source-toggle')[1].trigger('click')
    await flushPromises()

    expect(api.getOne).toHaveBeenCalledTimes(2)
    const cards = wrapper.findAll('.cpp-card')
    expect(cards[0].text()).toContain('来源501')
    expect(cards[1].text()).toContain('来源502')
  })
})
