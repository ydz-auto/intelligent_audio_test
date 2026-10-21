/**
 * INT-577 UX 审计 P2 回归：挑选向导「结果类型」筛选器生效（客户端过滤方案①）。
 *
 * 背景（审计实证）：筛选栏 resultTypes 绑定存在，但 loadCandidates 不下发该参数
 * （后端候选查询无 result_type 过滤）亦无客户端过滤 → 候选列表/树完全不变，控件纯摆设。
 *
 * 修复：CherryPickWizard 增加 filteredCandidates 计算属性，loadCandidates 后按
 * filters.resultTypes 客户端过滤候选行/树（重建树时过滤 result_type 节点）；
 * 展示计数 visibleTotal 同步；result_type 命中时「全选当前筛选」降级当前已加载树
 * （后端 select-all 不支持 result_type，跨页全选降级口径）。
 *
 * 本 spec 锁定：① 无筛选全量展示；② 勾选结果类型 → 树/平铺只含命中行且计数同步；
 * ③ 结果类型激活时 select-all 走当前已加载降级（不发后端 select-all）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const api = vi.hoisted(() => ({
  listCandidates: vi.fn(),
  selectAllCandidates: vi.fn(),
  preview: vi.fn(),
  tasksGetAll: vi.fn(),
  devicesGetAllFlat: vi.fn(),
}))
const notifications = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))
const modalOpen = vi.hoisted(() => vi.fn())

vi.mock('../../../../infrastructure/api', () => ({
  cherryPickApi: {
    listCandidates: api.listCandidates,
    selectAllCandidates: api.selectAllCandidates,
    preview: api.preview,
  },
  tasksApi: { getAll: api.tasksGetAll },
  devicesApi: { getAllFlat: api.devicesGetAllFlat },
}))
vi.mock('../../../../composables/task/usePickCart', async () => {
  const { ref, computed } = await import('vue')
  return {
    usePickCart: () => {
      const cart = ref({ groups: [], total: 0, invalidItemIds: [] })
      return {
        cart,
        cartLoading: ref(false),
        cartCount: ref(0),
        invalidCount: ref(0),
        sets: ref([]),
        resultIdSet: computed(() => new Set<number>()),
        cartRevision: ref(0),
        refreshCart: vi.fn(async () => {}),
        addToCart: vi.fn(),
        removeItem: vi.fn(),
        removeItems: vi.fn(),
        clearCart: vi.fn(),
        refreshSets: vi.fn(async () => {}),
        saveAsSet: vi.fn(),
        restoreSetToCart: vi.fn(),
        deleteSet: vi.fn(),
      }
    },
  }
})
vi.mock('../../../../composables/modal/useNotification', () => ({ useNotification: () => notifications }))
vi.mock('../../../../composables/modal/useModal', () => ({ useModalControl: () => ({ open: modalOpen }) }))
vi.mock('../../../../composables/modal/constants', () => ({ MODAL_TYPES: { BASIC_CONFIRM: 'basicConfirm', INPUT_CONFIRM: 'inputConfirm' } }))
// 树/购物车组件桩：本 spec 只锁「结果类型过滤 → 树根/平铺行」数据侧，不渲染真实树
vi.mock('../PickTree.vue', () => ({
  default: {
    name: 'PickTreeStub',
    props: ['roots', 'selected', 'expandedKeys', 'alreadyAdded', 'leafMeta'],
    template: '<div class="pick-tree-stub" />',
  },
}))
vi.mock('../CartTree.vue', () => ({
  default: { name: 'CartTreeStub', props: ['roots'], template: '<div class="cart-tree-stub" />' },
}))

import CherryPickWizard from '../CherryPickWizard.vue'
import { collectLeafResultIds } from '../pickTree'

const CAND = (resultId: number, resultType: string, extra: Record<string, any> = {}) => ({
  resultId, taskId: 10, taskName: '任务10', taskStatus: 'completed',
  caseId: `C${resultId}`, caseName: `用例${resultId}`,
  deviceId: 1, deviceName: '设备A',
  resultType, executionStatus: 'completed', evaluated: true,
  ...extra,
})

const PAGE = (items: any[], total: number) => ({ items, total, page: 1, perPage: 50 })

async function mountWizard() {
  // INT-1110：向导两阶段（阶段 1 选任务 → 阶段 2 选结果）；本 spec 锁阶段 2 结果类型
  // 客户端过滤 → 以预选任务直达阶段 2（§3.8.1 批量「加入挑选」口径）
  const w = mount(CherryPickWizard, { props: { presetTaskIds: [10] } })
  await flushPromises()
  return w
}

function treeLeafIds(w: any): number[] {
  const roots = w.findComponent({ name: 'PickTreeStub' }).props('roots') as any[]
  return collectLeafResultIds(roots)
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  api.listCandidates.mockResolvedValue(PAGE([
    CAND(1, 'asr'), CAND(2, 'asr'), CAND(3, 'tts'), CAND(4, 'default'),
  ], 4))
  api.tasksGetAll.mockResolvedValue({ items: [] })
  api.devicesGetAllFlat.mockResolvedValue([])
  api.preview.mockResolvedValue({
    totalResults: 0, invalidResultIds: [], sourceTaskCount: 0, sourceTaskIds: [],
    deviceIds: [], deviceNames: [], caseCount: 0, executionStatusCounts: {}, duplicates: [],
  })
})

describe('CherryPickWizard 结果类型筛选器（UX 审计 P2 回归）', () => {
  it('无结果类型筛选 → 候选全量进树（4 条叶）', async () => {
    const w = await mountWizard()
    const ids = treeLeafIds(w)
    expect(ids.sort((a, b) => a - b)).toEqual([1, 2, 3, 4])
    expect(w.find('.cpw-toolbar-info').text()).toContain('共 4 条')
  })

  it('勾选结果类型 asr → 树只含 asr 命中行且计数同步为 2', async () => {
    const w = await mountWizard()
    // 阶段 2 筛选栏 select 顺序（任务 facet 锁定隐藏）：搜索 / 设备 / 结果类型 / 执行 / 评估 / 时间
    const rtSelect = w.findAll('.cpw-filter-bar select')[1]
    await rtSelect.setValue(['asr'])
    await flushPromises()

    const ids = treeLeafIds(w)
    expect(ids.sort((a, b) => a - b)).toEqual([1, 2])
    expect(w.find('.cpw-toolbar-info').text()).toContain('共 2 条')
  })

  it('设备视图同样按结果类型过滤行（三视图共享同一候选源）', async () => {
    const w = await mountWizard()
    const rtSelect = w.findAll('.cpw-filter-bar select')[1]
    await rtSelect.setValue(['asr'])
    await flushPromises()

    // 切设备视图：树只含 asr 命中行（叶集与用例视图一致）
    const deviceBtn = w.findAll('button').find((b) => b.text().includes('设备视图'))!
    await deviceBtn.trigger('click')
    await flushPromises()
    const ids = treeLeafIds(w)
    expect(ids.sort((a, b) => a - b)).toEqual([1, 2])
  })

  it('结果类型激活时「全选当前筛选」降级当前已加载树（不发后端 select-all，与展示一致）', async () => {
    const w = await mountWizard()
    const rtSelect = w.findAll('.cpw-filter-bar select')[1]
    await rtSelect.setValue(['asr'])
    await flushPromises()

    const selectAllBtn = w.findAll('button').find((b) => b.text().includes('全选当前筛选'))!
    await selectAllBtn.trigger('click')
    await flushPromises()

    expect(api.selectAllCandidates).not.toHaveBeenCalled()
    const vm = w.vm as any
    expect(vm.selectedResultIds.size).toBe(2)
    expect([...vm.selectedResultIds].sort((a: number, b: number) => a - b)).toEqual([1, 2])
  })

  it('未选结果类型时 select-all 仍走后端跨页全选（回归既有 §11-4 语义）', async () => {
    api.selectAllCandidates.mockResolvedValue({ resultIds: [1, 2, 3, 4] })
    const w = await mountWizard()

    const selectAllBtn = w.findAll('button').find((b) => b.text().includes('全选当前筛选'))!
    await selectAllBtn.trigger('click')
    await flushPromises()

    expect(api.selectAllCandidates).toHaveBeenCalledTimes(1)
    const vm = w.vm as any
    expect(vm.selectedResultIds.size).toBe(4)
  })
})
