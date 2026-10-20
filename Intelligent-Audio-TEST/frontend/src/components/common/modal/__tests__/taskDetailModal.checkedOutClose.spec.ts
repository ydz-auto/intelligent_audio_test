/**
 * INT-1007：挑选合并下单成功后，任务详情模态窗须随路由跳转一并关闭 —— 组件单测。
 *
 * 复现背景（INT-921 模态窗验收实测）：任务详情模态窗（GlobalModalContainer TASK_DETAIL）内
 * 「加入购物车」→ CherryPickDialog 下单成功 emit('checked-out') 后，宿主只关 CherryPickDialog
 * + router.push，父级 TASK_DETAIL 模态残留在全局 modal manager，覆盖跳转后所有页面
 * （顶栏被遮罩拦截，elementFromPoint 命中 modal-overlay active）。
 * 修复：handleCheckedOut 在跳转前 emit('close')，GlobalModalContainer 监听 close → 关闭父级模态。
 *
 * 锁定口径：
 * - checked-out 携带 taskId：先 emit close 再跳转 /tasks/{id}（随跳转一并关闭，无残留）；
 * - checked-out 无 taskId（如空来源 reevaluate）：不跳转、不关闭父级模态（仅关向导弹层停留当前页）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  getOne: vi.fn(),
  getProgress: vi.fn(),
  logsGetAll: vi.fn(),
  confirmOpen: vi.fn(),
  hasPermission: vi.fn(() => true),
  pushes: [] as any[],
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: (loc: any) => mocks.pushes.push(loc) }),
}))

vi.mock('../../../../composables/task/tasksPort', () => ({
  tasksPort: {
    getOne: mocks.getOne,
    getProgress: mocks.getProgress,
    removeCase: vi.fn(),
    stop: vi.fn(),
    control: vi.fn(),
    retry: vi.fn(),
    reevaluate: vi.fn(),
  },
}))

vi.mock('../../../../composables/task/logsPort', () => ({
  logsPort: { getAll: mocks.logsGetAll },
}))

// socket 已连接（isConnected=true）：taskStatus 只能来自详情接口初始化（同 taskStatusInit 单测口径）
vi.mock('../../../../composables/task/taskChannelPort', () => ({
  taskChannelPort: {
    onTaskProgress: () => () => {},
    onTaskLog: () => () => {},
    subscribeTask: vi.fn(),
    unsubscribeTask: vi.fn(),
    isConnected: () => true,
    onConnectionChange: () => () => {},
  },
}))

vi.mock('../../../../store/authStore', () => ({
  useAuthStore: () => ({ hasPermission: mocks.hasPermission }),
}))

vi.mock('../../../../composables/modal/useModal', () => ({
  useModalControl: () => ({ open: mocks.confirmOpen }),
  MODAL_TYPES: { BASIC_CONFIRM: 'BASIC_CONFIRM', TEST_CASE_DETAIL: 'TEST_CASE_DETAIL', REEXECUTE_OPTIONS: 'REEXECUTE_OPTIONS' },
}))

vi.mock('../../../../composables/modal/useNotification', () => ({
  useNotification: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))

import TaskDetailModal from '../TaskDetailModal.vue'
import CherryPickDialog from '../CherryPickDialog.vue'

const TASK_COMPLETED = {
  id: 9, name: '任务A', status: 'completed', cases: [], devices: [], apis: [],
  expectedTotalTime: '', usedTime: '', expectedCompleteTime: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.hasPermission.mockReturnValue(true)
  mocks.pushes.length = 0
  mocks.logsGetAll.mockResolvedValue({ items: [], total: 0 })
  mocks.getProgress.mockResolvedValue(null)
})

describe('TaskDetailModal 下单成功关闭父级模态（INT-1007）', () => {
  const mountModal = async () => {
    mocks.getOne.mockResolvedValue(TASK_COMPLETED)
    const w = mount(TaskDetailModal, {
      props: { taskId: 9 },
      global: { stubs: { CherryPickDialog: true } },
    })
    await flushPromises()
    return w
  }

  it('checked-out 携带 taskId：先 emit close 再跳转 /tasks/{id}（父级模态随跳转关闭）', async () => {
    const w = await mountModal()

    // 终态任务 → 点击「加入购物车」打开挑选向导（CherryPickDialog 以 stub 渲染，不触真实 API）
    await w.find('.step-actions button.btn-info').trigger('click')
    const dialog = w.findComponent(CherryPickDialog)
    expect(dialog.exists(), '挑选向导应已打开').toBe(true)

    // 下单成功：CherryPickDialog 向宿主 emit checked-out
    dialog.vm.$emit('checked-out', { action: 'merge', taskId: 100 })
    await flushPromises()

    expect(w.emitted('close'), '跳转前应 emit close 关闭父级 TASK_DETAIL 模态').toBeTruthy()
    expect(mocks.pushes).toEqual(['/tasks/100'])
  })

  it('checked-out 无 taskId（如空来源 reevaluate）：不跳转、不关闭父级模态', async () => {
    const w = await mountModal()

    await w.find('.step-actions button.btn-info').trigger('click')
    const dialog = w.findComponent(CherryPickDialog)
    dialog.vm.$emit('checked-out', { action: 'reevaluate', taskId: undefined })
    await flushPromises()

    expect(w.emitted('close'), '无跳转场景不关闭父级模态').toBeFalsy()
    expect(mocks.pushes).toEqual([])
  })
})
