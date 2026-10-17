/**
 * INT-577 P0 回归：批量「加入挑选」向导开启（跨 :key=fullPath 重挂载共享请求机制）。
 *
 * 背景（测试实证）：App.vue `<router-view :key="$route.fullPath">` 在 query 变化时
 * 整树重挂载。旧实现经 cherryPickPanelRef 在导航前实例 A 上 openWizardWithTasks，
 * A 被重挂载销毁后最终实例 B 向导不出现（P0 两轮复测不通过）。
 *
 * 修复：发起方经 usePickWizardRequest 共享请求（模块级单例），新面板 immediate watch
 * 消费并自开向导；向导关闭/下单时清除请求防泄漏。本 spec 锁定该机制：
 * 1. 挂载前面板已有待消费请求 → 向导自开（预设任务/直达步骤透传）；
 * 2. 无请求 → 向导不自开（面板列表态）；
 * 3. 关闭向导 → 共享请求清除 → 重挂载后不再自开（防泄漏）。
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
vi.mock('../../../components/common/data/PaginationComponent.vue', () => ({
  default: { name: 'PaginationComponent', template: '<div />' },
}))
// 桩替代向导本体：本 spec 只锁面板「消费请求 → 开向导」集成点（向导内部由 wizard 侧用例覆盖）
vi.mock('../../../components/task/pick/CherryPickWizard.vue', () => ({
  default: {
    name: 'CherryPickWizard',
    props: ['presetTaskIds', 'initialStep'],
    template: '<div class="cpw-stub"><div class="cpw-preset">{{ presetTaskIds.join(",") }}</div><div class="cpw-step">{{ initialStep }}</div><button class="cpw-close" @click="$emit(\'close\')">X</button></div>',
  },
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
import { requestPickWizard, clearPickWizardRequest } from '../../../composables/task/usePickWizardRequest'

function makeProps(overrides: Record<string, any> = {}) {
  return {
    containers: {
      loading: false,
      items: [],
      total: 0,
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
  clearPickWizardRequest()
  api.getSource.mockResolvedValue({ taskId: 1, isCherryPick: true, total: 0, groups: [] })
})

describe('CherryPickPanel 向导开启请求（INT-577 P0 回归）', () => {
  it('挂载前已有批量「加入挑选」请求 → 向导自开且任务级预选透传', async () => {
    requestPickWizard({ presetTaskIds: [101, 202] })
    const wrapper = mount(CherryPickPanel, { props: makeProps() })
    await flushPromises()

    const wiz = wrapper.find('.cpw-stub')
    expect(wiz.exists()).toBe(true)
    expect(wrapper.find('.cpw-preset').text()).toBe('101,202')
    expect(wrapper.find('.cpw-step').text()).toBe('pick')
  })

  it('「去复核」请求 → 向导直达复核步骤（initialStep=review 透传）', async () => {
    requestPickWizard({ step: 'review' })
    const wrapper = mount(CherryPickPanel, { props: makeProps() })
    await flushPromises()

    expect(wrapper.find('.cpw-stub').exists()).toBe(true)
    expect(wrapper.find('.cpw-step').text()).toBe('review')
  })

  it('无请求 → 面板列表态（向导不自开）', async () => {
    const wrapper = mount(CherryPickPanel, { props: makeProps() })
    await flushPromises()

    expect(wrapper.find('.cpw-stub').exists()).toBe(false)
    // 列表 Actions（开始挑选/打开购物车/管理挑选集）正常展示
    expect(wrapper.find('.cpp-actions').exists()).toBe(true)
  })

  it('关闭向导 → 共享请求清除（重挂载后不再自开，防泄漏）', async () => {
    requestPickWizard({ presetTaskIds: [7] })
    const wrapper = mount(CherryPickPanel, { props: makeProps() })
    await flushPromises()
    expect(wrapper.find('.cpw-stub').exists()).toBe(true)

    // 关闭向导（桩内 close 钮 → close 事件）→ 请求清除
    await wrapper.find('.cpw-close').trigger('click')
    await flushPromises()
    expect(wrapper.find('.cpw-stub').exists()).toBe(false)

    // 模拟重挂载（App.vue :key=fullPath 场景）：请求已清除 → 新实例不自开
    const wrapper2 = mount(CherryPickPanel, { props: makeProps() })
    await flushPromises()
    expect(wrapper2.find('.cpw-stub').exists()).toBe(false)
  })
})
