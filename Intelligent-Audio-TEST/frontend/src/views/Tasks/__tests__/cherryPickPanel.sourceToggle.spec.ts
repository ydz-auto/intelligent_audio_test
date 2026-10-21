/**
 * INT-401 返工：CherryPickPanel 源结果溯源展开回归锁定（验收 P1-2）。
 *
 * 回归：toggleSource 构造新 Set 后从未 add(taskId)，v-if="expanded.has(...)"
 * 永不成立 → 溯源数据已 load（后端 GET 已调用且返回 200）但 UI 永不展开。
 * 锁定「点击展开 → 来源分组 + 引用结果逐条可见（含缺失标注）→ 再点收起」
 * 双向交互，以及多卡同时展开互不覆盖。
 *
 * INT-577 升级适配：面板 props 由 cherryPick 更名为 containers（统一容器列表），
 * 溯源 DOM 由 merged-* 改 cpp-source-*（按合并方式自适应）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const api = vi.hoisted(() => ({ getSource: vi.fn() }))

vi.mock('../../../infrastructure/api', () => ({
  cherryPickApi: { getSource: api.getSource },
}))
vi.mock('../../../components/task/TaskCard.vue', () => ({
  default: {
    name: 'TaskCard',
    props: ['task', 'actions', 'isFavorite', 'showCheckbox', 'showConfig'],
    template: '<div class="task-card-stub"><div class="task-title">{{ task.name }}</div></div>',
  },
}))
// INT-1103：TestCaseCard 升级为全站统一组件后经 CherryPickWizard→PickTree 被间接引入；
// 本测试只验面板溯源展开/收起，不验用例卡，卡组件以 stub 屏蔽其依赖链。
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

const CONTAINER = { id: 501, name: '容器501', status: 'completed', totalCases: 2, completedCases: 2 }

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
  api.getSource.mockResolvedValue({
    taskId: 501,
    isCherryPick: true,
    total: 1,
    groups: [{
      sourceTaskId: 10,
      sourceTaskName: '来源任务10',
      results: [
        { id: 1001, resultId: 1001, sourceCaseId: 'C1', missing: false },
        { id: 1002, resultId: 1002, sourceCaseId: 'C2', missing: true },
      ],
    }],
  })
})

describe('CherryPickPanel 源结果溯源展开（INT-401 P1-2 回归）', () => {
  it('点击展开：来源任务分组 + 引用结果逐条展示（含缺失标注）', async () => {
    const wrapper = mount(CherryPickPanel, { props: makeProps() })
    await flushPromises()

    // 默认收起：仅标题条（chevron-down），无来源内容
    expect(wrapper.find('.cpp-source-toggle').exists()).toBe(true)
    expect(wrapper.find('.cpp-source-result').exists()).toBe(false)
    expect(wrapper.find('.cpp-source-icon').classes()).toContain('fa-chevron-down')

    // 点击「源结果溯源」→ 展开（P1-2 修复前 expanded 不含 taskId，内容永不出现）
    await wrapper.find('.cpp-source-toggle').trigger('click')
    expect(api.getSource).toHaveBeenCalledWith(501)
    await flushPromises()

    expect(wrapper.text()).toContain('来源任务10')
    const results = wrapper.findAll('.cpp-source-result')
    expect(results.length).toBe(2)
    expect(wrapper.find('.missing-badge').text()).toContain('源结果已缺失')
    // 展开态：chevron-up 提示可收起
    expect(wrapper.find('.cpp-source-icon').classes()).toContain('fa-chevron-up')
  })

  it('再点收起：来源内容消失，回到折叠态', async () => {
    const wrapper = mount(CherryPickPanel, { props: makeProps() })
    await flushPromises()

    await wrapper.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    expect(wrapper.find('.cpp-source-result').exists()).toBe(true)

    await wrapper.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    expect(wrapper.find('.cpp-source-result').exists()).toBe(false)
    expect(wrapper.find('.cpp-source-icon').classes()).toContain('fa-chevron-down')
  })

  it('多卡同时展开互不覆盖：第二张卡展开不丢第一张溯源数据', async () => {
    const wrapper = mount(CherryPickPanel, {
      props: makeProps({
        items: [
          { id: 501, name: '容器501', status: 'completed', totalCases: 1, completedCases: 1 },
          { id: 502, name: '容器502', status: 'completed', totalCases: 1, completedCases: 1 },
        ],
        total: 2,
        pages: 1,
      }),
    })
    await flushPromises()

    const toggles = wrapper.findAll('.cpp-source-toggle')
    expect(toggles.length).toBe(2)

    api.getSource.mockImplementation((id: number) => Promise.resolve({
      taskId: id,
      isCherryPick: true,
      total: 1,
      groups: [{
        sourceTaskId: id,
        sourceTaskName: `来源${id}`,
        results: [{ id: 1, resultId: 1, sourceCaseId: 'C1', missing: false }],
      }],
    }))

    await toggles[0].trigger('click')
    await flushPromises()
    await toggles[1].trigger('click')
    await flushPromises()

    // 两张卡各自展示自己的来源（INT-401 先前单一 sourceGroups 会被覆盖）
    const wraps = wrapper.findAll('.cpp-card')
    expect(wraps[0].text()).toContain('来源501')
    expect(wraps[1].text()).toContain('来源502')
  })
})
