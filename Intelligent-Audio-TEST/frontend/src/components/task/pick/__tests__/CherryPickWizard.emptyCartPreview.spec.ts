/**
 * INT-1286 P3 回归：下单成功后购物车出清（cartRevision 递增、cart 空）不再重拉空 preview。
 *
 * 复现：submitCheckout → refreshCart() 清空购物车 → cartRevision+1 → 原 watch 在
 * step=checkout/review 时再调 loadPreview → POST /tasks/cherry-picks/preview 返回
 * 400「购物车为空」→ 控制台 SEVERE（界面无害，向导随即关闭）。
 *
 * 修复：loadPreview 空购物车守卫（cartCount=0 直接置 null 不发请求）+ cartRevision
 * watch 仅在 cartCount>0 时重拉。本 spec 锁定：① 空购物车 + 版本变化 → 不发 preview；
 * ② 非空购物车 + 版本变化 → 仍重拉 preview（回归既有 §6.3 复核摘要实时刷新）。
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
      const cartRevision = ref(0)
      return {
        cart,
        cartLoading: ref(false),
        cartCount: computed(() => cart.value.total),
        invalidCount: ref(0),
        sets: ref([]),
        resultIdSet: computed(() => new Set<number>()),
        cartRevision,
        refreshCart: vi.fn(async () => { cartRevision.value += 1 }),
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

describe('CherryPickWizard 下单成功后空购物车不再重拉 preview（INT-1286 P3）', () => {
  it('空购物车 + 购物车版本变化 → 不发 preview（下单成功出清不落 400 SEVERE）', async () => {
    const w = mount(CherryPickWizard, { props: { initialStep: 'checkout', presetTaskIds: [10] } })
    await flushPromises()
    // 初始即 checkout 步，购物车为空 → 挂载路径不主动拉 preview
    expect(api.preview).not.toHaveBeenCalled()

    // 模拟下单成功后 refreshCart 清空（cartRevision+1，cart 仍空）
    const vm = w.vm as any
    await vm.refreshCart()
    await flushPromises()

    expect(api.preview).not.toHaveBeenCalled()
  })

  it('非空购物车 + 购物车版本变化 → 仍重拉 preview（回归既有 §6.3 复核摘要实时刷新）', async () => {
    const w = mount(CherryPickWizard, { props: { initialStep: 'checkout', presetTaskIds: [10] } })
    await flushPromises()
    const vm = w.vm as any
    // 购物车非空
    vm.cart.total = 2
    await flushPromises()

    await vm.refreshCart()
    await flushPromises()

    expect(api.preview).toHaveBeenCalledTimes(1)
  })
})
