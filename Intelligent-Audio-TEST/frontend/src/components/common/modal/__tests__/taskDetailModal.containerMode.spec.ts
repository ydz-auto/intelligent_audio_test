/**
 * INT-1832 · 规范 18 §2.3/§2.4：任务详情模态窗的容器接线 —— 集成单测。
 *
 * 锁定口径：
 * - 详情壳（TaskDetailModal）用 useContainerComposition 调 source 端点判定容器，
 *   容器判定结果经 props 落到 TestExecutionComponent（信息头 + 容器版面）
 * - source 200 → 容器：信息头渲染、「用例清单 / 关联资源」折叠区替代页签、进度与日志隐藏
 * - source 400 / code:203（站内普通任务常态）→ 非容器静默：四区形态与现状一致，
 *   无信息头、无折叠区、无错态（详情照常可用）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  getOne: vi.fn(),
  getProgress: vi.fn(),
  logsGetAll: vi.fn(),
  getReviewCount: vi.fn(),
  getSource: vi.fn(),
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
  useModalControl: () => ({ open: vi.fn() }),
  MODAL_TYPES: { BASIC_CONFIRM: 'BASIC_CONFIRM', TEST_CASE_DETAIL: 'TEST_CASE_DETAIL', REEXECUTE_OPTIONS: 'REEXECUTE_OPTIONS' },
}))

vi.mock('../../../../composables/modal/useNotification', () => ({
  useNotification: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
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

beforeEach(() => {
  vi.clearAllMocks()
  mocks.hasPermission.mockReturnValue(true)
  mocks.logsGetAll.mockResolvedValue({ items: [], total: 0 })
  mocks.getProgress.mockResolvedValue(null)
  mocks.getReviewCount.mockResolvedValue(0)
  mocks.getOne.mockResolvedValue(CONTAINER_TASK)
})

const mountModal = async () => {
  const w = mount(TaskDetailModal, { props: { taskId: 580 } })
  await flushPromises()
  return w
}

describe('TaskDetailModal 容器接线（INT-1832）', () => {
  it('source 200 → 详情切容器形态：信息头 + 两个折叠区，进度与日志隐藏', async () => {
    mocks.getSource.mockResolvedValue(CONTAINER_SOURCE)
    const w = await mountModal()

    expect(mocks.getSource).toHaveBeenCalledWith(580)

    // 信息头：合并方式 / 部分失败 / 来源/结果/用例
    expect(w.find('.chb-badge--merge-type').text()).toBe('结果挑选')
    expect(w.find('.chb-badge--warning').text()).toBe('部分失败 3/5')
    const stats = w.find('.chb-stats').text()
    expect(stats).toContain('来源 2 个任务')
    expect(stats).toContain('结果 5 条')
    expect(stats).toContain('用例 5 个')

    // 版面：进度概览 / 实时日志 / 原页签组不出现
    expect(w.find('.progress-overview').exists()).toBe(false)
    expect(w.find('.real-time-logs').exists()).toBe(false)
    expect(w.find('.association-tabs').exists()).toBe(false)
    expect(w.findAll('.container-collapse-header')).toHaveLength(2)
  })

  it('source 400 / code:203（普通任务）→ 非容器静默，详情四区形态不变', async () => {
    const apiError: any = new Error('任务不是挑选合并容器')
    apiError.code = 203
    mocks.getSource.mockRejectedValue(apiError)

    const w = await mountModal()

    expect(w.find('.container-header-badges').exists()).toBe(false)
    expect(w.find('.container-collapse-header').exists()).toBe(false)
    expect(w.find('.progress-overview').exists()).toBe(true)
    expect(w.find('.real-time-logs').exists()).toBe(true)
    expect(w.find('.association-tabs').exists()).toBe(true)
    // 详情本身未被可选增强区拖入错态
    expect(w.find('.error-state').exists()).toBe(false)
    expect(w.text()).toContain('小艺拒识挑选合并')
  })

  it('source 200 + is_cherry_pick=false（普通任务真实返回）→ 同样非容器静默', async () => {
    mocks.getSource.mockResolvedValue({ taskId: 580, isCherryPick: false, total: 0, groups: [] })

    const w = await mountModal()

    expect(w.find('.container-header-badges').exists()).toBe(false)
    expect(w.find('.container-collapse-header').exists()).toBe(false)
    expect(w.find('.progress-overview').exists()).toBe(true)
    expect(w.find('.association-tabs').exists()).toBe(true)
  })
})
