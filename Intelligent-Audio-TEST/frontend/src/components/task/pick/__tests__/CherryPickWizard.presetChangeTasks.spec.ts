/**
 * INT-1110 代码审计 01a15e8a P1 回归：预选任务直达阶段 2 后「更换任务」回阶段 1 任务列表为空。
 * INT-1286：阶段 1 任务行数据源由「候选行聚合」改为「终态任务列表（GET /tasks）」——
 * 不再逐页拉全候选（真实库候选 3614 条单页 8~60s 且偶发 Deadline Exceeded 落 SEVERE）；
 * 候选计数按任务 per_page=1 轻量并行拉取，非阻塞渐进填充，失败降级「—」。
 *
 * 本 spec 锁定：① preset 直达阶段 2 →「更换任务」回阶段 1 任务行非空（任务列表补载）；
 * ② 阶段 2 已勾选结果跨「更换任务」往返保留；③ 任务行覆盖终态任务列表全部任务
 * （非候选行分页），候选计数按任务拉取并展示。
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

/** 候选行：taskId 入 extra（阶段 1 任务行按 taskId 聚合计数——INT-1286 起不再使用） */
const CAND = (resultId: number, taskId: number, extra: Record<string, any> = {}) => ({
  resultId, taskId, taskName: `任务${taskId}`, taskStatus: 'completed',
  caseId: `C${resultId}`, caseName: `用例${resultId}`,
  deviceId: 1, deviceName: '设备A',
  resultType: 'asr', executionStatus: 'completed', evaluated: true,
  ...extra,
})

const PAGE = (items: any[], total: number) => ({ items, total, page: 1, perPage: 50 })

/** 终态任务行（GET /tasks items 条目） */
const TASK = (id: number, status = 'completed', name?: string) => ({
  id, name: name ?? `任务${id}`, status, createdAt: '2026-01-01T00:00:00',
})

/**
 * 双数据源 mock（INT-1286）：
 * - 阶段 1 任务行 ← tasksGetAll（终态任务列表）
 * - 阶段 2 候选 ← listCandidates perPage=50（taskIds 任务集）
 * - 阶段 1 计数 ← listCandidates perPage=1（单任务 total）
 */
function mockSource(opts: {
  tasks?: any[]
  taskCandidates?: any[]
  counts?: Record<number, number>
}) {
  const { tasks = [], taskCandidates = [], counts = {} } = opts
  api.tasksGetAll.mockResolvedValue({ items: tasks, total: tasks.length, page: 1, perPage: 50, pages: 1 })
  api.listCandidates.mockImplementation((params: any) => {
    if (params?.perPage === 1) {
      const tid = Number(params.taskIds?.[0])
      return Promise.resolve({ items: [], total: counts[tid] ?? 0, page: 1, perPage: 1 })
    }
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

describe('CherryPickWizard 预选直达阶段 2 →「更换任务」回阶段 1（审计 01a15e8a P1 回归 + INT-1286）', () => {
  it('preset 挂载直达阶段 2；「更换任务」后阶段 1 任务行非空（任务列表补载）', async () => {
    mockSource({
      tasks: [TASK(10), TASK(11)],
      taskCandidates: [CAND(1, 10)],
    })
    const w = mount(CherryPickWizard, { props: { presetTaskIds: [10] } })
    await flushPromises()

    // 挂载即阶段 2（§3.8.1 预选直达）
    expect(w.find('.cpw-phase-title').text()).toContain('阶段 2：选择结果')
    expect(api.listCandidates).toHaveBeenCalledWith(expect.objectContaining({ taskIds: [10], perPage: 50 }))

    // 「更换任务」→ 回阶段 1，任务行来自终态任务列表且非空
    const changeBtn = w.findAll('button').find((b) => b.text().includes('更换任务'))!
    await changeBtn.trigger('click')
    await flushPromises()

    expect(w.find('.pts-title').text()).toContain('阶段 1：选择任务')
    expect(api.tasksGetAll).toHaveBeenCalled()
    const rows = w.findAll('.pts-row')
    expect(rows.length).toBe(2)
    expect(rows.map((r) => r.text()).some((t) => t.includes('任务10'))).toBe(true)
    expect(rows.map((r) => r.text()).some((t) => t.includes('任务11'))).toBe(true)
  })

  it('阶段 2 已勾选结果跨「更换任务」往返保留；重新勾选任务后下一步候选按新任务集重拉', async () => {
    mockSource({
      tasks: [TASK(10), TASK(11)],
      taskCandidates: [CAND(1, 10), CAND(2, 10)],
    })
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

  it('INT-1286：任务行覆盖终态任务列表全部任务（非候选行分页），候选计数按任务拉取并展示', async () => {
    // 候选行只覆盖 10/11（首 200 内），任务 12/13 不在候选分页——任务列表仍全部出行
    mockSource({
      tasks: [TASK(10), TASK(11), TASK(12), TASK(13)],
      taskCandidates: [CAND(1, 10), CAND(2, 11)],
      counts: { 10: 5, 11: 2, 12: 3, 13: 0 },
    })
    const w = mount(CherryPickWizard, { props: { presetTaskIds: [10] } })
    await flushPromises()

    const changeBtn = w.findAll('button').find((b) => b.text().includes('更换任务'))!
    await changeBtn.trigger('click')
    await flushPromises()

    const rows = w.findAll('.pts-row')
    expect(rows.length).toBe(4)
    // 候选分页之外的页尾任务也进入阶段 1（INT-1286 修复点：数据源=任务列表）
    expect(rows.map((r) => r.text()).some((t) => t.includes('任务12'))).toBe(true)
    expect(rows.map((r) => r.text()).some((t) => t.includes('任务13'))).toBe(true)
    // 候选计数按任务 per_page=1 拉取并展示
    expect(api.listCandidates).toHaveBeenCalledWith(
      expect.objectContaining({ taskIds: [12], perPage: 1 }),
      expect.objectContaining({ silentError: true }),
    )
    expect(rows.map((r) => r.text()).some((t) => t.includes('3 条'))).toBe(true)
  })

  it('INT-1286：任务列表加载失败 → 阶段 1 错误态可见重试（静默请求不落 SEVERE）', async () => {
    // 任务列表（GET /tasks）失败 → isError 错误态 + 重试钮；重试成功后出行
    api.tasksGetAll
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue({ items: [TASK(10), TASK(11)], total: 2, page: 1, perPage: 50, pages: 1 })
    api.listCandidates.mockResolvedValue(PAGE([CAND(1, 10)], 1))

    const w = mount(CherryPickWizard, { props: {} })
    await flushPromises()

    expect(w.find('.pts-error').text()).toContain('可挑选任务加载失败，请重试')
    // 失败请求静默（silentError），调用方不落 error 级日志
    expect(api.tasksGetAll).toHaveBeenCalledWith(
      expect.objectContaining({ perPage: 50, page: 1 }),
      expect.objectContaining({ silentError: true }),
    )

    const retryBtn = w.findAll('button').find((b) => b.text().includes('重试'))!
    await retryBtn.trigger('click')
    await flushPromises()
    expect(w.findAll('.pts-row').length).toBe(2)
  })
})
