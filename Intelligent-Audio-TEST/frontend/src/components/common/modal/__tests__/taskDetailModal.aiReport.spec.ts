/**
 * INT-738 D02：任务详情「生成 AI 报告」入口按钮契约 —— 组件单测。
 *
 * 锁定口径（随 08_灵犀Agent 卡落地 /ai-chat 路由，先留按钮契约）：
 * - 任务加载成功：详情头部动作区渲染「生成 AI 报告」按钮（btn-primary，不落 .step-actions 既有按钮集）
 * - 点击跳转 /ai-chat?task={id}（router.push，hash 路由下不裸 path）
 * - 任务加载失败（error）：内容区整体为错误态，AI 按钮不渲染
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  getOne: vi.fn(),
  logsGetAll: vi.fn(),
  confirmOpen: vi.fn(),
  pushes: [] as any[],
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: (loc: any) => mocks.pushes.push(loc) }),
  // INT-1838：组件同时读当前路由 query（「开始挑选」跳挑选合并页签保留既有参数）
  useRoute: () => ({ query: {} }),
}))

vi.mock('../../../../composables/task/tasksPort', () => ({
  tasksPort: {
    getOne: mocks.getOne,
    removeCase: vi.fn(),
    stop: vi.fn(),
    getProgress: vi.fn().mockResolvedValue(null),
    control: vi.fn(),
    retry: vi.fn(),
    reevaluate: vi.fn(),
  },
}))

vi.mock('../../../../composables/task/logsPort', () => ({
  logsPort: { getAll: mocks.logsGetAll },
}))

vi.mock('../../../../composables/modal/useModal', () => ({
  useModalControl: () => ({ open: mocks.confirmOpen }),
  MODAL_TYPES: { BASIC_CONFIRM: 'BASIC_CONFIRM', TEST_CASE_DETAIL: 'TEST_CASE_DETAIL', REEXECUTE_OPTIONS: 'REEXECUTE_OPTIONS' },
}))

vi.mock('../../../../composables/modal/useNotification', () => ({
  useNotification: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))

vi.mock('../../../../store/authStore', () => ({
  useAuthStore: () => ({ hasPermission: () => true }),
}))

import TaskDetailModal from '../TaskDetailModal.vue'

const TASK = {
  id: 9, name: '任务A', status: 'completed', cases: [], devices: [], apis: [],
  expectedTotalTime: '', usedTime: '', expectedCompleteTime: '',
}

describe('TaskDetailModal「生成 AI 报告」入口（INT-738 D02）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.pushes.length = 0
    mocks.logsGetAll.mockResolvedValue({ items: [], total: 0 })
    mocks.getOne.mockResolvedValue(TASK)
  })

  const mountModal = async () => {
    const w = mount(TaskDetailModal, { props: { taskId: 9 } })
    await flushPromises()
    return w
  }

  it('任务加载成功：渲染「生成 AI 报告」按钮（按钮契约，随 /ai-chat 路由落地生效）', async () => {
    const w = await mountModal()
    const btn = w.find('.task-detail-actions button.btn-primary')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toContain('生成 AI 报告')
  })

  it('点击跳转 /ai-chat?task={id}（router.push，不带路由对象时状态正确）', async () => {
    const w = await mountModal()
    await w.find('.task-detail-actions button.btn-primary').trigger('click')
    expect(mocks.pushes).toEqual([{ path: '/ai-chat', query: { task: '9' } }])
  })

  it('任务加载失败：内容区为错误态，AI 按钮不渲染', async () => {
    mocks.getOne.mockRejectedValue(new Error('boom'))
    const w = await mountModal()
    await flushPromises()
    expect(w.find('.task-detail-actions').exists()).toBe(false)
    expect(w.find('.error-state').exists()).toBe(true)
  })
})
