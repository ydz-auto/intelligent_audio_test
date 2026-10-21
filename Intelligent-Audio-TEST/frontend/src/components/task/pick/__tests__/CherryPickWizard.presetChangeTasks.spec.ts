/**
 * INT-1110 代码审计 01a15e8a P1 回归：预选任务直达阶段 2 后「更换任务」回阶段 1 任务列表为空。
 *
 * 根因：preset 路径以阶段 2 挂载（phase 初值 = props.presetTaskIds?.length ? 'results' : 'tasks'），
 * onMounted 只跑 loadCandidates()（阶段 2 分支），loadAllCandidates() 从未执行；
 * 「更换任务」按钮仅翻转 phase 无加载调用 → taskRows（computed 自空 allCandidates）恒 0 行，
 * PickTaskStage 空态无恢复入口（死路）。
 *
 * 修复：goChangeTasks() 显式函数——phase 置 'tasks' + loadAllCandidates()；
 * 模板「更换任务」绑 @click="goChangeTasks"；P3 顺手：loadAllCandidates 按页拉满（>200 不丢页尾）。
 *
 * 本 spec 锁定：① preset 直达阶段 2 →「更换任务」回阶段 1 任务行非空（loadAllCandidates 真正执行）；
 * ② 阶段 2 已勾选结果跨「更换任务」往返保留；③ 多页候选时 loadAllCandidates 拉满（P3）。
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
vi.mock('../PickTree.vue', () => ({
  default: {
    name: 'PickTreeStub',
    props: ['roots', 'selected', 'expandedKeys', 'alreadyAdded', 'leafMeta'],
    template: '<div class="pick-tree-stub" />',
  },
}))
vi.mock('../PickCaseOrgList.vue', () => ({
  default: {
    name: 'PickCaseOrgListStub',
    props: ['roots', 'selected', 'expandedKeys', 'alreadyAdded', 'leafMeta', 'org', 'subView'],
    template: '<div class="pick-case-org-list-stub" />',
  },
}))
vi.mock('../CartTree.vue', () => ({
  default: { name: 'CartTreeStub', props: ['roots'], template: '<div class="cart-tree-stub" />' },
}))

import CherryPickWizard from '../CherryPickWizard.vue'

/** 候选行：taskId 入 extra（阶段 1 任务行按 taskId 聚合计数） */
const CAND = (resultId: number, taskId: number, extra: Record<string, any> = {}) => ({
  resultId, taskId, taskName: `任务${taskId}`, taskStatus: 'completed',
  caseId: `C${resultId}`, caseName: `用例${resultId}`,
  deviceId: 1, deviceName: '设备A',
  resultType: 'asr', executionStatus: 'completed', evaluated: true,
  ...extra,
})

const PAGE = (items: any[], total: number) => ({ items, total, page: 1, perPage: 50 })

/** 阶段 2 候选（任务集锁定）+ 阶段 1 全量候选（perPage 200，无 taskIds）双口径 mock */
function mockDualSource(taskCandidates: any[], allCandidates: any[], allTotal?: number) {
  api.listCandidates.mockImplementation((params: any) => {
    if (params?.perPage === 200) return Promise.resolve(PAGE(allCandidates, allTotal ?? allCandidates.length))
    return Promise.resolve(PAGE(taskCandidates, taskCandidates.length))
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  api.tasksGetAll.mockResolvedValue({ items: [] })
  api.devicesGetAllFlat.mockResolvedValue([])
  api.preview.mockResolvedValue({
    totalResults: 0, invalidResultIds: [], sourceTaskCount: 0, sourceTaskIds: [],
    deviceIds: [], deviceNames: [], caseCount: 0, executionStatusCounts: {}, duplicates: [],
  })
})

describe('CherryPickWizard 预选直达阶段 2 →「更换任务」回阶段 1（审计 01a15e8a P1 回归）', () => {
  it('preset 挂载直达阶段 2；「更换任务」后阶段 1 任务行非空（loadAllCandidates 补载）', async () => {
    mockDualSource(
      [CAND(1, 10)],
      [CAND(1, 10), CAND(2, 11)],
    )
    const w = mount(CherryPickWizard, { props: { presetTaskIds: [10] } })
    await flushPromises()

    // 挂载即阶段 2（§3.8.1 预选直达）
    expect(w.find('.cpw-phase-title').text()).toContain('阶段 2：选择结果')
    expect(api.listCandidates).toHaveBeenCalledWith(expect.objectContaining({ taskIds: [10], perPage: 50 }))

    // 「更换任务」→ 回阶段 1，任务列表按全量候选聚合且非空
    const changeBtn = w.findAll('button').find((b) => b.text().includes('更换任务'))!
    await changeBtn.trigger('click')
    await flushPromises()

    expect(w.find('.pts-title').text()).toContain('阶段 1：选择任务')
    expect(api.listCandidates).toHaveBeenLastCalledWith(expect.objectContaining({ perPage: 200 }))
    expect(api.listCandidates).not.toHaveBeenLastCalledWith(expect.objectContaining({ taskIds: [10] }))
    const rows = w.findAll('.pts-row')
    expect(rows.length).toBe(2)
    expect(rows.map((r) => r.text()).some((t) => t.includes('任务10'))).toBe(true)
    expect(rows.map((r) => r.text()).some((t) => t.includes('任务11'))).toBe(true)
  })

  it('阶段 2 已勾选结果跨「更换任务」往返保留；重新勾选任务后下一步候选按新任务集重拉', async () => {
    mockDualSource(
      [CAND(1, 10), CAND(2, 10)],
      [CAND(1, 10), CAND(2, 10), CAND(3, 11)],
    )
    const w = mount(CherryPickWizard, { props: { presetTaskIds: [10] } })
    await flushPromises()

    // 阶段 2 勾选 1 条结果（跨阶段保留口径）
    const vm = w.vm as any
    vm.onToggleLeaf(1)
    await flushPromises()
    expect(vm.selectedResultIds.has(1)).toBe(true)

    // 更换任务 → 阶段 1：预选任务 10 仍在勾选态，追加任务 11
    const changeBtn = w.findAll('button').find((b) => b.text().includes('更换任务'))!
    await changeBtn.trigger('click')
    await flushPromises()
    expect(w.find('.pts-title').text()).toContain('阶段 1')
    const task11Checkbox = w.findAll('.pts-row').find((r) => r.text().includes('任务11'))!
      .find('input[type="checkbox"]')
    await task11Checkbox.setValue(true)
    await flushPromises()

    // 下一步 → 回阶段 2，候选按新任务集（10+11）重拉，结果勾选保留
    const nextBtn = w.findAll('button').find((b) => b.text().includes('下一步'))!
    await nextBtn.trigger('click')
    await flushPromises()

    expect(w.find('.cpw-phase-title').text()).toContain('阶段 2：选择结果')
    expect(api.listCandidates).toHaveBeenLastCalledWith(expect.objectContaining({ taskIds: [10, 11], perPage: 50 }))
    expect(vm.selectedResultIds.has(1)).toBe(true)
  })

  it('P3：候选总量 >200 时 loadAllCandidates 按页拉满（阶段 1 不丢页尾任务）', async () => {
    api.listCandidates.mockImplementation((params: any) => {
      if (params?.perPage === 200) {
        if (params.page === 2) return Promise.resolve(PAGE([CAND(3, 12), CAND(4, 13)], 4))
        return Promise.resolve(PAGE([CAND(1, 10), CAND(2, 11)], 4))
      }
      return Promise.resolve(PAGE([CAND(1, 10)], 1))
    })
    const w = mount(CherryPickWizard, { props: { presetTaskIds: [10] } })
    await flushPromises()

    const changeBtn = w.findAll('button').find((b) => b.text().includes('更换任务'))!
    await changeBtn.trigger('click')
    await flushPromises()

    const rows = w.findAll('.pts-row')
    expect(rows.length).toBe(4)
    // 第 2 页候选任务也进入阶段 1（P3 修复点）
    expect(rows.map((r) => r.text()).some((t) => t.includes('任务12'))).toBe(true)
    expect(rows.map((r) => r.text()).some((t) => t.includes('任务13'))).toBe(true)
  })
})
