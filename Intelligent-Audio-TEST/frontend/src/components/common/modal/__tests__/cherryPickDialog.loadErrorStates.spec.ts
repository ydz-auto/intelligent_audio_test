/**
 * INT-551：挑选向导候选加载失败错误态——失败不得静默降级为误导性空态。
 *
 * 覆盖（INT-401 前端UX审计 P2-1）：
 * - 候选接口 reject → 展示错误态（含重试）而非「无符合条件的执行结果」空态文案
 * - 错误态重试 → 重新拉取候选，成功后恢复列表
 * - 设备选项加载失败 → 可见降级提示 + 重试（原仅 console.error 无 UI 反馈）
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
/** 购物车条数（可变更，供门控类用例） */
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

describe('步骤1 挑选：候选加载失败错误态（INT-551）', () => {
  it('候选接口 reject → 展示错误态文案而非「无符合条件的执行结果」空态', async () => {
    api.listCandidates.mockRejectedValue(new Error('server down'))
    const w = await mountDialog()

    // 不再出现误导性空态
    expect(w.find('.cp-empty').exists()).toBe(false)
    expect(w.text()).not.toContain('无符合条件的执行结果')
    // 展示可见错误态 + 重试入口
    const errorState = w.find('.cp-error')
    expect(errorState.exists()).toBe(true)
    expect(errorState.text()).toContain('加载执行结果失败')
    expect(errorState.text()).toContain('重试')
  })

  it('错误态重试 → 重新拉取候选，成功后恢复列表', async () => {
    api.listCandidates.mockRejectedValueOnce(new Error('server down'))
    const w = await mountDialog()
    expect(w.find('.cp-error').exists()).toBe(true)

    api.listCandidates.mockResolvedValueOnce({
      items: [{ resultId: 1, taskId: 10, taskName: '任务10', caseId: 'C1', deviceId: 1, executionStatus: 'completed', evaluated: true }],
      total: 1,
    })
    await w.find('.cp-error button').trigger('click')
    await flushPromises()

    expect(w.find('.cp-error').exists()).toBe(false)
    expect(w.find('.cp-empty').exists()).toBe(false)
    expect(w.find('.cp-row').exists()).toBe(true)
  })
})

describe('步骤1 挑选：设备选项加载失败降级提示（INT-551）', () => {
  it('设备接口 reject → 可见「设备列表加载失败」+ 重试，不静默', async () => {
    api.devicesGetAllFlat.mockRejectedValue(new Error('net down'))
    const w = await mountDialog()

    const bar = w.find('.cp-error-bar')
    expect(bar.exists()).toBe(true)
    expect(bar.text()).toContain('设备列表加载失败')
    expect(bar.text()).toContain('重试')
  })

  it('设备重试成功 → 降级提示消失，设备下拉恢复', async () => {
    api.devicesGetAllFlat.mockRejectedValueOnce(new Error('net down'))
    const w = await mountDialog()
    expect(w.find('.cp-error-bar').exists()).toBe(true)

    api.devicesGetAllFlat.mockResolvedValueOnce([{ id: 1, name: '设备A' }, { id: 2, name: '设备B' }])
    await w.find('.cp-error-bar button').trigger('click')
    await flushPromises()

    expect(w.find('.cp-error-bar').exists()).toBe(false)
    const devices = w.findAll('.cp-filters select')[1]
    const opts = devices.findAll('option').map(o => o.text())
    expect(opts).toContain('设备A')
  })
})
