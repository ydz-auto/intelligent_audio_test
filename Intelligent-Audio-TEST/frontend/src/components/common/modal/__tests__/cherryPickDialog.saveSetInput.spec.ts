/**
 * INT-286：挑选合并向导「另存挑选集」输入回归（window.prompt → INPUT_CONFIRM 表单模态）。
 *
 * 锁定口径：
 * - 购物车步骤点「另存为挑选集」打开 INPUT_CONFIRM（预填当天日期名 + 同名可重复提示）
 * - 确认载荷 trim 后随 saveAsSet 下发；取消（reject）→ 不下发
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const api = vi.hoisted(() => ({
  listCandidates: vi.fn(),
  preview: vi.fn(),
  tasksGetAll: vi.fn(),
}))
const cartApi = vi.hoisted(() => ({
  saveAsSet: vi.fn(),
}))
const modalOpen = vi.hoisted(() => vi.fn())
const notifications = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))

vi.mock('../../../../infrastructure/api', () => ({
  cherryPickApi: { listCandidates: api.listCandidates, preview: api.preview },
  tasksApi: { getAll: api.tasksGetAll },
}))
vi.mock('../../../../composables/task/usePickCart', async () => {
  const { ref, computed } = await import('vue')
  return {
    usePickCart: () => {
      const cart = ref({ groups: [], invalidItemIds: [] })
      return {
        cart,
        cartLoading: ref(false),
        cartCount: computed(() => 2),
        invalidCount: ref(0),
        sets: ref([]),
        refreshCart: vi.fn(async () => {}),
        addToCart: vi.fn(),
        removeItem: vi.fn(),
        removeItems: vi.fn(),
        clearCart: vi.fn(),
        refreshSets: vi.fn(async () => {}),
        saveAsSet: cartApi.saveAsSet,
        restoreSetToCart: vi.fn(),
        deleteSet: vi.fn(),
      }
    },
  }
})
vi.mock('../../../../composables/modal/useNotification', () => ({ useNotification: () => notifications }))
vi.mock('../../../../composables/modal/useModal', () => ({ useModalControl: () => ({ open: modalOpen }) }))

import CherryPickDialog from '../CherryPickDialog.vue'
import { MODAL_TYPES } from '../../../../composables/modal/constants'

beforeEach(() => {
  vi.clearAllMocks()
  api.listCandidates.mockResolvedValue({ items: [], total: 0 })
  api.tasksGetAll.mockResolvedValue({ items: [] })
  cartApi.saveAsSet.mockResolvedValue({ name: '我的挑选集', itemCount: 2 })
})

async function mountOnCartStep() {
  const w = mount(CherryPickDialog)
  await flushPromises()
  // 切到购物车步骤
  await w.findAll('.cp-step').find(s => s.text().includes('购物车'))!.trigger('click')
  await flushPromises()
  return w
}

describe('CherryPickDialog 另存挑选集（INT-286）', () => {
  it('打开 INPUT_CONFIRM 表单模态：预填当天日期名 + 同名可重复保存提示', async () => {
    modalOpen.mockResolvedValue({ value: '挑选集_2026-10-15' })
    const w = await mountOnCartStep()

    const saveBtn = w.findAll('button').find(b => b.text().includes('另存为挑选集'))!
    await saveBtn.trigger('click')

    expect(modalOpen).toHaveBeenCalledTimes(1)
    expect(modalOpen).toHaveBeenCalledWith(MODAL_TYPES.INPUT_CONFIRM, expect.objectContaining({
      title: '另存挑选集',
      label: '挑选集名称',
      hint: '同名允许重复保存',
      confirmText: '保存',
    }))
    expect(modalOpen.mock.calls[0][1].initialValue as string).toMatch(/^挑选集_\d{4}-\d{2}-\d{2}$/)
  })

  it('确认载荷 trim 后随 saveAsSet 下发并成功反馈', async () => {
    modalOpen.mockResolvedValue({ value: ' 我的挑选集 ' })
    const w = await mountOnCartStep()

    await w.findAll('button').find(b => b.text().includes('另存为挑选集'))!.trigger('click')
    await flushPromises()

    expect(cartApi.saveAsSet).toHaveBeenCalledWith('我的挑选集')
    expect(notifications.success).toHaveBeenCalledWith('挑选集「我的挑选集」已保存（2 条）')
  })

  it('取消（resolve null）→ 不下发 saveAsSet', async () => {
    // INT-1011：取消收敛为 resolve(null)，不再是 rejection
    modalOpen.mockResolvedValue(null)
    const w = await mountOnCartStep()

    await w.findAll('button').find(b => b.text().includes('另存为挑选集'))!.trigger('click')
    await flushPromises()

    expect(cartApi.saveAsSet).not.toHaveBeenCalled()
  })
})
