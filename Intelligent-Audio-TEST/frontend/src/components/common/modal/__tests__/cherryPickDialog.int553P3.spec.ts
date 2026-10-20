/**
 * INT-553：挑选向导 P3 批次（INT-401 前端UX审计 P3-1/P3-2/P3-3）回归锁定。
 *
 * 覆盖：
 * - P3-1 筛选变更（设备/执行状态/评估状态下拉 + 按用例搜索）统一重置 page=1 后重拉，
 *   避免非首页切换筛选落到无数据页（原仅 taskId 重置分页）
 * - P3-2 步骤条非顺序跳转受限：挑选态不可直达下单；顺序经购物车可进下单；
 *   购物车为空时下单步骤亦不可点；任意位置可后退
 * - P3-3 merge 出口名称空值提交按钮禁用（与表单必填校验一致化；reexecute 名称仍可选）
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

import CherryPickDialog from '../CherryPickDialog.vue'

beforeEach(() => {
  vi.clearAllMocks()
  cartCountValue.value = 2
  api.listCandidates.mockResolvedValue({ items: [], total: 0 })
  api.preview.mockResolvedValue({ totalResults: 0, sourceTaskCount: 0, deviceNames: [], caseCount: 0, duplicates: [] })
  api.tasksGetAll.mockResolvedValue({ items: [] })
  api.devicesGetAllFlat.mockResolvedValue([
    { id: 1, name: '设备A' },
    { id: 2, name: '设备B' },
  ])
  modalOpen.mockReset()
})

async function mountDialog() {
  const w = mount(CherryPickDialog)
  await flushPromises()
  return w
}

function lastCandidateCall() {
  return api.listCandidates.mock.calls[api.listCandidates.mock.calls.length - 1][0]
}

const STEP = (w: any, label: string) => w.findAll('.cp-step').find((s: any) => s.text().includes(label))!

describe('步骤1 挑选：筛选变更重置分页（INT-553 P3-1）', () => {
  it('设备下拉变更 → page 重置为 1 后重拉', async () => {
    const w = await mountDialog()
    ;(w.vm as any).filters.page = 3
    await w.findAll('.cp-filters select')[1].setValue('1') // 设备下拉
    await flushPromises()
    const call = lastCandidateCall()
    expect(call.page).toBe(1)
    expect(call.deviceIds).toEqual([1])
  })

  it('执行状态下拉变更 → page 重置为 1 后重拉', async () => {
    const w = await mountDialog()
    ;(w.vm as any).filters.page = 3
    await w.findAll('.cp-filters select')[2].setValue('failed') // 执行状态
    await flushPromises()
    const call = lastCandidateCall()
    expect(call.page).toBe(1)
    expect(call.executionStatus).toBe('failed')
  })

  it('评估状态下拉变更 → page 重置为 1 后重拉', async () => {
    const w = await mountDialog()
    ;(w.vm as any).filters.page = 3
    await w.findAll('.cp-filters select')[3].setValue('evaluated') // 评估状态
    await flushPromises()
    const call = lastCandidateCall()
    expect(call.page).toBe(1)
    expect(call.evaluationStatus).toBe('evaluated')
  })

  it('「按用例搜索」变更（防抖）→ page 重置为 1 后重拉', async () => {
    const w = await mountDialog()
    ;(w.vm as any).filters.page = 3
    const input = w.find('input[placeholder="按用例搜索"]')
    await input.setValue('INT553用例')
    await new Promise(r => setTimeout(r, 350))
    await flushPromises()
    const call = lastCandidateCall()
    expect(call.page).toBe(1)
    expect(call.caseKeyword).toBe('INT553用例')
  })
})

describe('步骤条：非顺序跳转受限（INT-553 P3-2）', () => {
  it('挑选态直接点击「下单」步骤被拦截，停留挑选页且该步带 locked 态', async () => {
    const w = await mountDialog()
    const vm = w.vm as any
    expect(vm.step).toBe('pick')
    await STEP(w, '下单').trigger('click')
    await flushPromises()
    expect(vm.step).toBe('pick')
    expect(STEP(w, '下单').classes()).toContain('locked')
  })

  it('挑选态可顺序前进到「购物车」（前进一格）', async () => {
    const w = await mountDialog()
    const vm = w.vm as any
    await STEP(w, '购物车').trigger('click')
    await flushPromises()
    expect(vm.step).toBe('cart')
  })

  it('购物车非空：购物车态点「下单」顺序前进到 checkout 并加载预览', async () => {
    const w = await mountDialog()
    const vm = w.vm as any
    await STEP(w, '购物车').trigger('click')
    await flushPromises()
    await STEP(w, '下单').trigger('click')
    await flushPromises()
    expect(vm.step).toBe('checkout')
    expect(api.preview).toHaveBeenCalled()
  })

  it('购物车为空：购物车态点「下单」步骤被拦截', async () => {
    cartCountValue.value = 0
    const w = await mountDialog()
    const vm = w.vm as any
    await STEP(w, '购物车').trigger('click')
    await flushPromises()
    await STEP(w, '下单').trigger('click')
    await flushPromises()
    expect(vm.step).toBe('cart')
    expect(STEP(w, '下单').classes()).toContain('locked')
  })

  it('checkout 态可后退到「挑选」（任意位置可后退）', async () => {
    const w = await mountDialog()
    const vm = w.vm as any
    vm.step = 'checkout'
    await flushPromises()
    await STEP(w, '挑选').trigger('click')
    await flushPromises()
    expect(vm.step).toBe('pick')
  })
})

describe('步骤3 下单：merge 出口名称必填禁用（INT-553 P3-3）', () => {
  it('merge 出口名称空值 → 提交按钮禁用（含纯空白）', async () => {
    const w = await mountDialog()
    const vm = w.vm as any
    vm.step = 'checkout'
    await flushPromises()
    const submit = w.findAll('button').find(b => b.text().includes('提交下单'))!
    expect(vm.action).toBe('merge')
    expect(submit.attributes('disabled')).toBeDefined()

    vm.mergeName = '   '
    await flushPromises()
    expect(submit.attributes('disabled')).toBeDefined()
  })

  it('merge 出口名称非空 → 提交按钮可用', async () => {
    const w = await mountDialog()
    const vm = w.vm as any
    vm.step = 'checkout'
    await flushPromises()
    const submit = w.findAll('button').find(b => b.text().includes('提交下单'))!
    vm.mergeName = '合并任务'
    await flushPromises()
    expect(submit.attributes('disabled')).toBeUndefined()
  })

  it('reexecute 出口名称为空 → 提交按钮仍可用（名称可选）', async () => {
    const w = await mountDialog()
    const vm = w.vm as any
    vm.step = 'checkout'
    vm.action = 'reexecute'
    await flushPromises()
    const submit = w.findAll('button').find(b => b.text().includes('提交下单'))!
    expect(submit.attributes('disabled')).toBeUndefined()
  })
})
