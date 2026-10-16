/**
 * INT-401：挑选合并向导交互流程修复回归锁定。
 *
 * 覆盖（负责人 2026-10-15 实测打回三条中的挑选合并流程疑点）：
 * - 设备下拉独立取设备列表（§4 设备为筛选条件，不从候选结果聚合）
 * - 「按用例搜索」改走 case_keyword 模糊搜索（原错误塞 case_ids 精确 IN，永查不到）
 * - 反选只作用当前页候选、保留跨页已选（原从当前页重建集合丢跨页选项）
 * - 整组取消（三档粒度双向，原仅单向加选）
 * - 任务详情入口预筛选（presetTaskId 定位本任务结果）
 * - 跨任务配置不一致强制确认（§5.2/§11-③）+ merge 出口任务级配置字段透传
 * - 购物车空时提交禁用门控（预览失败不再可提交）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const api = vi.hoisted(() => ({
  listCandidates: vi.fn(),
  preview: vi.fn(),
  checkout: vi.fn(),
  tasksGetAll: vi.fn(),
  devicesGetAllFlat: vi.fn(),
}))
const notifications = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))
const modalOpen = vi.hoisted(() => vi.fn())
/** 购物车条数（可变更，供空车门控用例） */
const cartCountValue = vi.hoisted(() => ({ value: 2 }))

vi.mock('../../../../infrastructure/api', () => ({
  cherryPickApi: {
    listCandidates: api.listCandidates,
    preview: api.preview,
    checkout: api.checkout,
  },
  tasksApi: { getAll: api.tasksGetAll },
  devicesApi: { getAllFlat: api.devicesGetAllFlat },
}))
vi.mock('../../../../composables/task/usePickCart', async () => {
  const { ref, computed } = await import('vue')
  return {
    usePickCart: () => {
      const cart = ref({ groups: [], invalidItemIds: [] })
      return {
        cart,
        cartLoading: ref(false),
        cartCount: computed(() => cartCountValue.value),
        invalidCount: ref(0),
        sets: ref([]),
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

import CherryPickDialog from '../CherryPickDialog.vue'
import { MODAL_TYPES } from '../../../../composables/modal/constants'

const CANDIDATE = (resultId: number, deviceId: number, caseId: string) => ({
  resultId, taskId: 10, taskName: '任务10', taskStatus: 'completed',
  caseId, deviceId, executionStatus: 'completed', evaluated: true,
})

beforeEach(() => {
  vi.clearAllMocks()
  cartCountValue.value = 2
  api.listCandidates.mockResolvedValue({ items: [], total: 0 })
  api.tasksGetAll.mockResolvedValue({ items: [] })
  api.devicesGetAllFlat.mockResolvedValue([
    { id: 1, name: '设备A' },
    { id: 2, name: '设备B' },
  ])
  modalOpen.mockReset()
})

async function mountDialog(props = {}) {
  const w = mount(CherryPickDialog, { props })
  await flushPromises()
  return w
}

describe('步骤1 挑选：筛选变更重置页码（P2-1）', () => {
  it('设备/执行状态/评估状态变更回到第 1 页再查询（避免旧页码「无符合条件」误判）', async () => {
    api.listCandidates.mockResolvedValue({ items: [], total: 0 })
    const w = await mountDialog()
    const vm = w.vm as any
    vm.filters.page = 3

    // 设备筛选变更
    await w.findAll('select')[1].setValue('1')
    await flushPromises()
    expect(api.listCandidates.mock.calls[api.listCandidates.mock.calls.length - 1][0].page).toBe(1)
    expect(vm.filters.page).toBe(1)

    // 执行状态变更
    vm.filters.page = 5
    await w.findAll('select')[2].setValue('failed')
    await flushPromises()
    expect(api.listCandidates.mock.calls[api.listCandidates.mock.calls.length - 1][0].page).toBe(1)
    expect(vm.filters.page).toBe(1)

    // 评估状态变更
    vm.filters.page = 7
    await w.findAll('select')[3].setValue('evaluated')
    await flushPromises()
    expect(api.listCandidates.mock.calls[api.listCandidates.mock.calls.length - 1][0].page).toBe(1)
  })
})

describe('步骤1 挑选：设备选项独立取设备列表（INT-401）', () => {
  it('设备下拉来自 devicesApi 独立列表（不从候选结果聚合）', async () => {
    const w = await mountDialog()
    expect(api.devicesGetAllFlat).toHaveBeenCalled()
    const devices = w.findAll('.cp-filters select')[1]
    const opts = devices.findAll('option').map(o => o.text())
    expect(opts).toContain('设备A')
    expect(opts).toContain('设备B')
  })
})

describe('步骤1 挑选：「按用例搜索」走 case_keyword（INT-401）', () => {
  it('输入关键词下发 case_keyword 而非 case_ids（精确 IN 语义区分）', async () => {
    const w = await mountDialog()
    const input = w.find('input[placeholder="按用例搜索"]')
    await input.setValue('INT339用例')
    await new Promise(r => setTimeout(r, 350))
    await flushPromises()

    const last = api.listCandidates.mock.calls[api.listCandidates.mock.calls.length - 1][0]
    expect(last.caseKeyword).toBe('INT339用例')
    expect(last.caseIds).toEqual([])
  })
})

describe('步骤1 挑选：反选保留跨页已选（INT-401）', () => {
  it('反选只切换当前页候选，不清空其他页已选', async () => {
    api.listCandidates.mockResolvedValue({
      items: [CANDIDATE(100, 1, 'C1'), CANDIDATE(101, 2, 'C2')], total: 4,
    })
    const w = await mountDialog()
    await flushPromises()
    const vm = w.vm as any
    // 模拟跨页已选 200（翻页后集合保留的既有状态）
    vm.selectedResultIds = new Set([200])

    await w.findAll('button').find(b => b.text().includes('反选'))!.trigger('click')

    const sel = vm.selectedResultIds as Set<number>
    expect(sel.has(100)).toBe(true)
    expect(sel.has(101)).toBe(true)
    expect(sel.has(200)).toBe(true)
  })
})

describe('步骤1 挑选：整组取消（INT-401 三档粒度双向）', () => {
  it('整组取消移除该组全部勾选，保留其他组已选', async () => {
    // 候选按来源任务分组：任务10 含 100/101，任务11 含 102
    api.listCandidates.mockResolvedValue({
      items: [
        { ...CANDIDATE(100, 1, 'C1'), taskId: 10, taskName: '任务10' },
        { ...CANDIDATE(101, 1, 'C2'), taskId: 10, taskName: '任务10' },
        { ...CANDIDATE(102, 2, 'C3'), taskId: 11, taskName: '任务11' },
      ],
      total: 3,
    })
    const w = await mountDialog()
    await flushPromises()
    const vm = w.vm as any
    vm.selectedResultIds = new Set([100, 101, 102, 300])

    const unselectBtn = w.findAll('button').find(b => b.text().includes('整组取消'))!
    await unselectBtn.trigger('click')

    expect(vm.selectedResultIds.has(100)).toBe(false)
    expect(vm.selectedResultIds.has(101)).toBe(false)
    expect(vm.selectedResultIds.has(102)).toBe(true)
    expect(vm.selectedResultIds.has(300)).toBe(true)
  })
})

describe('步骤1 挑选：任务详情入口预筛选（INT-401）', () => {
  it('presetTaskId 打开向导即定位该任务执行结果', async () => {
    await mountDialog({ presetTaskId: 42 })
    const first = api.listCandidates.mock.calls.find(c => c[0].taskIds?.includes(42))
    expect(first).toBeTruthy()
  })
})

describe('INT-551：候选加载失败错误态（审计 P2-1）', () => {
  it('listCandidates reject → 展示错误态（含重试），空态文案不出现', async () => {
    api.listCandidates.mockRejectedValue(new Error('网关超时'))
    const w = await mountDialog()
    const errorState = w.find('.cp-error')
    expect(errorState.exists()).toBe(true)
    expect(errorState.text()).toContain('加载执行结果失败')
    expect(errorState.text()).toContain('网关超时')
    expect(errorState.text()).toContain('重试')
    expect(w.text()).not.toContain('无符合条件的执行结果')
  })

  it('失败保留旧数据：错误条出现时旧候选列表仍展示', async () => {
    // 初次加载成功（C1）→ 随后一次刷新失败——旧数据保留，仅错误条提示（INT-289 口径）
    api.listCandidates
      .mockResolvedValueOnce({ items: [CANDIDATE(100, 1, 'C1')], total: 1 })
      .mockRejectedValueOnce(new Error('网络抖动'))
    const w = await mountDialog()
    // 触发来源任务下拉 change → loadCandidates 再次执行（本次 reject）
    await w.find('.cp-filters select').trigger('change')
    await flushPromises()
    expect(w.find('.cp-error-bar').exists()).toBe(true)
    // 旧候选仍保留展示（不落回误导空态）
    expect(w.text()).toContain('C1')
  })

  it('错误后点重试成功 → 错误态消失、候选列表正常展示', async () => {
    api.listCandidates
      .mockRejectedValueOnce(new Error('网关超时'))
      .mockResolvedValueOnce({ items: [CANDIDATE(101, 2, 'C2')], total: 1 })
    const w = await mountDialog()
    expect(w.find('.cp-error').exists()).toBe(true)
    await w.find('.cp-error .cp-btn').trigger('click')
    await flushPromises()
    expect(w.find('.cp-error').exists()).toBe(false)
    expect(w.text()).toContain('C2')
  })
})

describe('INT-551：设备选项加载失败错误提示（审计 P2-1）', () => {
  it('devicesApi reject → 显示设备列表加载失败提示（原静默空下拉）', async () => {
    api.devicesGetAllFlat.mockRejectedValue(new Error('设备服务不可用'))
    const w = await mountDialog()
    const hint = w.find('.cp-error-bar')
    expect(hint.exists()).toBe(true)
    expect(hint.text()).toContain('设备列表加载失败')
  })
})

describe('步骤3 下单：merge 任务级配置 + 跨任务配置不一致强制确认（INT-401）', () => {
  async function mountOnCheckout(previewData: any) {
    api.preview.mockResolvedValue(previewData)
    const w = await mountDialog()
    const vm = w.vm as any
    vm.preview = previewData
    await w.findAll('.cp-step').find(s => s.text().includes('下单'))!.trigger('click')
    await flushPromises()
    return w
  }

  it('configInconsistent=true → 提交前弹 BASIC_CONFIRM 确认（§11-③）', async () => {
    modalOpen.mockResolvedValue(true)
    api.checkout.mockResolvedValue({ taskId: 77, resultCount: 2 })
    const w = await mountOnCheckout({
      totalResults: 2, invalidResultIds: [], sourceTaskCount: 2,
      sourceTaskIds: [1, 2], deviceIds: [7], deviceNames: ['设备7'],
      caseCount: 2, executionStatusCounts: {}, duplicates: [],
      configInconsistent: true, configFields: ['algorithm_type'],
      sourceConfigs: [
        { taskId: 1, taskName: 'A', algorithmType: 'asr' },
        { taskId: 2, taskName: 'B', algorithmType: 'tts' },
      ],
    })
    const vm = w.vm as any
    vm.mergeName = '合并任务'
    await w.findAll('button').find(b => b.text().includes('提交下单'))!.trigger('click')
    await flushPromises()

    expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.BASIC_CONFIRM, expect.objectContaining({
      title: '跨任务配置不一致',
    }))
    expect(api.checkout).toHaveBeenCalled()
    expect(api.checkout.mock.calls[0][0].name).toBe('合并任务')
  })

  it('用户取消配置确认 → 不发 checkout', async () => {
    modalOpen.mockRejectedValue(new Error('cancel'))
    const w = await mountOnCheckout({
      totalResults: 2, invalidResultIds: [], sourceTaskCount: 2,
      sourceTaskIds: [1, 2], deviceIds: [7], deviceNames: ['设备7'],
      caseCount: 2, executionStatusCounts: {}, duplicates: [],
      configInconsistent: true, configFields: ['algorithm_params'],
    })
    const vm = w.vm as any
    vm.mergeName = '合并任务'
    await w.findAll('button').find(b => b.text().includes('提交下单'))!.trigger('click')
    await flushPromises()

    expect(api.checkout).not.toHaveBeenCalled()
  })

  it('merge 出口任务级配置字段（算法参数/配置）随 checkout 透传', async () => {
    api.checkout.mockResolvedValue({ taskId: 78 })
    const w = await mountOnCheckout({
      totalResults: 1, invalidResultIds: [], sourceTaskCount: 1,
      sourceTaskIds: [1], deviceIds: [7], deviceNames: ['设备7'],
      caseCount: 1, executionStatusCounts: {}, duplicates: [],
      configInconsistent: false,
    })
    const vm = w.vm as any
    vm.mergeName = '合并任务'
    vm.showMergeConfig = true
    vm.mergeAlgorithmType = 'tts'
    vm.mergeAlgorithmParams = '{"model":"x"}'
    vm.mergeConfig = '{"batch":2}'
    await w.findAll('button').find(b => b.text().includes('提交下单'))!.trigger('click')
    await flushPromises()

    expect(api.checkout.mock.calls[0][0]).toEqual(expect.objectContaining({
      algorithm_type: 'tts',
      algorithm_params: { model: 'x' },
      config: { batch: 2 },
    }))
  })

  it('算法参数非合法 JSON → 提示且不发 checkout', async () => {
    const w = await mountOnCheckout({
      totalResults: 1, invalidResultIds: [], sourceTaskCount: 1,
      sourceTaskIds: [1], deviceIds: [], deviceNames: [], caseCount: 1,
      executionStatusCounts: {}, duplicates: [], configInconsistent: false,
    })
    const vm = w.vm as any
    vm.mergeName = '合并任务'
    vm.showMergeConfig = true
    vm.mergeAlgorithmParams = 'not-json'
    await w.findAll('button').find(b => b.text().includes('提交下单'))!.trigger('click')
    await flushPromises()

    expect(api.checkout).not.toHaveBeenCalled()
  })
})

describe('步骤3 下单：购物车空禁用门控（INT-401）', () => {
  it('cartCount=0 时「去下单」禁用（预览失败不再可提交）', async () => {
    cartCountValue.value = 0
    const w = await mountDialog()
    await w.findAll('.cp-step').find(s => s.text().includes('购物车'))!.trigger('click')
    await flushPromises()
    const goCheckout = w.findAll('button').find(b => b.text().includes('去下单'))!
    expect(goCheckout.attributes('disabled')).toBeDefined()
  })

  it('cartCount=0 时「提交下单」禁用（下单门控）', async () => {
    cartCountValue.value = 0
    const w = await mountDialog()
    await w.findAll('.cp-step').find(s => s.text().includes('下单'))!.trigger('click')
    await flushPromises()
    const submit = w.findAll('button').find(b => b.text().includes('提交下单'))!
    expect(submit.attributes('disabled')).toBeDefined()
  })
})
