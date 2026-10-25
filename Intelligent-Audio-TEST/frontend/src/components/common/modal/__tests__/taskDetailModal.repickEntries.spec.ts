/**
 * INT-1838 · 规范 18 §6：挑选合并容器「再次挑选」入口 —— 集成单测。
 *
 * 锁定口径：
 * - 容器详情动作组出现两个入口（复用本次结果重新挑选 / 开始挑选），与「生成 AI 报告」并列
 * - 两入口同需 task:cherry_pick：无权限（algo_engineer / guest）整组隐藏，组成区与信息头只读可见
 * - 「复用本次结果重新挑选」= 取 source.groups[].results[] 全部 result_id 一次批量加购 →
 *   toast → 打开购物车抽屉；不复制容器、不新建任务；重复点击幂等（后端跳过已加购）
 * - 「开始挑选」= 写共享请求 step='pick'（不预筛任何来源任务）→ 跳挑选合并页签
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  getOne: vi.fn(),
  getProgress: vi.fn(),
  logsGetAll: vi.fn(),
  getReviewCount: vi.fn(),
  getSource: vi.fn(),
  hasPermission: vi.fn((_point?: string): boolean => true),
  addToCart: vi.fn(),
  openDrawer: vi.fn(),
  requestPickWizard: vi.fn(),
  push: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
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
  useModalControl: () => ({ open: vi.fn(), close: vi.fn() }),
  MODAL_TYPES: { BASIC_CONFIRM: 'BASIC_CONFIRM', TEST_CASE_DETAIL: 'TEST_CASE_DETAIL', REEXECUTE_OPTIONS: 'REEXECUTE_OPTIONS', TASK_DETAIL: 'TASK_DETAIL' },
}))

vi.mock('../../../../composables/modal/useNotification', () => ({
  useNotification: () => ({
    success: mocks.success,
    warning: mocks.warning,
    error: mocks.error,
    info: vi.fn(),
  }),
}))

// 再次挑选入口的三个协作层（加购 / 抽屉 / 向导请求）
vi.mock('../../../../composables/task/usePickCart', () => ({
  usePickCart: () => ({ addToCart: mocks.addToCart }),
}))

vi.mock('../../../../composables/task/cartDrawerState', () => ({
  useCartDrawerState: () => ({ open: mocks.openDrawer, close: vi.fn(), visible: { value: false } }),
}))

vi.mock('../../../../composables/task/usePickWizardRequest', () => ({
  requestPickWizard: mocks.requestPickWizard,
  clearPickWizardRequest: vi.fn(),
  usePickWizardRequest: () => ({ pendingRequest: { value: null } }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push }),
  useRoute: () => ({ query: {} }),
}))

// 只替换容器溯源端点，其余 infrastructure 保持真实
vi.mock('@/infrastructure/api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    cherryPickApi: { ...actual.cherryPickApi, getSource: mocks.getSource },
    tasksApi: { ...actual.tasksApi, getReviewCount: mocks.getReviewCount },
  }
})

import TaskDetailModal from '../TaskDetailModal.vue'

const CONTAINER_TASK = {
  id: 580,
  name: '小艺拒识挑选合并_2026/10/24 09:12:31',
  description: '挑选合并自 2 个来源任务',
  status: 'failed',
  executionStatus: 'failed',
  caseCount: 5,
  totalCases: 5,
  failedCases: 3,
  createdAt: '2026-10-24T01:07:59Z',
  cases: [
    { id: 'c1', name: '用例一', status: 'completed', executionStatus: 'completed', evaluationStatus: 'completed', duration: 3 },
    { id: 'c2', name: '用例二', status: 'failed', executionStatus: 'failed', evaluationStatus: 'completed' },
  ],
  devices: [{ id: 9, name: 'pura90小艺', status: 'online' }],
  apis: [],
  expectedTotalTime: '',
  usedTime: '',
  expectedCompleteTime: '',
}

const CONTAINER_SOURCE = {
  taskId: 580,
  isCherryPick: true,
  total: 5,
  groups: [
    { sourceTaskId: 384, sourceTaskName: 'E2E测试任务_2026/9/21', results: [{ id: 1, resultId: 3792 }, { id: 2, resultId: 3796 }] },
    { sourceTaskId: 419, sourceTaskName: '小艺拒识E2E测试任务_2026/10/13', results: [{ id: 3, resultId: 5714 }, { id: 4, resultId: 5715 }, { id: 5, resultId: 5716 }] },
  ],
}

const ALL_RESULT_IDS = [3792, 3796, 5714, 5715, 5716]

const mountModal = async () => {
  const w = mount(TaskDetailModal, { props: { taskId: 580 } })
  await flushPromises()
  return w
}

const actionButton = (w: ReturnType<typeof mount>, label: string) =>
  w.findAll('.task-detail-actions button').find((b) => b.text().includes(label))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.hasPermission.mockReturnValue(true)
  mocks.logsGetAll.mockResolvedValue({ items: [], total: 0 })
  mocks.getProgress.mockResolvedValue(null)
  mocks.getReviewCount.mockResolvedValue(0)
  mocks.getOne.mockResolvedValue(CONTAINER_TASK)
  mocks.getSource.mockResolvedValue(CONTAINER_SOURCE)
  mocks.addToCart.mockResolvedValue({ added: ALL_RESULT_IDS, missing: [], duplicated: [] })
})

describe('TaskDetailModal 再次挑选入口（INT-1838）', () => {
  it('容器 + task:cherry_pick → 动作组渲染两个入口，与「生成 AI 报告」并列', async () => {
    const w = await mountModal()

    const labels = w.findAll('.task-detail-actions button').map((b) => b.text())
    expect(labels.some((t) => t.includes('生成 AI 报告'))).toBe(true)
    expect(labels.some((t) => t.includes('复用本次结果重新挑选'))).toBe(true)
    expect(labels.some((t) => t.includes('开始挑选'))).toBe(true)
  })

  it('无 task:cherry_pick（algo_engineer / guest）→ 两入口隐藏，信息头与组成区只读可见', async () => {
    mocks.hasPermission.mockImplementation((p?: string) => p !== 'task:cherry_pick')
    const w = await mountModal()

    expect(actionButton(w, '复用本次结果重新挑选')).toBeUndefined()
    expect(actionButton(w, '开始挑选')).toBeUndefined()
    // 只读可见：信息头 + 组成区照常
    expect(w.find('.container-header-badges').exists()).toBe(true)
    expect(w.find('#composition').exists()).toBe(true)
  })

  it('非容器任务 → 不渲染再次挑选入口', async () => {
    mocks.getSource.mockResolvedValue({ taskId: 580, isCherryPick: false, total: 0, groups: [] })
    const w = await mountModal()

    expect(actionButton(w, '复用本次结果重新挑选')).toBeUndefined()
    expect(actionButton(w, '开始挑选')).toBeUndefined()
  })

  it('「复用本次结果重新挑选」→ 一次批量加购（条数 = source.total）→ toast → 打开购物车抽屉', async () => {
    const w = await mountModal()

    await actionButton(w, '复用本次结果重新挑选')!.trigger('click')
    await flushPromises()

    // 一次批量请求，result_id 覆盖 source 全量（不复制容器、不新建任务）
    expect(mocks.addToCart).toHaveBeenCalledTimes(1)
    expect(mocks.addToCart).toHaveBeenCalledWith(ALL_RESULT_IDS)
    expect(mocks.success).toHaveBeenCalledWith(`已加入购物车 ${ALL_RESULT_IDS.length} 条`)
    expect(mocks.error).not.toHaveBeenCalled()
    expect(mocks.openDrawer).toHaveBeenCalledTimes(1)
  })

  it('重复点击幂等：后端跳过已加购 → 提示重复条数，不报错', async () => {
    mocks.addToCart.mockResolvedValue({ added: [], missing: [], duplicated: ALL_RESULT_IDS })
    const w = await mountModal()

    await actionButton(w, '复用本次结果重新挑选')!.trigger('click')
    await flushPromises()

    expect(mocks.success).toHaveBeenCalledWith('已加入购物车 0 条（重复 5 条已跳过）')
    expect(mocks.error).not.toHaveBeenCalled()
    expect(mocks.openDrawer).toHaveBeenCalledTimes(1)
  })

  it('源结果已失效 → 回显失效条数（warning），仍打开抽屉', async () => {
    mocks.addToCart.mockResolvedValue({ added: [3792, 3796, 5714], missing: [5715, 5716], duplicated: [] })
    const w = await mountModal()

    await actionButton(w, '复用本次结果重新挑选')!.trigger('click')
    await flushPromises()

    expect(mocks.warning).toHaveBeenCalledWith('已加入购物车 3 条（2 条源结果已失效未加入）')
    expect(mocks.openDrawer).toHaveBeenCalledTimes(1)
  })

  it('「开始挑选」→ 打开阶段 1（step=pick，不预筛任务）并跳挑选合并页签', async () => {
    const w = await mountModal()

    await actionButton(w, '开始挑选')!.trigger('click')

    expect(mocks.requestPickWizard).toHaveBeenCalledWith({ step: 'pick' })
    // 无 presetTaskIds = 不预筛任何来源任务
    expect(mocks.requestPickWizard.mock.calls[0][0].presetTaskIds).toBeUndefined()
    expect(mocks.push).toHaveBeenCalledWith({ path: '/tasks', query: { tab: 'cherry-picks' } })
  })

  it('加购失败 → 错误 toast，不打开抽屉', async () => {
    mocks.addToCart.mockRejectedValue(new Error('加入购物车失败'))
    const w = await mountModal()

    await actionButton(w, '复用本次结果重新挑选')!.trigger('click')
    await flushPromises()

    expect(mocks.error).toHaveBeenCalledWith('加入购物车失败')
    expect(mocks.openDrawer).not.toHaveBeenCalled()
  })

  it('溯源定位：带 focusCaseId 打开时把来源用例卡滚入可视区并高亮（§6 行内溯源）', async () => {
    const w = mount(TaskDetailModal, { props: { taskId: 580, focusCaseId: 'c2' } })
    await flushPromises()
    await new Promise((r) => setTimeout(r, 400))

    const cards = w.findAll('.case-card')
    expect(cards.length).toBeGreaterThan(0)
    const focused = w.find('.case-card.tdm-focus-highlight')
    expect(focused.exists()).toBe(true)
    // 命中的是来源用例 c2（不是同页其它用例）
    expect(focused.text()).toContain('c2')
  })

  it('未带 focusCaseId → 不高亮任何用例卡', async () => {
    const w = await mountModal()
    await flushPromises()
    expect(w.find('.case-card.tdm-focus-highlight').exists()).toBe(false)
  })
})
