/**
 * INT-553 P3-4：legacy 状态挑选入口前后一致 —— 入口可见性与 openCherryPick 门控
 * 同源 PICKABLE_STATUSES（domain/enums.ts），禁止散落字面量。
 *
 * 锁定口径（INT-339 §10 默认仅终态任务可挑选）：
 * - completed/failed/stopped：执行详情窗「加入购物车」按钮可见
 * - 后端历史遗留 'finished'/'success' 不在集合内——入口不可见即不可点，
 *   消除「按钮可见但点击仅 warning」的前后口径不一致
 * - 非终态（pending/queued/running/paused/skipped/merged）同样不可见
 * - TaskDetailModal 详情窗内渲染口径与 TestExecutionComponent 一致
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import { TaskStatus, PICKABLE_STATUSES } from '@/domain/enums'
import TestExecutionComponent from '../TestExecutionComponent.vue'
import TaskDetailModal from '../../common/modal/TaskDetailModal.vue'

// INT-401：挑选入口权限门控（task:cherry_pick）——测试环境无 Pinia，mock 授权为全放行
const authMock = vi.hoisted(() => ({ hasPermission: vi.fn(() => true) }))
vi.mock('../../../store/authStore', () => ({
  useAuthStore: () => ({ hasPermission: authMock.hasPermission }),
}))

const PICK_BTN = '.step-actions button.btn-info'

const mountExec = (taskStatus: string) =>
  mount(TestExecutionComponent, {
    props: {
      testType: 'API',
      taskInfo: {},
      associatedCases: [],
      associatedDevices: [],
      showLogs: false,
      activeTab: 'cases',
      taskStatus,
    },
  })

describe('TestExecutionComponent 挑选入口门控（INT-553 P3-4）', () => {
  it('枚举单一源：PICKABLE_STATUSES 恰为 completed/failed/stopped 三态', () => {
    expect([...PICKABLE_STATUSES]).toEqual([
      TaskStatus.COMPLETED,
      TaskStatus.FAILED,
      TaskStatus.STOPPED,
    ])
    expect(PICKABLE_STATUSES).not.toContain(TaskStatus.PENDING)
  })

  it.each([
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.STOPPED,
  ])('三态 %s：加入购物车按钮可见', (status) => {
    const w = mountExec(status)
    expect(w.find(PICK_BTN).exists(), `三态 ${status} 应展示挑选入口`).toBe(true)
    expect(w.find(PICK_BTN).text()).toContain('加入购物车')
  })

  it.each([
    'finished',
    'success',
    TaskStatus.PENDING,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.PAUSED,
    TaskStatus.SKIPPED,
    TaskStatus.MERGED,
  ])('非挑选态 %s：加入购物车按钮不可见（入口与门控同源）', (status) => {
    const w = mountExec(status)
    expect(w.find(PICK_BTN).exists(), `非挑选态 ${status} 不应展示挑选入口`).toBe(false)
  })
})

// ===== TaskDetailModal 详情窗口径 =====

const mocks = vi.hoisted(() => ({
  getOne: vi.fn(),
  getProgress: vi.fn(),
  logsGetAll: vi.fn(),
  notify: vi.fn(),
}))

vi.mock('@/composables/task/tasksPort', () => ({
  tasksPort: {
    getOne: mocks.getOne,
    removeCase: vi.fn(),
    stop: vi.fn(),
    getProgress: mocks.getProgress,
    control: vi.fn(),
    retry: vi.fn(),
    reevaluate: vi.fn(),
  },
}))
vi.mock('@/composables/task/logsPort', () => ({ logsPort: { getAll: mocks.logsGetAll } }))
vi.mock('@/composables/modal/useModal', () => ({ useModalControl: () => ({ open: vi.fn() }) }))
vi.mock('@/composables/modal/useNotification', () => ({
  useNotification: () => ({
    success: mocks.notify,
    error: mocks.notify,
    info: mocks.notify,
    warning: mocks.notify,
  }),
}))

const TASK = (status: string) => ({
  id: 9, name: '任务A', status, cases: [], devices: [], apis: [],
  expectedTotalTime: '', usedTime: '', expectedCompleteTime: '',
})

const PROGRESS = (status: string) => ({
  taskId: '9',
  status,
  testCases: [],
  logs: [],
  apiResources: [],
  totalCount: 0,
  completedCount: 0,
  inProgressCount: 0,
  executionFailedCount: 0,
  evaluationFailedCount: 0,
  progress: 0,
})

async function mountModal(status: string) {
  mocks.getOne.mockResolvedValue(TASK(status))
  mocks.getProgress.mockResolvedValue(PROGRESS(status))
  mocks.logsGetAll.mockResolvedValue({ items: [], total: 0 })
  const w = mount(TaskDetailModal, { props: { taskId: 9 } })
  await flushPromises()
  return w
}

describe('TaskDetailModal 挑选入口与门控一致（INT-553 P3-4）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('completed 任务：详情窗内渲染「加入购物车」按钮', async () => {
    const w = await mountModal(TaskStatus.COMPLETED)
    expect(w.find(PICK_BTN).exists()).toBe(true)
  })

  it('legacy finished 任务：详情窗内不渲染「加入购物车」按钮（原入口可见、门控仅警告）', async () => {
    const w = await mountModal('finished')
    expect(w.find(PICK_BTN).exists()).toBe(false)
  })

  it('legacy success 任务：详情窗内不渲染「加入购物车」按钮', async () => {
    const w = await mountModal('success')
    expect(w.find(PICK_BTN).exists()).toBe(false)
  })

  it('openCherryPick 门控与入口一致：非挑选态点击入口事件不弹向导（仅警告）', async () => {
    const w = await mountModal(TaskStatus.RUNNING)
    ;(w.vm as any).openCherryPick()
    expect(mocks.notify).toHaveBeenCalled()
    expect((w.vm as any).cherryPickVisible).toBe(false)
  })
})
