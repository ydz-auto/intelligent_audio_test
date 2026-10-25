/**
 * INT-1834 / INT-552：picked 行展开「补拉失败」错误态回归锁定（规范 18 §4.3 / §7）。
 *
 * 口径：首次展开补 1 次 `GET /tasks/{id}`；补拉失败 → 展开区 Empty + 「重试」，
 * 行本体与计数照常；重试成功后恢复组成区树。「无来源记录」只在 source 200 且
 * groups=[] 时出现，不能与失败混淆。
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

function makeProps(items: any[] = []) {
  return {
    containers: {
      loading: false,
      items: items.length
        ? items
        : [{ id: 1, name: '挑选合并任务A', mergeType: 'picked', sourceTaskCount: 1, sourceResultCount: 1, createdAt: '2026-10-01 10:00:00' }],
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

async function expandSource(w: any) {
  await w.find('.cpp-source-toggle').trigger('click')
  await flushPromises()
}

const SOURCE = {
  taskId: 1,
  isCherryPick: true,
  total: 1,
  groups: [{ sourceTaskId: 7, sourceTaskName: '源任务7', results: [{ id: 1, resultId: 101, sourceCaseId: 'C1' }] }],
}

const DETAIL = {
  id: 1,
  name: '挑选合并任务A',
  status: 'completed',
  cases: [{ caseId: 'C1', name: '用例一', groupName: '分组A', tags: [], executionStatus: 'completed', evaluationStatus: 'completed' }],
  devices: [],
  apis: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getSource.mockReset()
  api.getOne.mockReset()
  clearContainerCompositionCache()
})

describe('INT-1834 picked 行展开补拉失败', () => {
  it('详情补拉 reject → 展开区显示「组成加载失败」与重试，行本体照常', async () => {
    api.getSource.mockResolvedValue(SOURCE)
    api.getOne.mockRejectedValue(new Error('network down'))
    const w = await mountPanel()
    await expandSource(w)

    expect(w.text()).toContain('组成加载失败')
    expect(w.text()).toContain('重试')
    expect(w.text()).not.toContain('该任务没有合并来源记录')
    // 行本体与计数照常
    expect(w.find('.cpp-card').exists()).toBe(true)
    expect(w.find('.cpp-source-toggle').exists()).toBe(true)
  })

  it('重试成功后恢复组成区树（再次请求详情）', async () => {
    api.getSource.mockResolvedValue(SOURCE)
    api.getOne
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce(DETAIL)
    const w = await mountPanel()
    await expandSource(w)

    expect(w.text()).toContain('组成加载失败')

    const retryBtn = w.findAll('button').find((b) => b.text().includes('重试'))
    expect(retryBtn).toBeTruthy()
    await retryBtn!.trigger('click')
    await flushPromises()

    expect(api.getOne).toHaveBeenCalledTimes(2)
    expect(w.text()).not.toContain('组成加载失败')
    expect(w.text()).toContain('源任务7')
  })

  it('source 200 且 groups 为空（真无来源）→ 仍显示「没有合并来源记录」空态', async () => {
    api.getSource.mockResolvedValue({ taskId: 1, isCherryPick: true, total: 0, groups: [] })
    api.getOne.mockResolvedValue(DETAIL)
    const w = await mountPanel()
    await expandSource(w)

    expect(w.text()).toContain('该任务没有合并来源记录')
    expect(w.text()).not.toContain('组成加载失败')
  })
})
