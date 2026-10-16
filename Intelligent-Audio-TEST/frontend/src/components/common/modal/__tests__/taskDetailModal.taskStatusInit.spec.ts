/**
 * INT-401 P1-3：任务详情模态窗 taskStatus 初始化 —— 组件单测。
 *
 * 锁定口径（验收打回 P1-3 复现：终态任务详情 taskStatus 卡 PENDING）：
 * - socket 对已终态任务订阅后不重发 task_progress，HTTP 兜底进度又可能被
 *   generation 竞态丢弃 → taskStatus 停在 PENDING → 挑选入口不显示、暂停/停止误显
 * - 修复：详情模态窗以 GET /tasks/{id} 返回的 status 初始化 taskStatus，
 *   终态任务一开即正确（TestExecutionComponent 操作按钮集随之对齐）
 * - 终态任务：显示「加入购物车」，不显示暂停/停止
 * - 非终态任务：不显示「加入购物车」，显示暂停/停止（活跃任务由 socket/轮询事件覆盖）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  getOne: vi.fn(),
  getProgress: vi.fn(),
  logsGetAll: vi.fn(),
  confirmOpen: vi.fn(),
  hasPermission: vi.fn(() => true),
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

// socket 已连接（isConnected=true）：不启动 HTTP 兜底轮询，也不送达任何进度事件——
// 模拟「终态任务订阅后服务端不重发 task_progress」的最不利场景，taskStatus 只能来自
// 详情接口初始化（Fix 1）。
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

const CASES = [
  { id: 'c1', name: '用例一', status: 'completed', executionStatus: 'completed', evaluationStatus: 'completed', duration: 3 },
]

const TASK_COMPLETED = {
  id: 9, name: '任务A', status: 'completed', cases: CASES, devices: [], apis: [],
  expectedTotalTime: '', usedTime: '', expectedCompleteTime: '',
}
const TASK_RUNNING = { ...TASK_COMPLETED, status: 'running' }

beforeEach(() => {
  vi.clearAllMocks()
  mocks.hasPermission.mockReturnValue(true)
  mocks.logsGetAll.mockResolvedValue({ items: [], total: 0 })
  mocks.getProgress.mockResolvedValue(null)
})

const mountModal = async (taskData: any) => {
  mocks.getOne.mockResolvedValue(taskData)
  const w = mount(TaskDetailModal, { props: { taskId: 9 } })
  await flushPromises()
  return w
}

describe('TaskDetailModal taskStatus 初始化（INT-401 P1-3）', () => {
  it('终态任务：详情接口 status 初始化 taskStatus → 「加入购物车」可见、暂停/停止隐藏', async () => {
    const w = await mountModal(TASK_COMPLETED)

    const pick = w.find('.step-actions button.btn-info')
    expect(pick.exists(), '终态任务应展示「加入购物车」挑选入口').toBe(true)
    expect(pick.text()).toContain('加入购物车')
    // 终态任务不展示暂停/停止（操作按钮集由 taskStatus 驱动，不得误显）
    expect(w.find('.step-actions button.btn-danger').exists()).toBe(false)
    expect(w.find('.step-actions button.btn-secondary').exists()).toBe(false)
  })

  it('非终态（running）任务：不展示挑选入口，展示暂停/停止', async () => {
    const w = await mountModal(TASK_RUNNING)

    expect(w.find('.step-actions button.btn-info').exists(), '运行中任务不展示挑选入口').toBe(false)
    expect(w.find('.step-actions button.btn-danger').exists(), '运行中任务展示停止').toBe(true)
    expect(w.find('.step-actions button.btn-secondary').exists(), '运行中任务展示暂停/继续').toBe(true)
  })

  it('终态任务无 task:cherry_pick 权限 → 挑选入口隐藏（权限门控独立于 status 初始化）', async () => {
    mocks.hasPermission.mockReturnValue(false)
    const w = await mountModal(TASK_COMPLETED)

    expect(w.find('.step-actions button.btn-info').exists()).toBe(false)
    expect(w.find('.step-actions button.btn-danger').exists()).toBe(false)
  })
})
