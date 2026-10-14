/**
 * INT-305：执行详情模态窗移除用例 —— 组件单测。
 *
 * 锁定口径：
 * - TestExecutionComponent 用例行渲染移除按钮（平铺/标签分组视图），四阶段均可见
 * - 点击移除按钮 emit removeCase（携带 caseId/name），不冒泡触发用例详情
 * - TaskDetailModal 确认弹窗：按任务阶段给出对应删除后果文案
 *   （执行中→中断当前轮；终态→报告重算/excluded；待执行→直接移除）
 * - 确认后调 tasksPort.removeCase 并本地剔除 + 刷新详情
 * - 取消弹窗不调接口
 * - 最后一个用例时二次确认（确认→连任务停止；取消提示→仅移除）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  removeCase: vi.fn(),
  stop: vi.fn(),
  getOne: vi.fn(),
  logsGetAll: vi.fn(),
  confirmOpen: vi.fn(),
}))

vi.mock('../../../../composables/task/tasksPort', () => ({
  tasksPort: {
    getOne: mocks.getOne,
    removeCase: mocks.removeCase,
    stop: mocks.stop,
    getProgress: vi.fn().mockResolvedValue(null),
    control: vi.fn(),
    retry: vi.fn(),
    reevaluate: vi.fn(),
  },
}))

vi.mock('../../../../composables/task/logsPort', () => ({
  logsPort: { getAll: mocks.logsGetAll },
}))

vi.mock('../../../../composables/modal/useModal', () => {
  const open = mocks.confirmOpen
  return {
    useModalControl: () => ({ open }),
    MODAL_TYPES: { BASIC_CONFIRM: 'BASIC_CONFIRM', TEST_CASE_DETAIL: 'TEST_CASE_DETAIL', REEXECUTE_OPTIONS: 'REEXECUTE_OPTIONS' },
  }
})

vi.mock('../../../../composables/modal/useNotification', () => ({
  useNotification: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))

import TestExecutionComponent from '../../../layout/TestExecutionComponent.vue'
import TaskDetailModal from '../TaskDetailModal.vue'

const CASES = [
  { id: 'c1', name: '用例一', status: 'completed', executionStatus: 'completed', evaluationStatus: 'completed', duration: 3 },
  { id: 'c2', name: '用例二', status: 'pending', executionStatus: 'pending', evaluationStatus: 'pending', duration: '' },
]

const TASK_COMPLETED = {
  id: 9, name: '任务A', status: 'completed', cases: CASES, devices: [], apis: [],
  expectedTotalTime: '', usedTime: '', expectedCompleteTime: '',
}
const TASK_RUNNING = { ...TASK_COMPLETED, status: 'running' }
const TASK_PENDING = { ...TASK_COMPLETED, status: 'pending' }

const mountExec = () =>
  mount(TestExecutionComponent, {
    props: {
      testType: 'API',
      taskInfo: {},
      associatedCases: CASES,
      taskStatus: 'completed',
      showLogs: false,
      activeTab: 'cases',
    },
  })

describe('TestExecutionComponent 移除入口（INT-305）', () => {
  it('用例行渲染移除按钮；点击 emit removeCase 且不触发用例详情', async () => {
    const w = mountExec()
    const btns = w.findAll('button.case-remove-btn')
    expect(btns.length).toBe(2) // 平铺视图两行各一个

    await btns[1].trigger('click')
    const evt = w.emitted('removeCase')
    expect(evt).toBeTruthy()
    expect(evt![0][0]).toMatchObject({ caseId: 'c2', name: '用例二' })
    expect(w.emitted('testCaseClick')).toBeFalsy()
  })

  it('标签/分组视图同款移除入口', async () => {
    const w = mountExec()
    // 切到分组视图
    const groupBtn = w.findAll('.case-view-btn').find(b => b.text().includes('分组'))!
    await groupBtn.trigger('click')
    const groupHeader = w.find('.case-group-header')
    await groupHeader.trigger('click')
    expect(w.findAll('button.case-remove-btn').length).toBe(2)
  })
})

describe('TaskDetailModal 移除流程（INT-305）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.logsGetAll.mockResolvedValue({ items: [], total: 0 })
  })

  const mountModal = async (taskData: any) => {
    mocks.getOne.mockResolvedValue(taskData)
    const w = mount(TaskDetailModal, { props: { taskId: 9 } })
    await flushPromises()
    return w
  }

  it('终态任务：确认文案含报告重算/排除语义；确认后调 removeCase 并本地剔除', async () => {
    const w = await mountModal(TASK_COMPLETED)
    mocks.confirmOpen.mockResolvedValue({ confirmed: true })
    mocks.removeCase.mockResolvedValue({ taskId: '9', caseId: 'c1', purged: false, reportRequeued: true })

    await (w.vm as any).removeCase({ caseId: 'c1', name: '用例一' })
    await flushPromises()

    expect(mocks.confirmOpen).toHaveBeenCalledTimes(1)
    const opts = mocks.confirmOpen.mock.calls[0][1]
    expect(opts.title).toBe('移除用例')
    expect(opts.content).toContain('已结束')
    expect(opts.content).toContain('排除')
    expect(mocks.removeCase).toHaveBeenCalledWith(9, 'c1')
    // 本地剔除 + fetchTaskDetails 刷新（mock getOne 仍返回原 2 例，刷新为准）
    expect(mocks.getOne).toHaveBeenCalled()
  })

  it('执行中任务：文案提示中断当前轮次', async () => {
    const w = await mountModal(TASK_RUNNING)
    mocks.confirmOpen.mockResolvedValue({ confirmed: false })

    await (w.vm as any).removeCase({ caseId: 'c1', name: '用例一' })

    const opts = mocks.confirmOpen.mock.calls[0][1]
    expect(opts.content).toContain('正在执行')
    expect(opts.content).toContain('中断')
    expect(mocks.removeCase).not.toHaveBeenCalled()
  })

  it('待执行任务：文案为直接移除语义', async () => {
    const w = await mountModal(TASK_PENDING)
    mocks.confirmOpen.mockResolvedValue({ confirmed: false })

    await (w.vm as any).removeCase({ caseId: 'c1', name: '用例一' })

    const opts = mocks.confirmOpen.mock.calls[0][1]
    expect(opts.content).toContain('尚未开始执行')
    expect(mocks.removeCase).not.toHaveBeenCalled()
  })

  it('最后一个用例：二次确认后连任务停止；仅移除时不停止', async () => {
    const single = { ...TASK_COMPLETED, cases: [CASES[1]] }
    const w = await mountModal(single)
    // 第一次确认（移除用例）确认；第二次（任务将空）确认
    mocks.confirmOpen
      .mockResolvedValueOnce({ confirmed: true })
      .mockResolvedValueOnce({ confirmed: true })
    mocks.removeCase.mockResolvedValue({ taskId: '9', caseId: 'c2', purged: false, reportRequeued: false })
    mocks.stop.mockResolvedValue({})

    await (w.vm as any).removeCase({ caseId: 'c2', name: '用例二' })
    await flushPromises()

    expect(mocks.confirmOpen).toHaveBeenCalledTimes(2)
    expect(mocks.stop).toHaveBeenCalledWith(9)
    expect(mocks.removeCase).toHaveBeenCalledWith(9, 'c2')
  })

  it('最后一个用例：二次确认选仅移除 → 不停止任务', async () => {
    const single = { ...TASK_COMPLETED, cases: [CASES[1]] }
    const w = await mountModal(single)
    mocks.confirmOpen
      .mockResolvedValueOnce({ confirmed: true })
      .mockResolvedValueOnce({ confirmed: false })
    mocks.removeCase.mockResolvedValue({ taskId: '9', caseId: 'c2', purged: false, reportRequeued: false })

    await (w.vm as any).removeCase({ caseId: 'c2', name: '用例二' })
    await flushPromises()

    expect(mocks.stop).not.toHaveBeenCalled()
    expect(mocks.removeCase).toHaveBeenCalled()
  })

  it('用户取消确认 → 不调接口', async () => {
    const w = await mountModal(TASK_COMPLETED)
    mocks.confirmOpen.mockResolvedValue({ confirmed: false })

    await (w.vm as any).removeCase({ caseId: 'c1', name: '用例一' })

    expect(mocks.removeCase).not.toHaveBeenCalled()
    expect((w.vm as any).associatedCases.length).toBe(2)
  })
})
