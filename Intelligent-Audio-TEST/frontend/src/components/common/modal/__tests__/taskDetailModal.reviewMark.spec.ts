/**
 * INT-340：任务详情模态窗用例行「人工复核」标记 —— 组件单测。
 *
 * 锁定口径（验收 §7.2 / 验收打回 P1 修复）：
 * - fetchTaskDetails 组装 associatedCases 时透传 reviewed（后端 cases[].reviewed 已由
 *   taskAdapter.toTaskCaseBrief 转 camelCase），漏透传则 TestExecutionComponent:280
 *   `v-if="testCase.reviewed"` 徽章永不渲染
 * - 终态任务含复核结果：用例行渲染「已复核」徽章
 * - 未复核/缺省：reviewed=false，不渲染徽章
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  getOne: vi.fn(),
  logsGetAll: vi.fn(),
  confirmOpen: vi.fn(),
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
  useNotification: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))

import TaskDetailModal from '../TaskDetailModal.vue'

const CASES_WITH_REVIEW = [
  { id: 'c1', name: '用例一', status: 'completed', executionStatus: 'completed', evaluationStatus: 'completed', duration: 3, reviewed: true },
  { id: 'c2', name: '用例二', status: 'failed', executionStatus: 'failed', evaluationStatus: 'failed', duration: 2, reviewed: false },
]

const TASK_COMPLETED_WITH_REVIEW = {
  id: 9, name: '任务A', status: 'completed', cases: CASES_WITH_REVIEW, devices: [], apis: [],
  expectedTotalTime: '', usedTime: '', expectedCompleteTime: '',
}

/** 未复核结果 reviewed 缺省（后端可能不下发），映射需容错为 false */
const CASES_REVIEW_MISSING = [
  { id: 'c3', name: '用例三', status: 'completed', executionStatus: 'completed', evaluationStatus: 'completed', duration: 1 },
]

describe('TaskDetailModal 用例行人工复核标记（INT-340）', () => {
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

  it('任务详情 cases[] 映射透传 reviewed，复核结果用例行渲染「已复核」徽章', async () => {
    const w = await mountModal(TASK_COMPLETED_WITH_REVIEW)
    await flushPromises()

    const cases = (w.vm as any).associatedCases as any[]
    expect(cases.length).toBe(2)
    expect(cases[0].reviewed).toBe(true)
    expect(cases[1].reviewed).toBe(false)

    // 用例行徽章：复核用例渲染，未复核不渲染
    const badges = w.findAll('.reviewed-badge')
    expect(badges.length).toBe(1)
    expect(badges[0].text()).toContain('已复核')
  })

  it('reviewed 缺省（后端未下发）容错为 false，不渲染徽章', async () => {
    const w = await mountModal({ ...TASK_COMPLETED_WITH_REVIEW, cases: CASES_REVIEW_MISSING })
    await flushPromises()

    const cases = (w.vm as any).associatedCases as any[]
    expect(cases[0].reviewed).toBe(false)
    expect(w.findAll('.reviewed-badge').length).toBe(0)
  })
})
