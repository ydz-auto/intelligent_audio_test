/**
 * INT-552：挑选溯源加载失败错误态回归锁定。
 *
 * 原缺陷：loadSource catch 置 sourcesByTask[taskId]=[] → 展开「源结果溯源」时
 * 接口失败被静默降级为「暂无来源记录」空态，与「真无来源」混淆。
 * 修复引入 per-task sourceErrorByTask，展开区三分：loading / error（重试）/ 空态。
 *
 * INT-577 升级适配：面板 props 由 cherryPick 更名为 containers，溯源 DOM 改 cpp-source-*。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const api = vi.hoisted(() => ({ getSource: vi.fn() }))

vi.mock(import('../../../infrastructure/api'), async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    cherryPickApi: { ...actual.cherryPickApi, getSource: api.getSource },
  }
})
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

function makeProps() {
  return {
    containers: {
      loading: false,
      items: [{ id: 1, name: '挑选合并任务A', createdAt: '2026-10-01 10:00:00' }],
      total: 1,
      page: 1,
      perPage: 10,
      pages: 1,
      stats: null,
      filters: { mergeType: 'all' },
      setPage: vi.fn(),
      setPageSize: vi.fn(),
      fetchList: vi.fn(async () => {}),
      apply: vi.fn(),
      refresh: vi.fn(),
    },
    taskActions: [],
    isFavorite: () => false,
  }
}

async function mountPanel() {
  const w = mount(CherryPickPanel, {
    props: makeProps(),
    global: {
      stubs: {
        TaskCard: { template: '<div class="task-card-stub" />' },
        PaginationComponent: true,
      },
    },
  })
  await flushPromises()
  return w
}

/** 点击「源结果溯源」标题展开（触发 loadSource） */
async function expandSource(w: any) {
  await w.find('.cpp-source-toggle').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getSource.mockReset()
})

describe('INT-552 溯源加载错误态', () => {
  it('getSource reject → 显示错误态与重试按钮，而非「暂无来源记录」', async () => {
    api.getSource.mockRejectedValue(new Error('network down'))
    const w = await mountPanel()
    await expandSource(w)

    expect(w.text()).toContain('溯源加载失败')
    expect(w.text()).toContain('重试')
    expect(w.text()).not.toContain('该合并任务暂无来源记录')
  })

  it('重试成功后恢复来源分组展示（重试按钮再次触发 loadSource）', async () => {
    api.getSource
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({
        taskId: 1,
        isCherryPick: true,
        total: 2,
        groups: [{ sourceTaskId: 7, sourceTaskName: '源任务7', results: [{ id: 1, resultId: 101 }] }],
      })
    const w = await mountPanel()
    await expandSource(w)

    expect(w.text()).toContain('溯源加载失败')

    await w.find('.source-retry-btn').trigger('click')
    await flushPromises()

    expect(api.getSource).toHaveBeenCalledTimes(2)
    expect(w.text()).toContain('源任务7')
    expect(w.text()).not.toContain('溯源加载失败')
  })

  it('成功但 groups 为空（真无来源）→ 仍显示「暂无来源记录」空态', async () => {
    api.getSource.mockResolvedValue({ taskId: 1, isCherryPick: true, total: 0, groups: [] })
    const w = await mountPanel()
    await expandSource(w)

    expect(w.text()).toContain('该合并任务暂无来源记录')
    expect(w.text()).not.toContain('溯源加载失败')
  })
})
