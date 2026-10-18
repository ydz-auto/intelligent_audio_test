/**
 * INT-339 P2-3：CherryPickPanel 溯源展开/收起回归。
 *
 * 锁定口径（前端 UX 审计打回项 P2-3）：
 * - 溯源标题行常显（展开态不替换标题行），点击可再次收起（对照合并面板 MergedTaskPanel 基线）
 * - 展开后按卡加载来源分组（sourceLoadingByTask 每卡独立，多卡展开互不覆盖）
 * - 收起后再展开复用已缓存来源数据（sourcesByTask 按卡缓存）
 *
 * INT-577 升级适配：面板 props 由 cherryPick 更名为 containers，溯源 DOM 改 cpp-source-*。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const api = vi.hoisted(() => ({ getSource: vi.fn() }))

vi.mock('../../../infrastructure/api', () => ({
  cherryPickApi: { getSource: api.getSource },
}))
vi.mock('../../../components/task/TaskCard.vue', () => ({
  default: { template: '<div class="task-card-stub" />' },
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
  api.getSource.mockResolvedValue({
    taskId: 1,
    isCherryPick: true,
    total: 2,
    groups: [
      { sourceTaskId: 10, sourceTaskName: '源任务A', results: [{ id: 1, resultId: 100 }] },
      { sourceTaskId: 11, sourceTaskName: '源任务B', results: [{ id: 2, resultId: 101 }] },
    ],
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
    const w = mountPanel([{ id: 1, name: '挑选任务X' }])
    await flushPromises()

    // 初始：标题行存在、内容未展开
    expect(w.find('.cpp-source-toggle').exists()).toBe(true)
    expect(w.find('.cpp-source-toggle i.fa-chevron-down').exists()).toBe(true)
    expect(w.find('.cpp-source-body').exists()).toBe(false)

    // 点击展开 → 加载来源并展示内容
    await w.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    expect(w.find('.cpp-source-body').exists()).toBe(true)
    expect(w.find('.cpp-source-toggle i.fa-chevron-up').exists()).toBe(true)
    expect(api.getSource).toHaveBeenCalledWith(1)
    expect(w.text()).toContain('源任务A')
    expect(w.text()).toContain('源任务B')

    // 再点击标题 → 收起（标题行仍保留）
    await w.find('.cpp-source-toggle').trigger('click')
    await flushPromises()
    expect(w.find('.cpp-source-body').exists()).toBe(false)
    expect(w.find('.cpp-source-toggle').exists()).toBe(true)
    expect(w.find('.cpp-source-toggle i.fa-chevron-down').exists()).toBe(true)
  })

  it('多卡展开互不覆盖：来源数据按卡独立缓存', async () => {
    api.getSource.mockImplementation(async (taskId: number) => ({
      taskId,
      isCherryPick: true,
      total: 1,
      groups: [
        { sourceTaskId: Number(taskId) * 10, sourceTaskName: `源${taskId}`, results: [{ id: taskId, resultId: taskId }] },
      ],
    }))
    const w = mountPanel([{ id: 1, name: 'A' }, { id: 2, name: 'B' }])
    await flushPromises()

    const titles = w.findAll('.cpp-source-toggle')
    // 展开卡 1
    await titles[0].trigger('click')
    await flushPromises()
    // 展开卡 2
    await w.findAll('.cpp-source-toggle')[1].trigger('click')
    await flushPromises()

    expect(api.getSource).toHaveBeenCalledTimes(2)
    // 卡 1 溯源内容仍在（未被卡 2 覆盖）
    expect(w.text()).toContain('源1')
    expect(w.text()).toContain('源2')
  })
})
